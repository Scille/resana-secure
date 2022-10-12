import pytest
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock
import httpx

from parsec.backend.config import MockedBlockStoreConfig

from antivirus_connector.app import app_factory, AppConfig
from antivirus_connector.routes import ManifestError, ReassemblyError


@pytest.fixture
async def antivirus_test_app():
    config = AppConfig(
        sequester_service_decryption_key=b"\x00" * 32,
        antivirus_api_url="http://antivirus.localhost",
        antivirus_api_key="1234",
        blockstore_config=MockedBlockStoreConfig(),
        db_url="postgresql://db.localhost",
        db_min_connections=5,
        db_max_connections=7,
    )

    async with app_factory(config=config, blockstore=MagicMock(), client_allowed_origins=[]) as app:
        async with app.test_app() as test_app:
            yield test_app


@pytest.mark.trio
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH"])
async def test_submit_methods(antivirus_test_app, method):
    test_client = antivirus_test_app.test_client()

    response = await getattr(test_client, method.lower())("/submit/OrgID")
    assert response.status_code == 405


@pytest.mark.trio
@pytest.mark.parametrize("is_malware", (False, True))
async def test_submit(antivirus_test_app, monkeypatch, is_malware):
    test_client = antivirus_test_app.test_client()

    antivirus_state = "stalled"

    monkeypatch.setattr(
        "antivirus_connector.routes.load_manifest", AsyncMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        "antivirus_connector.routes.reassemble_file",
        AsyncMock(return_value=BytesIO(b"<file content>")),
    )

    async def fake_antivirus_http_post(self, url, headers, files):
        nonlocal antivirus_state
        assert antivirus_state == "stalled"
        assert url.endswith("/submit")
        assert headers["X-Auth-Token"]
        assert files["file"]
        antivirus_state = "work_started"
        return httpx.Response(200, json={"status": True, "uuid": "d8b5a554-04b8-4af6-9e08-524d76ec8d12"})
    monkeypatch.setattr("httpx.AsyncClient.post", fake_antivirus_http_post)

    async def fake_antivirus_http_get(self, url, headers):
        nonlocal antivirus_state
        assert antivirus_state in ("work_started", "work_continued")
        assert url.endswith("/results/d8b5a554-04b8-4af6-9e08-524d76ec8d12")
        assert headers["X-Auth-Token"]
        if antivirus_state == "work_started":
            antivirus_state = "work_continued"
            return httpx.Response(200, json={"status": True, "done": False, "is_malware": False})
        elif antivirus_state == "work_continued":
            antivirus_state = "finished"
            malwares = ["keylogger"] if is_malware else []
            return httpx.Response(200, json={"status": True, "done": True, "is_malware": is_malware, "malwares": malwares})
    monkeypatch.setattr("httpx.AsyncClient.get", fake_antivirus_http_get)

    response = await test_client.post(
        "/submit/Org",
        data=b"a",
    )
    if is_malware:
        assert response.status_code == 400
        body = await response.get_json()
        assert body == {"reason": "Malicious file detected by anti-virus scan: keylogger"}
    else:
        assert response.status_code == 200
        body = await response.get_json()
        assert body == {}


@pytest.mark.trio
async def test_submit_invalid_args(antivirus_test_app):
    test_client = antivirus_test_app.test_client()

    # Invalid org id
    response = await test_client.post(
        "/submit/a38^#'",
        data=b"a",
    )
    assert response.status_code == 422
    body = await response.get_json()
    assert body == {"error": "Failed to parse arguments: Invalid OrganizationID"}

    # Missing org id
    response = await test_client.post(
        "/submit",
        data=b"a",
    )
    assert response.status_code == 404

    # Missing sequester blob
    response = await test_client.post("/submit/Org", data=b"")
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"reason": "Vlob decryption failed: "}


@pytest.mark.trio
async def test_submit_deserialization_failure(antivirus_test_app, monkeypatch):
    monkeypatch.setattr(
        "antivirus_connector.routes.load_manifest",
        AsyncMock(side_effect=ManifestError("invalid key")),
    )
    test_client = antivirus_test_app.test_client()

    response = await test_client.post(
        "/submit/OrgID",
        data=b"a",
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"reason": "Vlob decryption failed: invalid key"}


@pytest.mark.trio
async def test_submit_reassembly_failure(antivirus_test_app, monkeypatch):
    monkeypatch.setattr(
        "antivirus_connector.routes.load_manifest", AsyncMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        "antivirus_connector.routes.reassemble_file",
        AsyncMock(side_effect=ReassemblyError("cannot decrypt block")),
    )
    test_client = antivirus_test_app.test_client()

    response = await test_client.post(
        "/submit/OrgID",
        data=b"a",
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"reason": "The file cannot be reassembled: cannot decrypt block"}