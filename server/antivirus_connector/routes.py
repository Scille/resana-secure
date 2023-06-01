from __future__ import annotations

from typing import Optional
from io import BytesIO
import structlog
import oscrypto
from quart import Blueprint, request, current_app
from werkzeug.exceptions import RequestEntityTooLarge

# from parsec.sequester_crypto import sequester_service_decrypt
from parsec._parsec import SequesterPrivateKeyDer
from parsec.api.data import FileManifest
from parsec.api.data.manifest import manifest_unverified_load
from parsec.api.protocol import SequesterServiceID, OrganizationID

from .antivirus import check_for_malwares, AntivirusError
from .config import AppConfig


logger = structlog.get_logger()


bp = Blueprint("api", __name__)


class ManifestError(Exception):
    pass


class ReassemblyError(Exception):
    pass


async def load_manifest(key: oscrypto.asymmetric.PrivateKey, vlob: bytes) -> Optional[FileManifest]:
    try:
        # decrypted_vlob = sequester_service_decrypt(key, vlob)
        decrypted_vlob = SequesterPrivateKeyDer.decrypt(vlob)
        # Connector does not care if data is signed or not
        manifest = manifest_unverified_load(decrypted_vlob)
        if not isinstance(manifest, FileManifest):
            return None
        return manifest
    except Exception as exc:
        raise ManifestError() from exc


async def reassemble_file(manifest: FileManifest, organization_id: OrganizationID) -> BytesIO:
    out = BytesIO()
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
                out.write(cleardata[: block.size])
            else:
                out.write(cleardata)
        except OSError as exc:
            raise ReassemblyError(f"Failed to reassemble the file: {exc}") from exc

    return out


@bp.route("/submit", methods=["POST"])
async def submit() -> tuple[dict[str, str], int]:
    # 400 status should only used when detecting a malicious file, other 4xx/5xx should
    # be used in case bad arguments or temporary failure. This is because Parsec consider
    # 400 status as an indication to not save the vlob and other status as a "retry later"
    # indication
    try:
        organization_id = OrganizationID(request.args.get("organization_id", ""))
        service_id = SequesterServiceID.from_hex(request.args.get("service_id", ""))
        vlob = await request.get_data(cache=False, as_text=False, parse_form_data=False)
    except RequestEntityTooLarge as exc:
        # Request body is too large
        logger.warning("Request too large", exc_info=exc)
        return {}, 413

    except Exception as exc:
        logger.warning("Failed to parse the arguments", exc_info=exc)
        return {"error": f"Failed to parse arguments: {exc}"}, 422

    config: AppConfig = current_app.config["APP_CONFIG"]
    try:
        key = config.sequester_services_decryption_key[service_id]
    except KeyError as exc:
        logger.warning(
            "No key available for provided sequester service",
            service_id=service_id,
            organization_id=organization_id.str,
            exc_info=exc,
        )
        return {"reason": "No key available for provided sequester service"}, 400

    try:
        # Decrypt and deserialize the manifest
        manifest = await load_manifest(key, vlob)
        if not manifest or manifest.size == 0:
            # Not a file manifest or empty
            return {}, 200

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
                "reason": f"Malicious file detected by anti-virus scan: {', '.join(malwares)}"
            }, 400

    except ManifestError as exc:
        logger.warning("Failed to deserialize the manifest", exc_info=exc)
        return {"reason": f"Vlob decryption failed: {exc}"}, 400

    except ReassemblyError as exc:
        logger.warning("Failed to reassemble the file", exc_info=exc)
        return {"reason": f"The file cannot be reassembled: {exc}"}, 400

    except AntivirusError as exc:
        logger.warning("Antivirus analysis failed", exc_info=exc)
        return {"error": f"Antivirus analysis failed: {exc}"}, 503
