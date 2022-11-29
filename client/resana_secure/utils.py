from __future__ import annotations

from typing import Callable, AsyncIterator, Iterator, Optional, Any, TypeVar, Awaitable
from typing_extensions import ParamSpec, Concatenate
from functools import wraps
from base64 import urlsafe_b64decode, urlsafe_b64encode
from contextlib import asynccontextmanager, contextmanager
from quart import jsonify, session, request
from werkzeug.exceptions import HTTPException
from werkzeug.routing import BaseConverter

from parsec._parsec import DateTime
from parsec.core.logged_core import LoggedCore
from parsec.api.data import EntryID
from parsec.api.protocol import OrganizationID, InvitationType, InvitationToken
from parsec.core.types import BackendInvitationAddr, BackendOrganizationAddr
from parsec.core.backend_connection import (
    BackendConnectionError,
    BackendNotAvailable,
    BackendConnectionRefused,
    BackendInvitationNotFound,
    BackendInvitationAlreadyUsed,
    BackendNotFoundError,
    BackendInvitationOnExistingMember,
)
from parsec.core.fs.exceptions import (
    FSWorkspaceNotFoundError,
    FSSharingNotAllowedError,
    FSBackendOfflineError,
    FSReadOnlyError,
    FSNoAccessError,
    FSError,
)
from parsec.core.invite import (
    InviteError,
    InviteNotFoundError,
    InviteAlreadyUsedError,
    InvitePeerResetError,
)
from parsec.core.mountpoint import MountpointAlreadyMounted, MountpointNotMounted
from parsec.core.fs.workspacefs import WorkspaceFS, WorkspaceFSTimestamped

from .cores_manager import CoreNotLoggedError
from .invites_manager import LongTermCtxNotStarted
from .app import current_app


class EntryIDConverter(BaseConverter):
    def to_python(self, value: str) -> Any:
        return super().to_python(value)

    def to_url(self, value: Any) -> str:
        return super().to_url(value)


class APIException(HTTPException):
    def __init__(self, status_code: int, data: Any) -> None:
        response = jsonify(data)
        response.status_code = status_code
        super().__init__(response=response)


def get_auth_token() -> Optional[str]:
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


async def check_if_timestamp() -> Optional[DateTime]:
    data = await request.get_json(silent=True)
    if data is None:
        if request.mimetype == "":
            # No content given
            return None
        else:
            raise APIException(400, {"error": "json_body_expected"})
    timestamp_raw = data.get("timestamp")
    if timestamp_raw is not None:
        try:
            timestamp = DateTime.from_rfc3339(timestamp_raw)
        except (ValueError, TypeError):
            raise APIException(400, {"error": "bad_data", "fields": ["timestamp"]})
    else:
        timestamp = None
    return timestamp


@asynccontextmanager
async def check_data() -> AsyncIterator[tuple[Any, set[str]]]:
    if not request.is_json:
        raise APIException(400, {"error": "json_body_expected"})
    data = await request.get_json(silent=True)
    if data is None:
        raise APIException(400, {"error": "json_body_expected"})
    bad_fields: set[str] = set()
    yield data, bad_fields
    if bad_fields:
        raise APIException(400, {"error": "bad_data", "fields": list(bad_fields)})


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


def get_workspace_type(
    core: LoggedCore, workspace_id: EntryID, timestamp: Optional[DateTime] = None
) -> WorkspaceFS | WorkspaceFSTimestamped:
    workspace = core.user_fs.get_workspace(workspace_id)
    if timestamp:
        workspace = WorkspaceFSTimestamped(workspace, timestamp)
    return workspace


def split_workspace_timestamp(workspace_id: str) -> tuple[EntryID, Optional[DateTime]]:
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
    except BackendConnectionError as exc:
        # Should mainly catch `BackendProtocolError`
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    except (FSWorkspaceNotFoundError, FSNoAccessError):
        raise APIException(404, {"error": "unknown_workspace"})
    except FSReadOnlyError:
        raise APIException(403, {"error": "read_only_workspace"})
    except FSSharingNotAllowedError:
        raise APIException(403, {"error": "sharing_not_allowed"})
    except FSBackendOfflineError:
        raise APIException(503, {"error": "offline"})
    except FSError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    except InviteNotFoundError:
        raise APIException(404, {"error": "unknown_token"})
    except InvitePeerResetError:
        raise APIException(409, {"error": "invalid_state"})
    except InviteAlreadyUsedError:
        raise APIException(400, {"error": "invitation_already_used"})
    except InviteError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    except LongTermCtxNotStarted:
        raise APIException(409, {"error": "invalid_state"})

    except MountpointAlreadyMounted:
        raise APIException(400, {"error": "mountpoint_already_mounted"})
    except MountpointNotMounted:
        raise APIException(404, {"error": "mountpoint_not_mounted"})
