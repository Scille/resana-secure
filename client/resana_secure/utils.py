from __future__ import annotations

import platform
from base64 import urlsafe_b64decode, urlsafe_b64encode
from contextlib import contextmanager
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterator, TypeVar

from quart import jsonify, request, session
from typing_extensions import Concatenate, ParamSpec
from werkzeug.exceptions import HTTPException

from parsec._parsec import DateTime, HumanHandle, UserID
from parsec.api.data import EntryID
from parsec.api.protocol import DeviceLabel, InvitationToken, InvitationType, OrganizationID
from parsec.core.backend_connection import (
    BackendConnectionError,
    BackendConnectionRefused,
    BackendInvitationAlreadyUsed,
    BackendInvitationNotFound,
    BackendInvitationOnExistingMember,
    BackendInvitationShamirRecoveryNotSetup,
    BackendNotAvailable,
    BackendNotFoundError,
)
from parsec.core.fs.exceptions import (
    FSBackendOfflineError,
    FSError,
    FSNoAccessError,
    FSReadOnlyError,
    FSSharingNotAllowedError,
    FSWorkspaceArchivingNotAllowedError,
    FSWorkspaceArchivingPeriodTooShort,
    FSWorkspaceNoAccess,
    FSWorkspaceNoReadAccess,
    FSWorkspaceNotFoundError,
    FSWorkspaceRealmArchived,
    FSWorkspaceRealmDeleted,
)
from parsec.core.fs.workspacefs import WorkspaceFS, WorkspaceFSTimestamped
from parsec.core.invite import (
    InviteAlreadyUsedError,
    InviteError,
    InviteNotFoundError,
    InvitePeerResetError,
)
from parsec.core.logged_core import LoggedCore
from parsec.core.mountpoint import MountpointAlreadyMounted, MountpointNotMounted
from parsec.core.types import BackendInvitationAddr, BackendOrganizationAddr

from .app import current_app
from .cores_manager import CoreNotLoggedError, find_matching_devices
from .invites_manager import LongTermCtxNotStarted


class APIException(HTTPException):
    def __init__(self, status_code: int, data: Any) -> None:
        response = jsonify(data)
        response.status_code = status_code
        super().__init__(response=response)

    @classmethod
    def from_bad_fields(cls, bad_fields: list[str]) -> APIException:
        return cls(status_code=400, data={"error": "bad_data", "fields": bad_fields})


def get_auth_token() -> str | None:
    authorization_header = request.headers.get("authorization")
    if authorization_header is None:
        auth_token = session.get("logged_in")
    else:
        try:
            auth_type, auth_token = authorization_header.split(None, 1)
            if auth_type.lower() != "bearer":
                auth_token = None
        except ValueError:
            auth_token = None
    return auth_token


P = ParamSpec("P")
T = TypeVar("T")


def authenticated(
    fn: Callable[Concatenate[LoggedCore, P], Awaitable[T]]
) -> Callable[P, Awaitable[T]]:
    @wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        auth_token = get_auth_token() or ""
        try:
            async with current_app.cores_manager.get_core(auth_token) as core:
                return await fn(core, *args, **kwargs)

        except CoreNotLoggedError:
            raise APIException(401, {"error": "authentication_requested"})

    return wrapper


