from quart import Blueprint

from parsec.api.protocol import InvitationType
from parsec.core.backend_connection import (
    BackendConnectionError,
    BackendNotAvailable,
    BackendConnectionRefused,
    BackendInvitationNotFound,
    BackendInvitationAlreadyUsed,
    BackendInvitationOnExistingMember,
)

from ..utils import authenticated, check_data, APIException, build_apitoken, apitoken_to_addr


invitations_bp = Blueprint("invitations_api", __name__)


@invitations_bp.route("/invitations", methods=["GET"])
@authenticated
async def get_invitations(core):
    try:
        invitations = await core.list_invitations()

    except BackendNotAvailable:
        raise APIException(503, {"error": "offline"})
    except BackendConnectionRefused:
        raise APIException(502, {"error": "connection_refused_by_server"})
    except BackendConnectionError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    cooked = {"users": [], "device": None}

    for invitation in invitations:
        apitoken = build_apitoken(
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

    try:
        if type == "user":
            addr = await core.new_user_invitation(email=claimer_email, send_email=False)
        else:
            addr = await core.new_device_invitation(send_email=False)

    except BackendInvitationOnExistingMember:
        raise APIException(400, {"error": "claimer_already_member"})
    except BackendNotAvailable:
        raise APIException(503, {"error": "offline"})
    except BackendConnectionRefused:
        raise APIException(502, {"error": "connection_refused_by_server"})
    except BackendConnectionError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    apitoken = build_apitoken(
        organization_id=addr.organization_id, invitation_type=addr.invitation_type, token=addr.token
    )
    return {"token": apitoken}, 200


@invitations_bp.route("/invitations/<string:apitoken>", methods=["DELETE"])
@authenticated
async def delete_invitation(core, apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    try:
        await core.delete_invitation(token=addr.token)

    except BackendNotAvailable:
        raise APIException(503, {"error": "offline"})
    except BackendInvitationNotFound:
        raise APIException(404, {"error": "unknown_token"})
    except BackendInvitationAlreadyUsed:
        raise APIException(400, {"error": "already_used"})
    except BackendConnectionRefused:
        raise APIException(502, {"error": "connection_refused_by_server"})
    except BackendConnectionError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    return {}, 204
