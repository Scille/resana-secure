from __future__ import annotations

from typing import TypedDict, Any

from quart import Blueprint

from parsec.core.logged_core import LoggedCore
from parsec.api.protocol import InvitationType

from ..utils import (
    authenticated,
    get_data,
    parse_arg,
    BadField,
    APIException,
    build_apitoken,
    apitoken_to_addr,
    backend_errors_to_api_exceptions,
)


invitations_bp = Blueprint("invitations_api", __name__)


class GetInvitationReply(TypedDict):
    users: list[dict[str, str]]
    device: dict[str, str] | None


@invitations_bp.route("/invitations", methods=["GET"])
@authenticated
async def get_invitations(core: LoggedCore) -> tuple[GetInvitationReply, int]:
    with backend_errors_to_api_exceptions():
        invitations = await core.list_invitations()

    cooked: GetInvitationReply = {"users": [], "device": None}

    for invitation in invitations:
        apitoken = build_apitoken(
            backend_addr=core.device.organization_addr,
            organization_id=core.device.organization_id,
            invitation_type=invitation.type,
            token=invitation.token,
        )
        if invitation.type == InvitationType.USER:
            cooked["users"].append(
                {
                    "token": apitoken,
                    "created_on": invitation.created_on.to_rfc3339(),
                    "claimer_email": invitation.claimer_email,
                    "status": invitation.status.str,
                }
            )
        else:  # Device
            cooked["device"] = {
                "token": apitoken,
                "created_on": invitation.created_on.to_rfc3339(),
                "status": invitation.status.str,
            }

    return cooked, 200


@invitations_bp.route("/invitations", methods=["POST"])
@authenticated
async def create_invitation(core: LoggedCore) -> tuple[dict[str, Any], int]:
    data = await get_data()
    type = parse_arg(data, "type", type=str)
    if type not in ("user", "device"):
        raise APIException.from_bad_fields([BadField(name="type")])
    if type == "user":
        claimer_email = parse_arg(data, "claimer_email", type=str)
        if isinstance(claimer_email, BadField):
            raise APIException.from_bad_fields([claimer_email])

    with backend_errors_to_api_exceptions():
        if type == "user" and isinstance(claimer_email, str):
            addr, _ = await core.new_user_invitation(email=claimer_email, send_email=False)
        else:
            addr, _ = await core.new_device_invitation(send_email=False)

    apitoken = build_apitoken(
        backend_addr=addr,
        organization_id=addr.organization_id,
        invitation_type=addr.invitation_type,
        token=addr.token,
    )
    return {"token": apitoken}, 200


@invitations_bp.route("/invitations/<string:apitoken>", methods=["DELETE"])
@authenticated
async def delete_invitation(core: LoggedCore, apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    with backend_errors_to_api_exceptions():
        await core.delete_invitation(token=addr.token)

    return {}, 204