def requires_rie(fn: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
    @wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        assert isinstance(args[0], LoggedCore)
        if not args[0].config.mountpoint_enabled:
            raise APIException(401, {"error": "not_connected_to_rie"})
        return await fn(*args, **kwargs)

    return wrapper


class BadField(Exception):
    def __init__(self, name: str):
        self.name = name

    def nested(self, name: str) -> BadField:
        return BadField(f"{name}.{self.name}")


class BadFields(Exception):
    def __init__(self, names: list[str]):
        self.names = names

    def nested(self, name: str) -> BadFields:
        return BadFields([f"{name}.{subname}" for subname in self.names])

    @classmethod
    def from_indexed_bad_fields(cls, indexed_bad_fields: dict[int, list[str]]) -> BadFields:
        return cls(
            [
                f"[{index}].{bad_field}"
                for index, bad_fields in indexed_bad_fields.items()
                for bad_field in bad_fields
            ]
        )


@dataclass
class Argument:
    name: str
    type: Any | None
    converter: Callable[[Any], T] | None
    validator: Callable[[Any], None] | None
    new_name: str | None
    default: Any | None
    required: bool

    def __post_init__(self) -> None:
        assert not (self.required and self.default is not None), "Can't have required with default"
        assert self.type or self.converter, "Type or converter is needed"


class Parser:
    def __init__(self) -> None:
        self.arguments: list[Argument] = []

    def add_argument(
        self,
        name: str,
        type: Any | None = None,
        converter: Callable[[Any], T] | None = None,
        validator: Callable[[Any], None] | None = None,
        new_name: str | None = None,
        default: T | None = None,
        required: bool = False,
    ) -> None:
        self.arguments.append(
            Argument(
                name,
                type=type,
                converter=converter,
                validator=validator,
                new_name=new_name,
                default=default,
                required=required,
            )
        )

    def parse_args(self, data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        args = {}
        bad_fields = []
        for arg in self.arguments:
            try:
                r = self._parse_arg(data, arg)
                name = arg.new_name or arg.name
                args[name] = r
            except BadField as f:
                bad_fields.append(f.name)
            except BadFields as f:
                bad_fields.extend(f.names)
        return args, bad_fields

    def _parse_arg(self, data: dict[str, Any], arg: Argument) -> Any:
        val = data.get(arg.name)
        if val is None:
            if arg.required:
                raise BadField(arg.name)
            return arg.default

        try:
            if arg.validator:
                arg.validator(val)
            if arg.converter:
                return arg.converter(val)
        except (ValueError, TypeError, AssertionError) as exc:
            raise BadField(arg.name) from exc
        except (BadField, BadFields) as exc:
            raise exc.nested(arg.name)

        if arg.type and not isinstance(val, arg.type):
            raise BadField(arg.name)
        return val


async def check_if_timestamp() -> DateTime | None:
    data = await get_data(allow_empty=True)
    parser = Parser()
    parser.add_argument("timestamp", converter=DateTime.from_rfc3339)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)
    return args["timestamp"]


async def get_data(allow_empty: bool = False) -> dict[str, Any]:
    data = await request.get_json(silent=True)
    if data is None:
        # With silent=True, get_json returns None if request is empty (= no mimetype) or with a format error
        if not allow_empty:
            raise APIException(400, {"error": "json_body_expected"})
        if request.mimetype != "":
            raise APIException(400, {"error": "json_body_expected"})
        data = {}
    return data


def build_apitoken(
    backend_addr: BackendOrganizationAddr | BackendInvitationAddr,
    organization_id: OrganizationID,
    invitation_type: InvitationType,
    token: InvitationToken,
) -> str:
    invitation_addr = BackendInvitationAddr.build(
        backend_addr=backend_addr.get_backend_addr(),
        organization_id=organization_id,
        invitation_type=invitation_type,
        token=token,
    )
    return urlsafe_b64encode(invitation_addr.to_url().encode("ascii")).decode("ascii")


def apitoken_to_addr(apitoken: str) -> BackendInvitationAddr:
    invitation_url = urlsafe_b64decode(apitoken.encode("ascii")).decode("ascii")
    return BackendInvitationAddr.from_url(invitation_url)


def check_workspace_available(
    core: LoggedCore, workspace_id: EntryID, timestamp: DateTime | None = None
) -> WorkspaceFS | WorkspaceFSTimestamped:
    try:
        workspace = core.user_fs.get_workspace(workspace_id)
    except FSWorkspaceNotFoundError:
        raise APIException(404, {"error": "unknown_workspace"})
    if timestamp:
        workspace = WorkspaceFSTimestamped(workspace, timestamp)
    if workspace.is_deleted():
        raise APIException(410, {"error": "deleted_workspace"})
    if workspace.get_workspace_entry().role is None:
        raise APIException(403, {"error": "forbidden_workspace"})
    return workspace


def split_workspace_timestamp(workspace_id: str) -> tuple[EntryID, DateTime | None]:
    timestamp_parsed = None
    if "_" in workspace_id:
        workspace_id_temp, *others = workspace_id.split("_")
        workspace_id = workspace_id_temp
        timestamp = others[0]
        try:
            timestamp_parsed = DateTime.from_rfc3339(timestamp)
        except ValueError:
            raise APIException(404, {"error": "unknown_workspace"})
    try:
        workspace_id_parsed = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})
    return workspace_id_parsed, timestamp_parsed


