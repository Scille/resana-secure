from __future__ import annotations

from typing import Any, cast

from quart import Blueprint

from parsec.core.logged_core import LoggedCore
from parsec.api.protocol import InvitationType, HumanHandle, UserProfile, InvitationToken, UserID
from parsec.api.data import SASCode
from parsec._parsec import save_device_with_password_in_config, InvitationDeletedReason, LocalDevice
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
    ShamirRecoveryGreetInProgress1Ctx,
    ShamirRecoveryGreetInProgress2Ctx,
    ShamirRecoveryGreetInProgress3Ctx,
    ShamirRecoveryClaimInProgress1Ctx,
    ShamirRecoveryClaimInProgress2Ctx,
    ShamirRecoveryClaimInProgress3Ctx,
    ShamirRecoveryClaimPreludeCtx,
    InviteNotFoundError,
)
from parsec.core.fs.storage.user_storage import user_storage_non_speculative_init
from parsec.core.backend_connection import backend_authenticated_cmds_factory
from parsec.core.recovery import generate_new_device_from_recovery

from ..utils import (
    authenticated,
    get_data,
    Parser,
    APIException,
    apitoken_to_addr,
    backend_errors_to_api_exceptions,
    get_default_device_label,
    email_validator,
)
from ..app import current_app

invite_bp = Blueprint("invite_api", __name__)


# Helper


async def _get_claimer_user_id_from_token(
    core: LoggedCore,
    token: InvitationToken,
) -> UserID:
    for invitation in await core.list_invitations():
        if invitation.token == token:
            return invitation.claimer_user_id
    raise InviteNotFoundError(token)


async def _delete_shamir_invitation(device: LocalDevice, token: InvitationToken) -> None:
    async with backend_authenticated_cmds_factory(
        addr=device.organization_addr,
        device_id=device.device_id,
        signing_key=device.signing_key,
    ) as cmds:
        await cmds.invite_delete(token=token, reason=InvitationDeletedReason.FINISHED)


### Greeter ###


