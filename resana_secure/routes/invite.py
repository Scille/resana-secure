from quart import Blueprint
from uuid import UUID

from parsec.api.protocol import InvitationType
from parsec.core.backend_connection import (
    BackendConnectionError,
    BackendNotAvailable,
    BackendConnectionRefused,
    BackendInvitationNotFound,
    BackendInvitationAlreadyUsed,
    BackendInvitationOnExistingMember,
)
from parsec.core.invite import InviteError, InviteNotFoundError, InviteAlreadyUsedError

from ..utils import authenticated, check_data, APIException


invite_bp = Blueprint("invite_api", __name__)


### Greeter ###


@invite_bp.route("/invitations/<string:token>/greeter/1-wait-peer-ready", methods=["POST"])
@authenticated
async def greeter_1_wait_peer_ready(core, token):
    try:
        token = UUID(hex=token)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    try:
        # First must retrieve the token to known which type it is
        invitations = await core.list_invitations()
        for invitation in invitations:
            if invitation["token"] == token:
                break
        else:
            raise APIException(404, {"error": "unknown_token"})

        # Now actually start the invitation
        if invitation["type"] == InvitationType.USER:
            in_progress_ctx = await core.start_greeting_user(token)
        else:
            in_progress_ctx = await core.start_greeting_device(token)

    except InviteNotFoundError:
        raise APIException(404, {"error": "unknown_token"})
    except InviteAlreadyUsedError:
        raise APIException(400, {"error": "invitation_already_used"})
    except BackendNotAvailable:
        raise APIException(503, {"error": "offline"})
    except BackendConnectionRefused:
        raise APIException(502, {"error": "connection_refused_by_server"})
    except (BackendConnectionError, InviteError) as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    return {"type": invitation["type"].value, "greeter_sas": in_progress_ctx.greeter_sas}, 200


@invite_bp.route("/invitations/<string:token>/greeter/2-wait-peer-trust", methods=["POST"])
@authenticated
async def greeter_2_wait_peer_trust(core, token):
    try:
        token = UUID(hex=token)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    try:
        if invitation["type"] == InvitationType.USER:
            in_progress_ctx = await core.start_greeting_user(token)
        else:
            in_progress_ctx = await core.start_greeting_device(token)

    except InviteNotFoundError:
        raise APIException(404, {"error": "unknown_token"})
    except InviteAlreadyUsedError:
        raise APIException(400, {"error": "invitation_already_used"})
    except BackendNotAvailable:
        raise APIException(503, {"error": "offline"})
    except BackendConnectionRefused:
        raise APIException(502, {"error": "connection_refused_by_server"})
    except (BackendConnectionError, InviteError) as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    return {"candidate_claimer_sas": candidate_claimer_sas}, 200


@invite_bp.route("/invitations/<string:token>/greeter/3-check-trust", methods=["POST"])
@authenticated
async def greeter_3_check_trust(core, token):
    try:
        token = UUID(hex=token)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})


@invite_bp.route("/invitations/<string:token>/greeter/4-finalize", methods=["POST"])
@authenticated
async def greeter_4_finalize(core, token):
    try:
        token = UUID(hex=token)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    return {}, 200  # TODO


### Claimer ###


# Note claimer routes are not authentication


@invite_bp.route("/invitations/<string:token>/claimer/1-wait-peer-ready", methods=["POST"])
async def claimer_1_wait_peer_ready(token):
    try:
        token = UUID(hex=token)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    return {}, 200  # TODO


@invite_bp.route("/invitations/<string:token>/claimer/2-check-trust", methods=["POST"])
async def claimer_2_check_trust(token):
    try:
        token = UUID(hex=token)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    return {}, 200  # TODO


@invite_bp.route("/invitations/<string:token>/claimer/3-wait-peer-trust", methods=["POST"])
async def claimer_3_wait_peer_trust(token):
    try:
        token = UUID(hex=token)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    return {}, 200  # TODO


@invite_bp.route("/invitations/<string:token>/claimer/4-finalize", methods=["POST"])
async def claimer_4_finalize(token):
    try:
        token = UUID(hex=token)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    return {}, 200  # TODO