@contextmanager
def backend_errors_to_api_exceptions() -> Iterator[None]:
    try:
        yield

    except BackendNotAvailable:
        raise APIException(503, {"error": "offline"})
    except BackendInvitationNotFound:
        raise APIException(400, {"error": "invitation_not_found"})
    except BackendInvitationAlreadyUsed:
        raise APIException(400, {"error": "invitation_already_used"})
    except BackendConnectionRefused:
        raise APIException(502, {"error": "connection_refused_by_server"})
    except BackendNotFoundError:
        raise APIException(404, {"error": "not_found"})
    except BackendInvitationOnExistingMember:
        raise APIException(400, {"error": "claimer_already_member"})
    except BackendInvitationShamirRecoveryNotSetup:
        raise APIException(400, {"error": "no_shamir_recovery_setup"})
    except BackendConnectionError as exc:
        # Should mainly catch `BackendProtocolError`
        raise APIException(400, {"error": "unexpected_error", "detail": repr(exc)})

    # The order is important here since:
    # - `FSWorkspaceArchivedError` inherits from `FSWorkspaceNoAccess`
    # - `FSWorkspaceDeletedError` inherits from `FSWorkspaceNoReadAccess`
    except FSWorkspaceRealmArchived:
        raise APIException(403, {"error": "archived_workspace"})
    except FSWorkspaceRealmDeleted:
        raise APIException(410, {"error": "deleted_workspace"})
    except FSWorkspaceArchivingPeriodTooShort:
        raise APIException(400, {"error": "archiving_period_is_too_short"})
    except FSWorkspaceArchivingNotAllowedError:
        raise APIException(403, {"error": "archiving_not_allowed"})
    except FSWorkspaceNotFoundError:
        raise APIException(404, {"error": "unknown_workspace"})
    except (FSNoAccessError, FSWorkspaceNoAccess):
        raise APIException(403, {"error": "forbidden_workspace"})
    except (FSReadOnlyError, FSWorkspaceNoReadAccess):
        raise APIException(403, {"error": "read_only_workspace"})
    except FSSharingNotAllowedError:
        raise APIException(403, {"error": "sharing_not_allowed"})
    except FSBackendOfflineError:
        raise APIException(503, {"error": "offline"})
    except FileExistsError:
        raise APIException(400, {"error": "file_exists"})
    except FSError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": repr(exc)})

    except InviteNotFoundError:
        raise APIException(404, {"error": "unknown_token"})
    except InvitePeerResetError:
        raise APIException(409, {"error": "invalid_state"})
    except InviteAlreadyUsedError:
        raise APIException(400, {"error": "invitation_already_used"})
    except InviteError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": repr(exc)})

    except LongTermCtxNotStarted:
        raise APIException(409, {"error": "invalid_state"})

    except MountpointAlreadyMounted:
        raise APIException(400, {"error": "mountpoint_already_mounted"})
    except MountpointNotMounted:
        raise APIException(404, {"error": "mountpoint_not_mounted"})


def get_default_device_label() -> DeviceLabel:
    try:
        return DeviceLabel(platform.node() or "-unknown-")
    except ValueError:
        return DeviceLabel("-unknown-")


def email_validator(email: str) -> None:
    HumanHandle(email, "email validation")


async def get_user_id_from_email(
    core: LoggedCore, email: str, *, omit_revoked: bool
) -> UserID | None:
    # Note: even with a valid email, we might get more than 1 result here
    # Example:
    # - query: billy@example.co
    # - user1: billy@example.co
    # - user2: billy@example.co.uk
    # Still, checking only the first page should be ok
    user_infos, _ = await core.find_humans(
        query=email, omit_revoked=omit_revoked, omit_non_human=True
    )
    for user_info in user_infos:
        if user_info.human_handle is None:
            continue
        if user_info.human_handle.email != email:
            continue
        return user_info.user_id
    return None


def rename_old_user_key_file(
    email: str, organization_id: OrganizationID, exclude_key_file_path: Path
) -> None:
    matching_devices = find_matching_devices(
        current_app.resana_config.core_config.config_dir,
        email=email,
        organization_id=organization_id,
    )
    for device in matching_devices:
        if exclude_key_file_path and device.key_file_path == exclude_key_file_path:
            continue
        new_key_file_path = str(device.key_file_path).replace(".keys", ".old_key")
        device.key_file_path.rename(new_key_file_path)