@invite_bp.route("/invitations/<string:apitoken>/greeter/1-wait-peer-ready", methods=["POST"])
@authenticated
async def greeter_1_wait_peer_ready(core: LoggedCore, apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    with backend_errors_to_api_exceptions():
        async with current_app.greeters_managers[core.device.slug].start_ctx(
            device=core.device, addr=addr
        ) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            # `do_wait_peer` has been done in `start_greeting_ctx` so nothing more to do
    if not isinstance(
        in_progress_ctx,
        (UserGreetInProgress1Ctx, DeviceGreetInProgress1Ctx, ShamirRecoveryGreetInProgress1Ctx),
    ):
        raise APIException(409, {"error": "invalid_state"})
    type = addr.invitation_type.str.lower()
    assert type in ("user", "device", "shamir_recovery")
    return (
        {
            "type": type,
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
        async with current_app.greeters_managers[core.device.slug].retrieve_ctx(
            addr
        ) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx,
                (
                    UserGreetInProgress1Ctx,
                    DeviceGreetInProgress1Ctx,
                    ShamirRecoveryGreetInProgress1Ctx,
                ),
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
        async with current_app.greeters_managers[core.device.slug].retrieve_ctx(
            addr
        ) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx,
                (
                    UserGreetInProgress2Ctx,
                    DeviceGreetInProgress2Ctx,
                    ShamirRecoveryGreetInProgress2Ctx,
                ),
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
        async with current_app.greeters_managers[core.device.slug].retrieve_ctx(
            addr
        ) as lifetime_ctx:
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

            elif isinstance(in_progress_ctx, ShamirRecoveryGreetInProgress3Ctx):
                claimer_user_id = await _get_claimer_user_id_from_token(core, addr.token)
                share_data = await core.get_shamir_recovery_share_data(claimer_user_id)
                await in_progress_ctx.send_share_data(share_data)

            else:
                raise APIException(409, {"error": "invalid_state"})

            lifetime_ctx.mark_as_terminated()

    return {}, 200


### Claimer ###


def _prelude_to_response(prelude: ShamirRecoveryClaimPreludeCtx) -> dict[str, Any]:
    threshold = prelude.threshold
    enough_shares = prelude.has_enough_shares()
    recipients = []
    for recipient in prelude.recipients:
        assert recipient.human_handle is not None
        email = recipient.human_handle.email
        weight = recipient.shares
        retrieved = recipient.user_id in prelude.recovered
        recipients.append({"email": email, "weight": weight, "retrieved": retrieved})
    recipients.sort(key=lambda x: cast(str, x["email"]))
    return {
        "type": "shamir_recovery",
        "threshold": threshold,
        "enough_shares": enough_shares,
        "recipients": recipients,
    }


# Note: claimer routes are not authenticated


@invite_bp.route("/invitations/<string:apitoken>/claimer/0-retreive-info", methods=["POST"])
async def claimer_0_retrieve_info_with_typo(apitoken: str) -> tuple[dict[str, Any], int]:
    return await claimer_0_retrieve_info(apitoken)


@invite_bp.route("/invitations/<string:apitoken>/claimer/0-retrieve-info", methods=["POST"])
async def claimer_0_retrieve_info(apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    with backend_errors_to_api_exceptions():

        async with current_app.claimers_manager.start_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()

            # Get invitation type
            type = addr.invitation_type.str.lower()
            assert type in ("user", "device", "shamir_recovery")

            # User/Device
            if isinstance(in_progress_ctx, (UserClaimInitialCtx, DeviceClaimInitialCtx)):
                assert in_progress_ctx.greeter_human_handle is not None
                greeter_email = in_progress_ctx.greeter_human_handle.email
                return {
                    "type": type,
                    "greeter_email": greeter_email,
                }, 200

            # Shamir Recovery
            elif isinstance(in_progress_ctx, ShamirRecoveryClaimPreludeCtx):
                response = _prelude_to_response(in_progress_ctx)
                return response, 200

            # Invalid state
            else:
                raise APIException(409, {"error": "invalid_state"})


@invite_bp.route("/invitations/<string:apitoken>/claimer/1-wait-peer-ready", methods=["POST"])
async def claimer_1_wait_peer_ready(apitoken: str) -> tuple[dict[str, Any], int]:
    try:
        addr = apitoken_to_addr(apitoken)
    except ValueError:
        raise APIException(404, {"error": "unknown_token"})

    data = await get_data(allow_empty=True)
    parser = Parser()
    parser.add_argument("greeter_email", type=str, validator=email_validator, required=False)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    with backend_errors_to_api_exceptions():
        async with current_app.claimers_manager.retrieve_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx,
                (UserClaimInitialCtx, DeviceClaimInitialCtx, ShamirRecoveryClaimPreludeCtx),
            ):
                raise APIException(409, {"error": "invalid_state"})

            if isinstance(in_progress_ctx, ShamirRecoveryClaimPreludeCtx):
                greeter_email = cast("str | None", args["greeter_email"])
                if greeter_email is None:
                    raise APIException.from_bad_fields(["greeter_email"])
                for recipient in in_progress_ctx.recipients:
                    assert recipient.human_handle is not None
                    if recipient.human_handle.email == greeter_email:
                        break
                else:
                    return {"error": "email_not_in_recipients"}, 400
                if recipient.user_id in in_progress_ctx.recovered:
                    return {"error": "recipient_already_recovered"}, 400
                in_progress_ctx = in_progress_ctx.get_initial_ctx(recipient)

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
        async with current_app.claimers_manager.retrieve_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx,
                (
                    UserClaimInProgress1Ctx,
                    DeviceClaimInProgress1Ctx,
                    ShamirRecoveryClaimInProgress1Ctx,
                ),
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
        async with current_app.claimers_manager.retrieve_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()
            if not isinstance(
                in_progress_ctx,
                (
                    UserClaimInProgress2Ctx,
                    DeviceClaimInProgress2Ctx,
                    ShamirRecoveryClaimInProgress2Ctx,
                ),
            ):
                raise APIException(409, {"error": "invalid_state"})

            in_progress_ctx = await in_progress_ctx.do_wait_peer_trust()
            response: dict[str, Any]

            # In the case of shamir recovery, recover the share right away
            # This way, we can tell the client to either:
            # - get back to step 0 to get more shares
            # - continue to step 4 to finalize
            if isinstance(in_progress_ctx, ShamirRecoveryClaimInProgress3Ctx):
                enough_shares = await in_progress_ctx.do_recover_share()
                in_progress_ctx = in_progress_ctx.prelude
                response = {"enough_shares": enough_shares}
            else:
                response = {}

            lifetime_ctx.update_in_progress_ctx(in_progress_ctx)

    return response, 200


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
        async with current_app.claimers_manager.retrieve_ctx(addr) as lifetime_ctx:
            in_progress_ctx = lifetime_ctx.get_in_progress_ctx()

            requested_device_label = get_default_device_label()
            if isinstance(in_progress_ctx, UserClaimInProgress3Ctx):
                new_device = await in_progress_ctx.do_claim_user(
                    requested_device_label=requested_device_label, requested_human_handle=None
                )

            elif isinstance(in_progress_ctx, DeviceClaimInProgress3Ctx):
                new_device = await in_progress_ctx.do_claim_device(
                    requested_device_label=requested_device_label
                )

            elif isinstance(in_progress_ctx, ShamirRecoveryClaimPreludeCtx):
                if not in_progress_ctx.has_enough_shares():
                    return {"error": "not-enough-shares"}, 400
                recovery_device = await in_progress_ctx.retrieve_recovery_device()
                new_device = await generate_new_device_from_recovery(
                    recovery_device, requested_device_label
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

            # In the case of a shamir recovery, it is the claimer that deletes the invitation
            if isinstance(in_progress_ctx, ShamirRecoveryClaimPreludeCtx):
                await _delete_shamir_invitation(new_device, addr.token)

            lifetime_ctx.mark_as_terminated()

    return {}, 200
