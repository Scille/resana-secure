from __future__ import annotations

import os
import tempfile
from base64 import b64decode, b64encode
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from quart import Blueprint

from parsec._parsec import (
    LocalDeviceCryptoError,
    ShamirRecoveryBriefCertificate,
    UserCertificate,
    load_recovery_device,
    save_device_with_password_in_config,
    save_recovery_device,
)
from parsec.core.local_device import (
    get_recovery_device_file_name,
)
from parsec.core.logged_core import LoggedCore
from parsec.core.recovery import generate_new_device_from_recovery, generate_recovery_device
from parsec.core.shamir import (
    ShamirRecoveryAlreadySetError,
    ShamirRecoveryError,
    ShamirRecoveryInvalidDataError,
    ShamirRecoveryNotSetError,
    create_shamir_recovery_device,
    get_shamir_recovery_others_list,
    get_shamir_recovery_self_info,
    remove_shamir_recovery_device,
)

from ..app import current_app
from ..utils import (
    APIException,
    BadFields,
    Parser,
    authenticated,
    email_validator,
    get_data,
    get_default_device_label,
    get_user_id_from_email,
    rename_old_user_key_file,
)

recovery_bp = Blueprint("recovery_api", __name__)


@dataclass
class ShamirRecoveryRecipient:
    email: str
    weight: int


async def brief_certificate_to_recipients(
    core: LoggedCore, brief_certificate: ShamirRecoveryBriefCertificate
) -> list[ShamirRecoveryRecipient]:
    recipients: list[ShamirRecoveryRecipient] = []
    for user_id, weight in brief_certificate.per_recipient_shares.items():
        user_certificate, _ = await core._remote_devices_manager.get_user(user_id)
        assert user_certificate.human_handle is not None  # All recipients are humans
        recipients.append(ShamirRecoveryRecipient(user_certificate.human_handle.email, weight))

    recipients.sort(key=lambda x: x.email)
    return recipients


@recovery_bp.route("/recovery/export", methods=["POST"])
@authenticated
async def export_device(core: LoggedCore) -> tuple[dict[str, Any], int]:
    data = await get_data()
    if data.keys():
        raise APIException.from_bad_fields(list(data.keys()))

    fp, raw_path = tempfile.mkstemp(suffix=".psrk")
    # Closing the open file returned by mkstemp
    os.close(fp)
    path = Path(raw_path)
    try:
        recovery_device = await generate_recovery_device(core.device)
        passphrase = await save_recovery_device(path, recovery_device, True)
        raw = path.read_bytes()
    finally:
        path.unlink()

    # base file_name format : parsec-recovery-<id_org>-<user-label="-unknown-">.psrk
    # target file_name : resana-secure-recovery-<id_org>.psrk
    file_name = (
        get_recovery_device_file_name(core.device)
        .replace("parsec-", "resana-secure-", 1)
        .replace("--unknown-", "")
    )

    return (
        {
            "file_content": b64encode(raw).decode(),
            "file_name": file_name,
            "passphrase": passphrase,
        },
        200,
    )


@recovery_bp.route("/recovery/import", methods=["POST"])
async def import_device() -> tuple[dict[str, Any], int]:
    data = await get_data()
    parser = Parser()
    parser.add_argument(
        "recovery_device_file_content",
        converter=b64decode,
        new_name="file_content",
        required=True,
    )
    parser.add_argument(
        "recovery_device_passphrase", type=str, new_name="passphrase", required=True
    )
    parser.add_argument("new_device_key", type=str, new_name="password", required=True)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    fp, raw_path = tempfile.mkstemp(suffix=".psrk")
    # Closing the open file returned by mkstemp
    os.close(fp)
    path = Path(raw_path)
    try:
        path.write_bytes(args["file_content"])
        try:
            recovery_device = await load_recovery_device(path, args["passphrase"])
            new_device = await generate_new_device_from_recovery(
                recovery_device, get_default_device_label()
            )
        except LocalDeviceCryptoError:
            raise APIException(400, {"error": "invalid_passphrase"})
    finally:
        path.unlink()

    key_file_path = save_device_with_password_in_config(
        config_dir=current_app.resana_config.core_config.config_dir,
        device=new_device,
        password=args["password"],
    )

    # rename old key files
    rename_old_user_key_file(
        new_device.human_handle.email if new_device.human_handle else "",
        new_device.organization_id,
        Path(key_file_path),
    )

    return {}, 200


# Shared recovery


