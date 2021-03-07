from uuid import UUID
from functools import wraps
from contextlib import asynccontextmanager
from quart import jsonify, Response, current_app, session, request
from quart.exceptions import HTTPException
from werkzeug.routing import BaseConverter

from parsec.api.protocol import OrganizationID, InvitationType
from parsec.core.types import BackendInvitationAddr

from .cores_manager import CoreNotLoggedError


class EntryIDConverter(BaseConverter):
    def to_python(self, value):
        return super().to_python(value)

    def to_url(self, value) -> str:
        return super().to_url(value)


class APIException(HTTPException):
    def __init__(self, status_code, data) -> None:
        super().__init__(status_code, "", "")
        self.data = data

    def get_response(self) -> Response:
        response = jsonify(self.data)
        response.status_code = self.status_code
        return response


def authenticated(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        # global auth_token
        auth_token = session.get("logged_in", "")
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
    data = await request.get_json()
    bad_fields = set()
    yield data, bad_fields
    if bad_fields:
        raise APIException(400, {"error": "bad_data", "fields": list(bad_fields)})


def build_apitoken(
    organization_id: OrganizationID, invitation_type: InvitationType, token: UUID
) -> str:
    invitation_type = "u" if invitation_type == InvitationType.USER else "d"
    return f"{organization_id}:{invitation_type}:{token.hex}"


def apitoken_to_addr(apitoken: str) -> BackendInvitationAddr:
    organization_id, invitation_type, token = apitoken.split(":")
    organization_id = OrganizationID(organization_id)
    if invitation_type == "u":
        invitation_type = InvitationType.USER
    elif invitation_type == "d":
        invitation_type = InvitationType.DEVICE
    else:
        raise ValueError
    token = UUID(hex=token)

    return BackendInvitationAddr.build(
        backend_addr=current_app.config["PARSEC_BACKEND_ADDR"],
        organization_id=organization_id,
        invitation_type=invitation_type,
        token=token,
    )
