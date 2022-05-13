from quart import Blueprint

from parsec.core.types import LocalDevice
from parsec.api.protocol import DeviceLabel
from resana_secure.utils import authenticated

recovery_bp = Blueprint("recovery_api", __name__)

@recovery_bp.route("/recovery/export_device", methods=["POST"])
async def export_device(core):
    await core.export_recovery()
    return ("": base64(txt))

@authenticated
@recovery_bp.route("/recovery/import_device", methods=["GET"])
async def import_device(core, device):
    await core.import_recovery(device)
    return ("": base64(txt))
