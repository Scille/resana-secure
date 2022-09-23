import pytest
from unittest.mock import AsyncMock, MagicMock
import base64
import urllib

from antivirus_connector.app import app_factory
from antivirus_connector.routes import ManifestError, ReassemblyError, reassemble_file
from antivirus_connector.antivirus import AntivirusError


@pytest.fixture
async def antivirus_test_app():
    async with app_factory(None, None, []) as app:
        async with app.test_app() as test_app:
            yield test_app


@pytest.mark.trio
@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE", "PATCH"])
async def test_submit_methods(antivirus_test_app, method):
    test_client = antivirus_test_app.test_client()

    response = await getattr(test_client, method.lower())("/submit/OrgID")
    assert response.status_code == 405


@pytest.mark.trio
async def test_submit(antivirus_test_app, monkeypatch):
    test_client = antivirus_test_app.test_client()

    monkeypatch.setattr(
        "antivirus_connector.routes.check_for_malwares", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "antivirus_connector.routes.load_manifest", AsyncMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        "antivirus_connector.routes.reassemble_file",
        AsyncMock(return_value=MagicMock()),
    )

    response = await test_client.post(
        "/submit/Org",
        data=b"a",
    )
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
    assert response.status_code == 400
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
    assert body == {"error": "Vlob decryption failed: "}


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
    assert body == {"error": "Vlob decryption failed: invalid key"}


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
    assert body == {"error": "The file cannot be reassembled: cannot decrypt block"}


@pytest.mark.trio
async def test_submit_antivirus_ko(antivirus_test_app, monkeypatch):
    monkeypatch.setattr(
        "antivirus_connector.routes.load_manifest", AsyncMock(return_value=MagicMock())
    )
    monkeypatch.setattr(
        "antivirus_connector.routes.reassemble_file",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "antivirus_connector.routes.check_for_malwares",
        AsyncMock(return_value=["keylogger"]),
    )
    test_client = antivirus_test_app.test_client()

    response = await test_client.post(
        "/submit/OrgID",
        data=b"a",
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "Malicious file detected by anti-virus scan: keylogger"}
