from quart import Blueprint, current_app
import platform

from parsec.api.protocol import InvitationType, HumanHandle
from parsec.api.data import UserProfile
from parsec.core.local_device import save_device_with_password
from parsec.core.backend_connection import (
    BackendConnectionError,
    BackendNotAvailable,
    BackendConnectionRefused,
)
from parsec.core.invite import (
    InviteError,
    InviteNotFoundError,
    InviteAlreadyUsedError,
    UserClaimInitialCtx,
    DeviceClaimInitialCtx,
    UserClaimInProgress1Ctx,
    DeviceClaimInProgress1Ctx,
    UserClaimInProgress2Ctx,
    DeviceClaimInProgress2Ctx,
    UserClaimInProgress3Ctx,
    DeviceClaimInProgress3Ctx,
    UserGreetInProgress1Ctx,
    DeviceGreetInProgress1Ctx,
    UserGreetInProgress2Ctx,
    DeviceGreetInProgress2Ctx,
    UserGreetInProgress3Ctx,
    DeviceGreetInProgress3Ctx,
)

from ..utils import authenticated, check_data, APIException, apitoken_to_addr


invite_bp = Blueprint("invite_api", __name__)


### Greeter ###


@invite_bp.route("/invitations/<string:apitoken>/greeter/1-wait-peer-ready", methods=["POST"])
@authenticated
async def greeter_1_wait_peer_ready(core, apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    try:
        async with current_app.greeters_manager.start_greeting_ctx(core, addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            # `do_wait_peer` has been done in `start_greeting_ctx` so nothing more to do

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

    return (
        {
            "type": "user" if addr.invitation_type == InvitationType.USER else "device",
            "greeter_sas": in_progress_ctx.greeter_sas,
        },
        200,
    )


@invite_bp.route("/invitations/<string:apitoken>/greeter/2-wait-peer-trust", methods=["POST"])
@authenticated
async def greeter_2_wait_peer_trust(core, apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    try:
        async with current_app.greeters_manager.retreive_greeting_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx, (UserGreetInProgress1Ctx, DeviceGreetInProgress1Ctx)
            ):
                raise APIException(409, {"error": "invalid_state"})

            in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
            lifetime_ctx.update_in_progress_ctx(in_progress_ctx)

            candidate_claimer_sas = [
                str(x) for x in in_progress_ctx.generate_claimer_sas_choices(size=4)
            ]

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


@invite_bp.route("/invitations/<string:apitoken>/greeter/3-check-trust", methods=["POST"])
@authenticated
async def greeter_3_check_trust(core, apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    async with check_data() as (data, bad_fields):
        claimer_sas = data.get("claimer_sas")
        if not isinstance(claimer_sas, str):
            bad_fields.add("claimer_sas")

    try:
        async with current_app.greeters_manager.retreive_greeting_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx, (UserGreetInProgress2Ctx, DeviceGreetInProgress2Ctx)
            ):
                raise APIException(409, {"error": "invalid_state"})

            if in_progress_ctx.claimer_sas != claimer_sas:
                raise APIException(400, {"error": "bad_claimer_sas"})

            in_progress_ctx = await in_progress_ctx.do_signify_trust()
            lifetime_ctx.update_in_progress_ctx(in_progress_ctx)

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

    return {}, 200


@invite_bp.route("/invitations/<string:apitoken>/greeter/4-finalize", methods=["POST"])
@authenticated
async def greeter_4_finalize(core, apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    async with check_data() as (data, bad_fields):
        if addr.invitation_type == InvitationType.USER:
            claimer_email = data.get("claimer_email")
            if not isinstance(claimer_email, str):
                bad_fields.add("claimer_email")
            granted_profile = data.get("granted_profile")
            if granted_profile == "ADMIN":
                granted_profile = UserProfile.ADMIN
            elif granted_profile == "STANDARD":
                granted_profile = UserProfile.STANDARD
            else:
                bad_fields.add("granted_profile")

    try:
        async with current_app.greeters_manager.retreive_greeting_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()

            if isinstance(in_progress_ctx, UserGreetInProgress3Ctx):
                in_progress_ctx = await in_progress_ctx.do_get_claim_requests()
                await in_progress_ctx.do_create_new_user(
                    author=core.device,
                    device_label=in_progress_ctx.requested_device_label,
                    human_handle=HumanHandle(email=claimer_email, label="-unknown-"),
                    profile=granted_profile,
                )

            elif isinstance(in_progress_ctx, DeviceGreetInProgress3Ctx):
                in_progress_ctx = await in_progress_ctx.do_get_claim_requests()
                await in_progress_ctx.do_create_new_device(
                    author=core.device, device_label=in_progress_ctx.requested_device_label
                )

            else:
                raise APIException(409, {"error": "invalid_state"})

            lifetime_ctx.mark_as_terminated()

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

    return {}, 200


### Claimer ###


# Note claimer routes are not authentication


@invite_bp.route("/invitations/<string:apitoken>/claimer/0-retreive-info", methods=["POST"])
async def claimer_0_retreive_info(apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    try:
        async with current_app.claimers_manager.start_claiming_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            type = "user" if addr.invitation_type == InvitationType.USER else "device"
            greeter_email = in_progress_ctx.greeter_human_handle.email

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

    return {"type": type, "greeter_email": greeter_email}, 200


@invite_bp.route("/invitations/<string:apitoken>/claimer/1-wait-peer-ready", methods=["POST"])
async def claimer_1_wait_peer_ready(apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    try:
        async with current_app.claimers_manager.retreive_claiming_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(in_progress_ctx, (UserClaimInitialCtx, DeviceClaimInitialCtx)):
                raise APIException(409, {"error": "invalid_state"})

            in_progress_ctx = await in_progress_ctx.do_wait_peer()
            lifetime_ctx.update_in_progress_ctx(in_progress_ctx)
            candidate_greeter_sas = [
                str(x) for x in in_progress_ctx.generate_greeter_sas_choices(size=4)
            ]

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

    return {"candidate_greeter_sas": candidate_greeter_sas}, 200


@invite_bp.route("/invitations/<string:apitoken>/claimer/2-check-trust", methods=["POST"])
async def claimer_2_check_trust(apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    async with check_data() as (data, bad_fields):
        greeter_sas = data.get("greeter_sas")
        if not isinstance(greeter_sas, str):
            bad_fields.add("greeter_sas")

    # TODO: handle exceptions
    async with current_app.claimers_manager.retreive_claiming_ctx(addr) as lifetime_ctx:
        in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
        if not isinstance(in_progress_ctx, (UserClaimInProgress1Ctx, DeviceClaimInProgress1Ctx)):
            raise APIException(409, {"error": "invalid_state"})

        if in_progress_ctx.greeter_sas != greeter_sas:
            raise APIException(400, {"error": "bad_greeter_sas"})

        in_progress_ctx = await in_progress_ctx.do_signify_trust()
        lifetime_ctx.update_in_progress_ctx(in_progress_ctx)
        claimer_sas = str(in_progress_ctx.claimer_sas)

    return {"claimer_sas": claimer_sas}, 200


@invite_bp.route("/invitations/<string:apitoken>/claimer/3-wait-peer-trust", methods=["POST"])
async def claimer_3_wait_peer_trust(apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    async with current_app.claimers_manager.retreive_claiming_ctx(addr) as lifetime_ctx:
        in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
        if not isinstance(in_progress_ctx, (UserClaimInProgress2Ctx, DeviceClaimInProgress2Ctx)):
            raise APIException(409, {"error": "invalid_state"})

        in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
        lifetime_ctx.update_in_progress_ctx(in_progress_ctx)

    return {}, 200


@invite_bp.route("/invitations/<string:apitoken>/claimer/4-finalize", methods=["POST"])
async def claimer_4_finalize(apitoken):
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    async with check_data() as (data, bad_fields):
        key = data.get("key")
        if not isinstance(key, str):
            bad_fields.add("key")
        # TODO: b64decode + reencode ?
        password = key

    async with current_app.claimers_manager.retreive_claiming_ctx(addr) as lifetime_ctx:
        in_progress_ctx = lifetime_ctx.get_in_progress_ctx()

        requested_device_label = platform.node() or "-unknown-"
        if isinstance(in_progress_ctx, UserClaimInProgress3Ctx):
            new_device = await in_progress_ctx.do_claim_user(
                requested_device_label=requested_device_label, requested_human_handle=None
            )

        elif isinstance(in_progress_ctx, DeviceClaimInProgress3Ctx):
            new_device = await in_progress_ctx.do_claim_device(
                requested_device_label=requested_device_label
            )

        else:
            raise APIException(409, {"error": "invalid_state"})

        # TODO: Handle exceptions
        save_device_with_password(
            config_dir=current_app.config["CORE_CONFIG_DIR"], device=new_device, password=password
        )
        lifetime_ctx.mark_as_terminated()

    return {}, 200
