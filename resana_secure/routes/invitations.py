from quart import Blueprint

from parsec.api.protocol import InvitationType

from ..utils import (
    authenticated,
    check_data,
    APIException,
    build_apitoken,
    apitoken_to_addr,
    backend_errors_to_api_exceptions,
)


invitations_bp = Blueprint("invitations_api", __name__)


@invitations_bp.route("/invitations", methods=["GET"])
@authenticated
async def get_invitations(core):
    with backend_errors_to_api_exceptions():
        invitations = await core.list_invitations()

    cooked = {"users": [], "device": None}

    for invitation in invitations:
        apitoken = build_apitoken(
            backend_addr=core.device.organization_addr,
            organization_id=core.device.organization_id,
            invitation_type=invitation["type"],
            token=invitation["token"],
        )
        if invitation["type"] == InvitationType.USER:
            cooked["users"].append(
                {
                    "token": apitoken,
                    "created_on": invitation["created_on"].to_iso8601_string(),
                    "claimer_email": invitation["claimer_email"],
                    "status": invitation["status"].value,
                }
            )
        else:  # Device
            cooked["device"] = {
                "token": apitoken,
                "created_on": invitation["created_on"].to_iso8601_string(),
                "status": invitation["status"].value,
            }

    return cooked, 200


@invitations_bp.route("/invitations", methods=["POST"])
@authenticated
async def create_invitation(core):
    async with check_data() as (data, bad_fields):
        type = data.get("type")
        if type not in ("user", "device"):
            bad_fields.add("type")
        if type == "user":
            claimer_email = data.get("claimer_email")

    with backend_errors_to_api_exceptions():
        if type == "user":
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
async def delete_invitation(core, apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    with backend_errors_to_api_exceptions():
        await core.delete_invitation(token=addr.token)

    return {}, 204
