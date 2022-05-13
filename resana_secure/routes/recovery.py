from quart import Blueprint, current_app
from base64 import b64encode, b64decode
import tempfile
from pathlib import Path

from parsec.core.local_device import save_recovery_device, get_recovery_device_file_name, load_recovery_device, save_device_with_password

from ..utils import authenticated, check_data


recovery_bp = Blueprint("recovery_api", __name__)


@recovery_bp.route("/recovery/export_device", methods=["POST"])
async def export_device(core):
    async with check_data() as (data, bad_fields):
        bad_fields |= data.keys()  # No fields allowed

    with tempfile.NamedTemporaryFile(suffix=".psrk") as fp:
        passphrase = await save_recovery_device(Path(fp.name), core.local_device, True)
        fp.seek(0)
        raw = fp.read()

    file_name = get_recovery_device_file_name(core.local_device).replace("parsec-", "resana-secure-", 1)

    return {
        "file_content": b64encode(raw),
        "file_name": file_name,
        "passphrase": passphrase,
    }, 200


@authenticated
@recovery_bp.route("/recovery/import_device", methods=["GET"])
async def import_device(core, device):
    async with check_data() as (data, bad_fields):
        file_content = data.get("recovery_device_file_content")
        if not isinstance(file_content, str):
            bad_fields.add("recovery_device_file_content")
        try:
            file_content = b64decode(recovery_device_file_content)
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

    with tempfile.NamedTemporaryFile(suffix=".psrk") as fp:
        path = Path(fp.name)
        path.write_bytes(file_content)
        new_device = await load_recovery_device(path, passphrase)

    save_device_with_password(
        config_dir=current_app.config["CORE_CONFIG"].config_dir,
        device=new_device,
        password=password,
    )

    return {}, 200
