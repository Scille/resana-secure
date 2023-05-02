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
from parsec.core.local_device import (
    get_recovery_device_file_name,
)

from ..utils import APIException, authenticated, get_data, Parser
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
            new_device = await load_recovery_device(path, args["passphrase"])
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
