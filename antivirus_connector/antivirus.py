import httpx
import trio
import structlog
import json

from .config import AppConfig


logger = structlog.get_logger()


class AntivirusError(Exception):
    pass


async def log_request(request):
    logger.debug(f"{request.method} {request.url} {request.headers}")


async def check_for_malwares(content_stream, config: AppConfig):
    url = config.antivirus_api_url
    api_key = config.antivirus_api_key

    async with httpx.AsyncClient(event_hooks={"request": [log_request]}) as client:
        headers = {"X-Auth-Token": api_key}
        form = {"file": content_stream.getvalue()}
        try:
            # Posting the file
            r = await client.post(
                f"{url}/submit",
                headers=headers,
                files=form,
            )
        except httpx.ConnectError:
            raise AntivirusError("Could not connect to the antivirus service")

        logger.debug(f"Antivirus API answered {r.status_code}")

        try:
            data = r.json()
        except json.decoder.JSONDecodeError:
            raise AntivirusError(f"{r.status_code} Invalid JSON response")

        if r.status_code != 200 or not data["status"]:
            raise AntivirusError(f"{r.status_code} {data.get('error', '')}")
        # File has been accepted, now we wait for it to be analyzed
        analysis_id = data["uuid"]
        done = False
        # Retry until the analysis is done
        while not done:
            try:
                # Get analysis status
                r = await client.get(
                    f"{url}/results/{analysis_id}",
                    headers=headers,
                )
            except httpx.ConnectError:
                raise AntivirusError("Could not connect to the antivirus service")
            try:
                data = r.json()
            except json.decoder.JSONDecodeError:
                raise AntivirusError(f"{r.status_code} Invalid JSON response")
            if r.status_code != 200 or not data["status"]:
                raise AntivirusError(f"{r.status_code} {data.get('error', '')}")
            done = data["done"]
            # Analysis is finished, check if a malware has been detected
            if done:
                if data["is_malware"]:
                    return data["malwares"]
                else:
                    return []
            else:
                # Avoid making too many requests
                trio.sleep(0.5)