@recovery_bp.route("/recovery/shamir/setup", methods=["POST"])
@authenticated
async def shamir_recovery_setup(core: LoggedCore) -> tuple[dict[str, Any], int]:
    data = await get_data()

    subparser = Parser()
    subparser.add_argument("email", type=str, required=True, validator=email_validator)
    subparser.add_argument("weight", type=int, default=1)

    def converter(arg: list[dict[str, str | int]]) -> list[ShamirRecoveryRecipient]:
        result = []
        indexed_bad_fields = {}
        for i, item in enumerate(arg):
            args, bad_fields = subparser.parse_args(item)
            if bad_fields:
                indexed_bad_fields[i] = bad_fields
                continue
            recipient = ShamirRecoveryRecipient(args["email"], args["weight"])
            result.append(recipient)
        if indexed_bad_fields:
            raise BadFields.from_indexed_bad_fields(indexed_bad_fields)
        return result

    parser = Parser()
    parser.add_argument(
        "threshold",
        type=int,
        required=True,
    )
    parser.add_argument("recipients", type=list, required=True, converter=converter)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)
    threshold = cast(int, args["threshold"])
    users = cast(list[ShamirRecoveryRecipient], args["recipients"])

    # Extract certificates
    weights: list[int] = []
    certificates: list[UserCertificate] = []
    users_not_found: list[str] = []
    for user in users:
        user_id = await get_user_id_from_email(core, user.email, omit_revoked=True)
        if user_id is None:
            users_not_found.append(user.email)
            continue
        certificate, _ = await core._remote_devices_manager.get_user(user_id)
        certificates.append(certificate)
        weights.append(user.weight)
    if users_not_found:
        return {"error": "users_not_found", "emails": users_not_found}, 400

    # Create shared recovery device
    try:
        await create_shamir_recovery_device(
            core,
            certificates,
            threshold,
            weights,
        )
    except ShamirRecoveryAlreadySetError:
        return {"error": "already_set"}, 400
    except ShamirRecoveryInvalidDataError:
        return {"error": "invalid_configuration"}, 400
    except ShamirRecoveryError as exc:
        return {"error": "unexpected_error", "detail": str(exc)}, 400

    return {}, 200


@recovery_bp.route("/recovery/shamir/setup", methods=["DELETE"])
@authenticated
async def remove_shamir_recovery_setup(core: LoggedCore) -> tuple[dict[str, Any], int]:
    data = await get_data(allow_empty=True)
    parser = Parser()
    _, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)
    # Remove shared recovery device
    try:
        await remove_shamir_recovery_device(core)
    except ShamirRecoveryError as exc:
        return {"error": "unexpected_error", "detail": str(exc)}, 400

    return {}, 200


@recovery_bp.route("/recovery/shamir/setup", methods=["GET"])
@authenticated
async def get_shamir_recovery_setup(core: LoggedCore) -> tuple[dict[str, Any], int]:
    data = await get_data(allow_empty=True)
    parser = Parser()
    _, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    try:
        device_certificate, brief_certificate = await get_shamir_recovery_self_info(core)
    except ShamirRecoveryNotSetError:
        return {"error": "not_setup"}, 404
    except ShamirRecoveryError as exc:
        return {"error": "unexpected_error", "detail": str(exc)}, 400

    device_label = (
        device_certificate.device_label.str if device_certificate.device_label is not None else None
    )
    recipients = await brief_certificate_to_recipients(core, brief_certificate)
    response = {
        "device_label": device_label,
        "threshold": brief_certificate.threshold,
        "recipients": [asdict(recipient) for recipient in recipients],
    }

    return response, 200


@recovery_bp.route("/recovery/shamir/setup/others", methods=["GET"])
@authenticated
async def list_shamir_recovery_for_other_users(core: LoggedCore) -> tuple[dict[str, Any], int]:
    data = await get_data(allow_empty=True)
    parser = Parser()
    _, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    try:
        result = await get_shamir_recovery_others_list(core)
    except ShamirRecoveryError as exc:
        return {"error": "unexpected_error", "detail": str(exc)}, 400

    items = []
    for (
        author_certificate,
        user_certificate,
        brief_certificate,
        maybe_share_data,
    ) in result:
        weight = 0 if maybe_share_data is None else len(maybe_share_data.weighted_share)
        device_label = (
            author_certificate.device_label.str
            if author_certificate.device_label is not None
            else None
        )
        assert user_certificate.human_handle is not None  # All recipients are humans
        recipients = await brief_certificate_to_recipients(core, brief_certificate)
        item = {
            "email": user_certificate.human_handle.email,
            "label": user_certificate.human_handle.label,
            "device_label": device_label,
            "threshold": brief_certificate.threshold,
            "recipients": [asdict(recipient) for recipient in recipients],
            "my_weight": weight,
        }
        items.append(item)

    response = {"setups": items}
    return response, 200
