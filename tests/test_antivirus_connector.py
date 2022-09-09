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

    response = await getattr(test_client, method.lower())("/submit")
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

    data = {
        "organization_id": "OrgID",
        "sequester_blob": base64.urlsafe_b64encode(b"a"),
    }
    response = await test_client.post(
        "/submit", data=urllib.parse.urlencode(data).encode()
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body == {}


@pytest.mark.trio
async def test_submit_invalid_args(antivirus_test_app):
    test_client = antivirus_test_app.test_client()

    data = {
        "organization_id": " a b c ",
        "sequester_blob": base64.urlsafe_b64encode(b"a"),
    }
    # Invalid org id
    response = await test_client.post(
        "/submit", data=urllib.parse.urlencode(data).encode()
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "Invalid value for argument: Invalid OrganizationID"}

    data = {
        "sequester_blob": base64.urlsafe_b64encode(b"a"),
    }
    # Missing org id
    response = await test_client.post(
        "/submit", data=urllib.parse.urlencode(data).encode()
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "Missing argument: 'organization_id'"}

    data = {
        "organization_id": "OrgID",
    }
    # Missing sequester blob
    response = await test_client.post(
        "/submit", data=urllib.parse.urlencode(data).encode()
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "Missing argument: 'sequester_blob'"}

    data = {
        "organization_id": "OrgID",
        "sequester_blob": b"aaa",
    }
    # Invalid sequester blob (not base64 encoded)
    response = await test_client.post(
        "/submit", data=urllib.parse.urlencode(data).encode()
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "Invalid value for argument: Incorrect padding"}

    data = {
        "organization_id": "OrgID",
        "sequester_blob": 42,
    }
    # Invalid sequester blob (invalid type)
    response = await test_client.post(
        "/submit", data=urllib.parse.urlencode(data).encode()
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "Invalid value for argument: Incorrect padding"}


@pytest.mark.trio
async def test_submit_deserialization_failure(antivirus_test_app, monkeypatch):
    monkeypatch.setattr(
        "antivirus_connector.routes.load_manifest",
        AsyncMock(side_effect=ManifestError("invalid key")),
    )
    test_client = antivirus_test_app.test_client()

    data = {
        "organization_id": "OrgID",
        "sequester_blob": base64.urlsafe_b64encode(b"a"),
    }

    response = await test_client.post(
        "/submit", data=urllib.parse.urlencode(data).encode()
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

    data = {
        "organization_id": "OrgID",
        "sequester_blob": base64.urlsafe_b64encode(b"a"),
    }

    response = await test_client.post(
        "/submit", data=urllib.parse.urlencode(data).encode()
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

    data = {
        "organization_id": "OrgID",
        "sequester_blob": base64.urlsafe_b64encode(b"a"),
    }

    response = await test_client.post(
        "/submit", data=urllib.parse.urlencode(data).encode()
    )
    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "Malicious file detected by anti-virus scan: keylogger"}
