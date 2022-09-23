import io
import urllib
import base64
import structlog
from quart import Blueprint, request, current_app

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
        assert isinstance(vlob, bytes)
        decrypted_vlob = sequester_service_decrypt(
            current_app.config["APP_CONFIG"].authority_private_key, vlob
        )
        # Connector does not care if data is signed or not
        manifest = manifest_unverified_load(decrypted_vlob)
        if not isinstance(manifest, FileManifest):
            return None
        return manifest
    except Exception as exc:
        raise ManifestError(str(exc))


async def reassemble_file(manifest, organization_id):
    assert isinstance(manifest, FileManifest)

    out = io.BytesIO()
    blockstore = current_app.config["BLOCKSTORE"]

    for block in manifest.blocks:
        try:
            block_data = await blockstore.read(
                organization_id=organization_id, id=block.id
            )
        except Exception as exc:
            raise ReassemblyError(f"Failed to download a block: {exc}")

        try:
            cleardata = block.key.decrypt(block_data)
        except Exception as exc:
            raise ReassemblyError(f"Failed to decrypt a block: {exc}")

        try:
            if out.tell() != block.offset:
                out.seek(block.offset)
            if block.size != len(cleardata):
                out.write(cleardata[block.size])
            else:
                out.write(cleardata)
        except OSError as exc:
            raise ReassemblyError(f"Failed to reassemble the file: {exc}")

    return out


@bp.route("/submit", methods=["POST"])
async def submit():
    try:
        # Get the raw data, `application/x-www-form-urlencoded`
        data = await request.get_data()
        # Decode it
        decoded = data.decode()
        # Parse it to a dict of list of values
        content = urllib.parse.parse_qs(decoded)
        b64_vlob = content["sequester_blob"][0]
        # Decode the base64
        vlob = base64.urlsafe_b64decode(b64_vlob.encode())
        # Get the organization_id
        organization_id = OrganizationID(content["organization_id"][0])
    except KeyError as exc:
        raise APIException(400, {"error": f"Missing argument: {exc}"})
    except ValueError as exc:
        raise APIException(400, {"error": f"Invalid value for argument: {exc}"})
    except Exception as exc:
        logger.warn(f"Error while parsing the arguments: {exc}")
        raise APIException(400, {"error": f"Error parsing arguments: {exc}"})
    try:
        # Decrypt and deserialize the manifest
        manifest = await load_manifest(vlob)
        if not manifest:
            # Not a file manifest
            return {"info": "Not a file manifest"}, 200

        # Download the blocks and recombine into a file
        content_stream = await reassemble_file(manifest, organization_id)

        # Send to the antivirus
        malwares = await check_for_malwares(
            content_stream, current_app.config["APP_CONFIG"]
        )
        if not malwares:
            return {}, 200
        else:
            logger.warn(f"Malwares detected: {', '.join(malwares)}")
            return {
                "error": f"Malicious file detected by anti-virus scan: {', '.join(malwares)}"
            }, 400
    except ManifestError as exc:
        logger.warn(f"Error while deserializing the manifest: {exc}")
        raise APIException(400, {"error": f"Vlob decryption failed: {exc}"})
    except ReassemblyError as exc:
        logger.warn(f"Error while reassembling the file: {exc}")
        raise APIException(400, {"error": f"The file cannot be reassembled: {exc}"})
    except AntivirusError as exc:
        logger.warn(f"Error with the antivirus analysis: {exc}")
        raise APIException(400, {"error": f"Antivirus analysis failed: {exc}"})
