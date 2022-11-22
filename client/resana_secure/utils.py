from __future__ import annotations

from typing import Optional
from functools import wraps
from base64 import urlsafe_b64decode, urlsafe_b64encode
from contextlib import asynccontextmanager, contextmanager
from quart import jsonify, current_app, session, request
from werkzeug.exceptions import HTTPException
from werkzeug.routing import BaseConverter

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

from .cores_manager import CoreNotLoggedError
from .invites_manager import LongTermCtxNotStarted


class EntryIDConverter(BaseConverter):
    def to_python(self, value):
        return super().to_python(value)

    def to_url(self, value) -> str:
        return super().to_url(value)


class APIException(HTTPException):
    def __init__(self, status_code, data) -> None:
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


def authenticated(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        auth_token = get_auth_token() or ""

        try:
            async with current_app.cores_manager.get_core(auth_token) as core:
                return await fn(*args, core=core, **kwargs)

        except CoreNotLoggedError:
            raise APIException(401, {"error": "authentication_requested"})

    return wrapper


@asynccontextmanager
async def check_data():
    if not request.is_json:
        raise APIException(400, {"error": "json_body_expected"})
    data = await request.get_json(silent=True)
    if data is None:
        raise APIException(400, {"error": "json_body_expected"})
    bad_fields = set()
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


@contextmanager
def backend_errors_to_api_exceptions():
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
