import io
from typing import Optional
import structlog
from quart import Blueprint, request, current_app
from werkzeug.exceptions import RequestEntityTooLarge

from parsec.sequester_crypto import sequester_service_decrypt
from parsec.api.data import FileManifest
from parsec.api.data.manifest import manifest_unverified_load
from parsec.api.protocol import OrganizationID

from .utils import APIException
from .antivirus import check_for_malwares, AntivirusError


logger = structlog.get_logger()


bp = Blueprint("api", __name__)


class ManifestError(Exception):
    pass


class ReassemblyError(Exception):
    pass


async def load_manifest(vlob: bytes) -> Optional[FileManifest]:
    try:
        decrypted_vlob = sequester_service_decrypt(
            current_app.config["APP_CONFIG"].authority_private_key, vlob
        )
        # Connector does not care if data is signed or not
        manifest = manifest_unverified_load(decrypted_vlob)
        if not isinstance(manifest, FileManifest):
            return None
        return manifest
    except Exception as exc:
        raise ManifestError() from exc


async def reassemble_file(manifest: FileManifest, organization_id: OrganizationID) -> bytes:
    out = io.BytesIO()
    out.truncate(manifest.size)
    blockstore = current_app.config["BLOCKSTORE"]

    for block in manifest.blocks:
        try:
            block_data = await blockstore.read(organization_id=organization_id, block_id=block.id)
        except Exception as exc:
            raise ReassemblyError(f"Failed to download a block: {exc}") from exc

        try:
            cleardata = block.key.decrypt(block_data)
        except Exception as exc:
            raise ReassemblyError(f"Failed to decrypt a block: {exc}") from exc

        try:
            if out.tell() != block.offset:
                out.seek(block.offset)
            if block.size != len(cleardata):
                out.write(cleardata[block.size])
            else:
                out.write(cleardata)
        except OSError as exc:
            raise ReassemblyError(f"Failed to reassemble the file: {exc}") from exc

    return out


@bp.route("/submit/<string:organization_id>", methods=["POST"])
async def submit(organization_id):
    try:
        organization_id = OrganizationID(organization_id)
        vlob = await request.get_data(cache=False)
    except RequestEntityTooLarge as exc:
        # Request body is too large
        logger.warning("Request too large", exc_info=exc)
        return {}, 413
    except Exception as exc:
        logger.warning("Failed to parse the arguments", exc_info=exc)
        raise APIException(400, {"error": f"Failed to parse arguments: {exc}"})
    try:
        # Decrypt and deserialize the manifest
        manifest = await load_manifest(vlob)
        if not manifest:
            # Not a file manifest
            return {"info": "Not a file manifest"}, 200

        # Download the blocks and recombine into a file
        content_stream = await reassemble_file(manifest, organization_id)

        # Send to the antivirus
        malwares = await check_for_malwares(content_stream, current_app.config["APP_CONFIG"])
        if not malwares:
            return {}, 200
        else:
            logger.warning(
                "Malwares detected",
                organizationd_id=organization_id,
                vlob_id=manifest.id,
                vlob_version=manifest.version,
                malwares=malwares,
            )
            return {
                "error": f"Malicious file detected by anti-virus scan: {', '.join(malwares)}"
            }, 400
    except ManifestError as exc:
        logger.warning("Failed to deserialize the manifest", exc_info=exc)
        raise APIException(400, {"error": f"Vlob decryption failed: {exc}"})
    except ReassemblyError as exc:
        logger.warning("Failed to reassemble the file", exc_info=exc)
        raise APIException(400, {"error": f"The file cannot be reassembled: {exc}"})
    except AntivirusError as exc:
        logger.warning("Antivirus analysis failed", exc_info=exc)
        raise APIException(400, {"error": f"Antivirus analysis failed: {exc}"})
