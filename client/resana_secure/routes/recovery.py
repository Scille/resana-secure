import os
from quart import Blueprint, current_app
from base64 import b64encode, b64decode
import tempfile
from pathlib import Path

from parsec.core.local_device import (
    save_recovery_device,
    get_recovery_device_file_name,
    load_recovery_device,
    save_device_with_password_in_config,
    LocalDeviceCryptoError,
)

from ..utils import APIException, authenticated, check_data


recovery_bp = Blueprint("recovery_api", __name__)


@recovery_bp.route("/recovery/export", methods=["POST"])
@authenticated
async def export_device(core):
    async with check_data() as (data, bad_fields):
        bad_fields |= data.keys()  # No fields allowed

    fp, path = tempfile.mkstemp(suffix=".psrk")
    # Closing the open file returned by mkstemp
    os.close(fp)
    path = Path(path)
    try:
        passphrase = await save_recovery_device(path, core.device, True)
        raw = path.read_bytes()
    finally:
        path.unlink()

    file_name = get_recovery_device_file_name(core.device).replace("parsec-", "resana-secure-", 1)

    return (
        {
            "file_content": b64encode(raw).decode(),
            "file_name": file_name,
            "passphrase": passphrase,
        },
        200,
    )


@recovery_bp.route("/recovery/import", methods=["POST"])
async def import_device():
    async with check_data() as (data, bad_fields):
        file_content = data.get("recovery_device_file_content")
        if not isinstance(file_content, str):
            bad_fields.add("recovery_device_file_content")
        try:
            file_content = b64decode(file_content)
        except ValueError:
            bad_fields.add("recovery_device_file_content")

        passphrase = data.get("recovery_device_passphrase")
        if not isinstance(passphrase, str):
            bad_fields.add("recovery_device_passphrase")

        # Note password is supposed to be base64 data, however we need a string
        # to save the device. Hence we "cheat" by using the content without
        # deserializing back from base64.
        password = data.get("new_device_key")
        if not isinstance(password, str):
            bad_fields.add("new_device_key")

    fp, path = tempfile.mkstemp(suffix=".psrk")
    # Closing the open file returned by mkstemp
    os.close(fp)
    path = Path(path)
    try:
        path.write_bytes(file_content)
        try:
            new_device = await load_recovery_device(path, passphrase)
        except LocalDeviceCryptoError:
            raise APIException(400, {"error": "invalid_passphrase"})
    finally:
        path.unlink()

    save_device_with_password_in_config(
        config_dir=current_app.core_config.config_dir,
        device=new_device,
        password=password,
    )

    return {}, 200
