from __future__ import annotations

from typing import Any

import platform
from quart import Blueprint

from parsec.core.logged_core import LoggedCore
from parsec.api.protocol import InvitationType, HumanHandle, DeviceLabel, UserProfile
from parsec.api.data import SASCode
from parsec._parsec import save_device_with_password_in_config
from parsec.core.invite import (
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
    UserGreetInProgress4Ctx,
    DeviceGreetInProgress4Ctx,
)
from parsec.core.fs.storage.user_storage import user_storage_non_speculative_init

from ..utils import (
    authenticated,
    get_data,
    Parser,
    APIException,
    apitoken_to_addr,
    backend_errors_to_api_exceptions,
)
from ..app import current_app


invite_bp = Blueprint("invite_api", __name__)


### Greeter ###


@invite_bp.route("/invitations/<string:apitoken>/greeter/1-wait-peer-ready", methods=["POST"])
@authenticated
async def greeter_1_wait_peer_ready(core: LoggedCore, apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    with backend_errors_to_api_exceptions():
        async with current_app.greeters_manager.start_ctx(
            device=core.device, addr=addr
        ) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            # `do_wait_peer` has been done in `start_greeting_ctx` so nothing more to do
    if not isinstance(in_progress_ctx, (UserGreetInProgress1Ctx, DeviceGreetInProgress1Ctx)):
        raise APIException(409, {"error": "invalid_state"})
    return (
        {
            "type": "user" if addr.invitation_type == InvitationType.USER else "device",
            "greeter_sas": in_progress_ctx.greeter_sas.str,
        },
        200,
    )


@invite_bp.route("/invitations/<string:apitoken>/greeter/2-wait-peer-trust", methods=["POST"])
@authenticated
async def greeter_2_wait_peer_trust(core: LoggedCore, apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    with backend_errors_to_api_exceptions():
        async with current_app.greeters_manager.retreive_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx, (UserGreetInProgress1Ctx, DeviceGreetInProgress1Ctx)
            ):
                raise APIException(409, {"error": "invalid_state"})

            in_progress_2_ctx = await in_progress_ctx.do_wait_peer_trust()
            lifetime_ctx.update_in_progress_ctx(in_progress_2_ctx)

            candidate_claimer_sas = [
                x.str for x in in_progress_2_ctx.generate_claimer_sas_choices(size=4)
            ]

    return {"candidate_claimer_sas": candidate_claimer_sas}, 200


@invite_bp.route("/invitations/<string:apitoken>/greeter/3-check-trust", methods=["POST"])
@authenticated
async def greeter_3_check_trust(core: LoggedCore, apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    data = await get_data()
    parser = Parser()
    parser.add_argument("claimer_sas", converter=SASCode, required=True)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    with backend_errors_to_api_exceptions():
        async with current_app.greeters_manager.retreive_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx, (UserGreetInProgress2Ctx, DeviceGreetInProgress2Ctx)
            ):
                raise APIException(409, {"error": "invalid_state"})

            if in_progress_ctx.claimer_sas != args["claimer_sas"]:
                raise APIException(400, {"error": "bad_claimer_sas"})

            in_progress_ctx = await in_progress_ctx.do_signify_trust()
            lifetime_ctx.update_in_progress_ctx(in_progress_ctx)

    return {}, 200


@invite_bp.route("/invitations/<string:apitoken>/greeter/4-finalize", methods=["POST"])
@authenticated
async def greeter_4_finalize(core: LoggedCore, apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    if addr.invitation_type == InvitationType.USER:
        data = await get_data()
        parser = Parser()
        parser.add_argument("claimer_email", type=str, required=True)
        parser.add_argument("granted_profile", type=str, required=True)
        args, bad_fields = parser.parse_args(data)
        if bad_fields:
            raise APIException.from_bad_fields(bad_fields)

        if args["granted_profile"] not in ("ADMIN", "STANDARD"):
            raise APIException.from_bad_fields(["granted_profile"])
        granted_profile = (
            UserProfile.ADMIN if args["granted_profile"] == "ADMIN" else UserProfile.STANDARD
        )
    else:
        granted_profile = None

    with backend_errors_to_api_exceptions():
        async with current_app.greeters_manager.retreive_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            in_progress_4_ctx: UserGreetInProgress4Ctx | DeviceGreetInProgress4Ctx

            if isinstance(in_progress_ctx, UserGreetInProgress3Ctx):
                assert isinstance(granted_profile, UserProfile)
                in_progress_4_ctx = await in_progress_ctx.do_get_claim_requests()
                await in_progress_4_ctx.do_create_new_user(
                    author=core.device,
                    device_label=in_progress_4_ctx.requested_device_label,
                    human_handle=HumanHandle(email=args["claimer_email"], label="-unknown-"),
                    profile=granted_profile,
                )

            elif isinstance(in_progress_ctx, DeviceGreetInProgress3Ctx):
                in_progress_4_ctx = await in_progress_ctx.do_get_claim_requests()
                await in_progress_4_ctx.do_create_new_device(
                    author=core.device, device_label=in_progress_4_ctx.requested_device_label
                )

            else:
                raise APIException(409, {"error": "invalid_state"})

            lifetime_ctx.mark_as_terminated()

    return {}, 200


### Claimer ###


# Note claimer routes are not authentication


@invite_bp.route("/invitations/<string:apitoken>/claimer/0-retreive-info", methods=["POST"])
async def claimer_0_retreive_info(apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    with backend_errors_to_api_exceptions():
        async with current_app.claimers_manager.start_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            type = "user" if addr.invitation_type == InvitationType.USER else "device"
            if not isinstance(in_progress_ctx, (UserClaimInitialCtx, DeviceClaimInitialCtx)):
                raise APIException(409, {"error": "invalid_state"})
            assert in_progress_ctx.greeter_human_handle is not None
            greeter_email = in_progress_ctx.greeter_human_handle.email

    return {"type": type, "greeter_email": greeter_email}, 200


@invite_bp.route("/invitations/<string:apitoken>/claimer/1-wait-peer-ready", methods=["POST"])
async def claimer_1_wait_peer_ready(apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    with backend_errors_to_api_exceptions():
        async with current_app.claimers_manager.retreive_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(in_progress_ctx, (UserClaimInitialCtx, DeviceClaimInitialCtx)):
                raise APIException(409, {"error": "invalid_state"})

            in_progress_1_ctx = await in_progress_ctx.do_wait_peer()
            lifetime_ctx.update_in_progress_ctx(in_progress_1_ctx)
            candidate_greeter_sas = [
                x.str for x in in_progress_1_ctx.generate_greeter_sas_choices(size=4)
            ]

    return {"candidate_greeter_sas": candidate_greeter_sas}, 200


@invite_bp.route("/invitations/<string:apitoken>/claimer/2-check-trust", methods=["POST"])
async def claimer_2_check_trust(apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    data = await get_data()
    parser = Parser()
    parser.add_argument("greeter_sas", converter=SASCode, required=True)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    with backend_errors_to_api_exceptions():
        async with current_app.claimers_manager.retreive_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx, (UserClaimInProgress1Ctx, DeviceClaimInProgress1Ctx)
            ):
                raise APIException(409, {"error": "invalid_state"})

            if in_progress_ctx.greeter_sas != args["greeter_sas"]:
                raise APIException(400, {"error": "bad_greeter_sas"})

            in_progress_2_ctx = await in_progress_ctx.do_signify_trust()
            lifetime_ctx.update_in_progress_ctx(in_progress_2_ctx)
            claimer_sas = in_progress_2_ctx.claimer_sas

    return {"claimer_sas": claimer_sas.str}, 200


@invite_bp.route("/invitations/<string:apitoken>/claimer/3-wait-peer-trust", methods=["POST"])
async def claimer_3_wait_peer_trust(apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    with backend_errors_to_api_exceptions():
        async with current_app.claimers_manager.retreive_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx, (UserClaimInProgress2Ctx, DeviceClaimInProgress2Ctx)
            ):
                raise APIException(409, {"error": "invalid_state"})

            in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
            lifetime_ctx.update_in_progress_ctx(in_progress_ctx)

    return {}, 200


@invite_bp.route("/invitations/<string:apitoken>/claimer/4-finalize", methods=["POST"])
async def claimer_4_finalize(apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    data = await get_data()
    parser = Parser()
    # Note password is supposed to be base64 data, however we need a string
    # to save the device. Hence we "cheat" by using the content without
    # deserializing back from base64.
    parser.add_argument("key", type=str, new_name="password", required=True)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    with backend_errors_to_api_exceptions():
        async with current_app.claimers_manager.retreive_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()

            try:
                requested_device_label = DeviceLabel(platform.node() or "-unknown-")
            except ValueError:
                requested_device_label = DeviceLabel("-unknown-")
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

            # Claiming a user means we are it first device, hence we know there
            # is no existing user manifest (hence our placeholder is non-speculative)
            if addr.invitation_type == InvitationType.USER:
                await user_storage_non_speculative_init(
                    data_base_dir=current_app.resana_config.core_config.data_base_dir,
                    device=new_device,
                )

            save_device_with_password_in_config(
                config_dir=current_app.resana_config.core_config.config_dir,
                device=new_device,
                password=args["password"],
            )
            lifetime_ctx.mark_as_terminated()

    return {}, 200
