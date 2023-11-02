import json
import ssl
import tempfile
from typing import List

import httpx
import structlog
import trio

from .config import AppConfig

logger = structlog.get_logger()


class AntivirusError(Exception):
    pass


async def check_for_malwares(content_stream, config: AppConfig) -> List[str]:
    url = config.antivirus_api_url
    api_key = config.antivirus_api_key

    with tempfile.NamedTemporaryFile(mode="w") as certfile, tempfile.NamedTemporaryFile(
        mode="w"
    ) as keyfile:
        cert = None
        if config.antivirus_api_cert and config.antivirus_api_cert_request_key:
            certfile.write(config.antivirus_api_cert)
            certfile.seek(0)
            keyfile.write(config.antivirus_api_cert_request_key)
            keyfile.seek(0)
            cert = (certfile.name, keyfile.name)

        context = ssl._create_unverified_context()
        # MyPy don't like cert arg
        async with httpx.AsyncClient(cert=cert, verify=context) as client:  # type: ignore[arg-type]
            headers = {"X-Auth-Token": api_key}
            form = {"file": content_stream.getvalue()}
            try:
                # Posting the file
                r = await client.post(url=f"{url}/submit", headers=headers, files=form)
            except httpx.ConnectError as exc:
                raise AntivirusError("Could not connect to the antivirus service") from exc

            logger.debug(f"Antivirus API answered {r.status_code}")

            try:
                data = r.json()
            except json.decoder.JSONDecodeError as exc:
                raise AntivirusError(
                    f"Unexpected response {r.status_code}: Invalid JSON body"
                ) from exc

            if (
                r.status_code != 200
                or not isinstance(data, dict)
                or data.get("status") is not True
                or not isinstance(data.get("sha256"), str)
            ):
                raise AntivirusError(f"Unexpected response {r.status_code}: {data!r}")

            # Analysis is already done
            if data["done"]:
                # Analysis is finished, check if a malware has been detected
                if data["is_malware"]:
                    if not isinstance(data.get("malwares"), list) or not all(
                        isinstance(m, str) for m in data["malwares"]
                    ):
                        raise AntivirusError(f"Unexpected response {r.status_code}: {data!r}")
                    return data["malwares"]
                else:
                    return []

            # File has been accepted, now we wait for it to be analyzed
            analysis_sha256 = data["sha256"]
            # Retry until the analysis is done
            while True:
                try:
                    # Get analysis status
                    r = await client.get(
                        f"{url}/cache/{analysis_sha256}",
                        headers=headers,
                    )
                except httpx.ConnectError as exc:
                    raise AntivirusError("Could not connect to the antivirus service") from exc
                try:
                    data = r.json()
                except json.decoder.JSONDecodeError as exc:
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
                    raise AntivirusError(f"Unexpected response {r.status_code}: {data!r}")

                if data["done"]:
                    # Analysis is finished, check if a malware has been detected
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
                    await trio.sleep(2)
