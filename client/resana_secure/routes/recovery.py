from __future__ import annotations

from typing import Any

import os
import tempfile
from pathlib import Path
from quart import Blueprint
from base64 import b64encode, b64decode

from parsec.core.logged_core import LoggedCore
from parsec._parsec import (
    save_recovery_device,
    load_recovery_device,
    save_device_with_password_in_config,
    LocalDeviceError,
)
from parsec.core.recovery import generate_recovery_device, generate_new_device_from_recovery
from parsec.core.local_device import (
    get_recovery_device_file_name,
)

from ..utils import APIException, authenticated, get_data, Parser, get_default_device_label
from ..app import current_app

recovery_bp = Blueprint("recovery_api", __name__)


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
        # TODO: change it for LocalDeviceCryptoError once https://github.com/Scille/parsec-cloud/issues/4048 is done
        except LocalDeviceError:
            raise APIException(400, {"error": "invalid_passphrase"})
    finally:
        path.unlink()
    save_device_with_password_in_config(
        config_dir=current_app.resana_config.core_config.config_dir,
        device=new_device,
        password=args["password"],
    )

    return {}, 200


@recovery_bp.route("/recovery/rename", methods=["POST"])
async def rename_device() -> tuple[dict[str, Any], int]:
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
        # TODO: change it for LocalDeviceCryptoError once https://github.com/Scille/parsec-cloud/issues/4048 is done
        except LocalDeviceError:
            raise APIException(400, {"error": "invalid_passphrase"})
    finally:
        path.unlink()
    
    # This will rename the create device from device.keys to device_backup.txt

    folder_path = str(current_app.resana_config.core_config.config_dir) + "/devices"
    file_list = [file.name for file in Path(folder_path).iterdir() if file.is_file()]
    old_name = folder_path + "/" + file_list[0]
    new_name = folder_path + "/" + file_list[0].replace(".keys","_backup.txt")
    os.rename(old_name,new_name)
    
    save_device_with_password_in_config(
        config_dir=current_app.resana_config.core_config.config_dir,
        device=new_device,
        password=args["password"],
    )
    
    return {}, 200