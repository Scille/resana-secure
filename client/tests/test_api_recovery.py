import pytest
from base64 import b64encode
from tempfile import mkstemp
import pathlib
from quart.typing import TestAppProtocol, TestClientProtocol

from tests.conftest import LocalDeviceTestbed


@pytest.mark.trio
async def test_recovery_ok(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    response = await authenticated_client.post("/recovery/export", json={})
    body = await response.get_json()
    assert response.status_code == 200
    assert (
        body["file_name"]
        == f"resana-secure-recovery-{local_device.device.organization_id.str}-{local_device.device.short_user_display}.psrk"
    )
    assert "file_content" in body
    assert "passphrase" in body

    new_device_key = b"P@ssw0rd."
    anonymous_client = test_app.test_client()
    response = await anonymous_client.post(
        "/recovery/import",
        json={
            "recovery_device_file_content": body["file_content"],
            "recovery_device_passphrase": body["passphrase"],
            "new_device_key": b64encode(new_device_key).decode("ascii"),
        },
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body == {}

    # New user should be able to connect
    response = await anonymous_client.post(
        "/auth",
        json={
            "email": local_device.device.human_handle.email,
            "key": b64encode(new_device_key).decode("ascii"),
            "organization": local_device.organization.str,
        },
    )
    assert response.status_code == 200


@pytest.mark.trio
async def test_recovery_invalid_passphrase(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    response = await authenticated_client.post("/recovery/export", json={})
    body = await response.get_json()
    assert response.status_code == 200
    assert (
        body["file_name"]
        == f"resana-secure-recovery-{local_device.device.organization_id.str}-{local_device.device.short_user_display}.psrk"
    )
    assert "file_content" in body
    assert "passphrase" in body

    invalid_passphrase = "1234-1234-1234-1234-1234-1234-1234-1234-1234-1234-1234-1234-1234"

    new_device_key = b"P@ssw0rd."
    anonymous_client = test_app.test_client()
    response = await anonymous_client.post(
        "/recovery/import",
        json={
            "recovery_device_file_content": body["file_content"],
            "recovery_device_passphrase": invalid_passphrase,
            "new_device_key": b64encode(new_device_key).decode("ascii"),
        },
    )

    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "invalid_passphrase"}


@pytest.mark.trio
async def test_recovery_delete_temp_file(
    test_app: TestAppProtocol, authenticated_client: TestClientProtocol, monkeypatch
):
    response = await authenticated_client.post("/recovery/export", json={})
    body = await response.get_json()
    assert response.status_code == 200

    temp_path: str

    new_device_key = b"P@ssw0rd."
    anonymous_client = test_app.test_client()

    def _mkstemp_patch(*args, **kwargs):
        nonlocal temp_path

        fp, temp_path = mkstemp(*args, **kwargs)
        assert pathlib.Path(temp_path).is_file()
        return fp, temp_path

    monkeypatch.setattr("resana_secure.routes.recovery.tempfile.mkstemp", _mkstemp_patch)

    response = await anonymous_client.post(
        "/recovery/import",
        json={
            "recovery_device_file_content": body["file_content"],
            "recovery_device_passphrase": body["passphrase"],
            "new_device_key": b64encode(new_device_key).decode("ascii"),
        },
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body == {}

    assert not pathlib.Path(temp_path).exists()
