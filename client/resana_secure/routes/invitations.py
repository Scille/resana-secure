from __future__ import annotations

from typing import TypedDict, Any

from quart import Blueprint

from parsec.core.logged_core import LoggedCore
from parsec.api.protocol import InvitationType

from ..utils import (
    authenticated,
    get_data,
    Parser,
    APIException,
    build_apitoken,
    apitoken_to_addr,
    backend_errors_to_api_exceptions,
    get_user_id_from_email,
    email_validator,
)


invitations_bp = Blueprint("invitations_api", __name__)


class GetInvitationReply(TypedDict):
    users: list[dict[str, str]]
    device: dict[str, str] | None
    shared_recoveries: list[dict[str, str]]


@invitations_bp.route("/invitations", methods=["GET"])
@authenticated
async def get_invitations(core: LoggedCore) -> tuple[GetInvitationReply, int]:
    with backend_errors_to_api_exceptions():
        invitations = await core.list_invitations()

    cooked: GetInvitationReply = {"users": [], "device": None, "shared_recoveries": []}

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
        elif invitation.type == InvitationType.DEVICE:
            cooked["device"] = {
                "token": apitoken,
                "created_on": invitation.created_on.to_rfc3339(),
                "status": invitation.status.str,
            }
        elif invitation.type == InvitationType.SHAMIR_RECOVERY:
            claimer_certificate, _ = await core._remote_devices_manager.get_user(
                invitation.claimer_user_id
            )
            assert claimer_certificate.human_handle is not None
            cooked["shared_recoveries"].append(
                {
                    "token": apitoken,
                    "created_on": invitation.created_on.to_rfc3339(),
                    "claimer_email": claimer_certificate.human_handle.email,
                    "status": invitation.status.str,
                }
            )
        else:
            assert False

    return cooked, 200


@invitations_bp.route("/invitations", methods=["POST"])
@authenticated
async def create_invitation(core: LoggedCore) -> tuple[dict[str, Any], int]:
    data = await get_data()
    parser = Parser()
    parser.add_argument("type", type=str, required=True)
    parser.add_argument("claimer_email", type=str, validator=email_validator)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    if args["type"] not in ("user", "device", "shared_recovery"):
        raise APIException.from_bad_fields(["type"])
    if args["type"] == "user" and not args["claimer_email"]:
        raise APIException.from_bad_fields(["claimer_email"])
    if args["type"] == "shared_recovery" and not args["claimer_email"]:
        raise APIException.from_bad_fields(["claimer_email"])

    with backend_errors_to_api_exceptions():
        if args["type"] == "user":
            addr, _ = await core.new_user_invitation(email=args["claimer_email"], send_email=False)
        elif args["type"] == "device":
            addr, _ = await core.new_device_invitation(send_email=False)
        elif args["type"] == "shared_recovery":
            user_id = await get_user_id_from_email(core, args["claimer_email"], omit_revoked=True)
            if user_id is None:
                return {"error": "claimer_not_a_member"}, 400
            addr, _ = await core.new_shamir_recovery_invitation(user_id, send_email=False)
        else:
            assert False

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
