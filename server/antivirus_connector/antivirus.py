import httpx
import trio
import structlog
import json
import tempfile
import os
from typing import List

from .config import AppConfig


logger = structlog.get_logger()


class AntivirusError(Exception):
    pass


async def check_for_malwares(content_stream, config: AppConfig) -> List[str]:
    url = config.antivirus_api_url
    api_key = config.antivirus_api_key
    api_cert = tempfile.NamedTemporaryFile(delete=False)
    api_cert.write(config.antivirus_api_cert)
    api_cert.close()

    async with httpx.AsyncClient() as client:
        headers = {"X-Auth-Token": api_key}
        form = {"file": content_stream.getvalue()}
        try:
            # Posting the file
            r = await client.post(
                url=f"{url}/submit",
                headers=headers,
                files=form,
                cert=api_cert
            )
        except httpx.ConnectError as exc:
            os.unlink(api_cert.name)
            raise AntivirusError("Could not connect to the antivirus service") from exc

        logger.debug(f"Antivirus API answered {r.status_code}")

        try:
            data = r.json()
        except json.decoder.JSONDecodeError as exc:
            raise AntivirusError(f"Unexpected response {r.status_code}: Invalid JSON body") from exc

        if (
            r.status_code != 200
            or not isinstance(data, dict)
            or data.get("status") is not True
            or not isinstance(data.get("uuid"), str)
        ):
            raise AntivirusError(f"Unexpected response {r.status_code}: {data!r}")

        # File has been accepted, now we wait for it to be analyzed
        analysis_id = data["uuid"]
        # Retry until the analysis is done
        while True:
            try:
                # Get analysis status
                r = await client.get(
                    f"{url}/results/{analysis_id}",
                    headers=headers,
                    cert=api_cert
                )
            except httpx.ConnectError as exc:
                os.unlink(api_cert.name)
                raise AntivirusError("Could not connect to the antivirus service") from exc
            try:
                data = r.json()
            except json.decoder.JSONDecodeError as exc:
                os.unlink(api_cert.name)
                raise AntivirusError(
                    f"Unexpected response {r.status_code}: Invalid JSON body"
                ) from exc

            if (
                r.status_code != 200
                or not isinstance(data, dict)
                or data.get("status") is not True
                or not isinstance(data.get("done"), bool)
                or not isinstance(data.get("is_malware"), bool)
            ):
                os.unlink(api_cert.name)
                raise AntivirusError(f"Unexpected response {r.status_code}: {data!r}")

            if data["done"]:
                # Analysis is finished, check if a malware has been detected
                os.unlink(api_cert.name)
                if data["is_malware"]:
                    if not isinstance(data.get("malwares"), list) or not all(
                        isinstance(m, str) for m in data["malwares"]
                    ):
                        raise AntivirusError(f"Unexpected response {r.status_code}: {data!r}")
                    return data["malwares"]
                else:
                    return []
            else:
                # Avoid making too many requests
                await trio.sleep(0.5)
