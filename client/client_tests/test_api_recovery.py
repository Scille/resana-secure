from __future__ import annotations

import os
import pathlib
from base64 import b64encode
from tempfile import mkstemp

import pytest
from quart.typing import TestAppProtocol, TestClientProtocol

from parsec._parsec import save_recovery_device

from .conftest import LocalDeviceTestbed


@pytest.mark.trio
async def test_recovery_ok(
    test_app: TestAppProtocol,
    core_config_dir: pathlib.Path,
    local_device: LocalDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    first_key_file = os.listdir(f"{core_config_dir}/devices")[0]
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
    assert local_device.device.human_handle is not None
    response = await anonymous_client.post(
        "/auth",
        json={
            "email": local_device.device.human_handle.email,
            "key": b64encode(new_device_key).decode("ascii"),
            "organization": local_device.organization.str,
        },
    )
    assert response.status_code == 200

    # Old key file should be rename
    list_key_file = os.listdir(f"{core_config_dir}/devices")
    assert len(list_key_file) == 2
    assert first_key_file.replace(".keys", ".old_key") in list_key_file


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

    temp_path: str | None = None

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

    assert temp_path is not None
    assert not pathlib.Path(temp_path).exists()


@pytest.mark.trio
async def test_can_import_old_recovery_devices(
    test_app: TestAppProtocol, local_device: LocalDeviceTestbed, tmp_path: pathlib.Path
):
    # Create a recovery device the old way
    file_key = tmp_path / "recovery.psrk"
    passphrase = await save_recovery_device(file_key, local_device.device, True)
    raw = file_key.read_bytes()

    anonymous_client = test_app.test_client()
    response = await anonymous_client.post(
        "/recovery/import",
        json={
            "recovery_device_file_content": b64encode(raw).decode(),
            "recovery_device_passphrase": passphrase,
            "new_device_key": "new_key",
        },
    )
    assert response.status_code == 200
    body = await response.get_json()
    assert body == {}

    # Auth with new device
    assert local_device.device.human_handle is not None
    response = await anonymous_client.post(
        "/auth",
        json={
            "email": local_device.device.human_handle.email,
            "key": "new_key",
            "organization": local_device.organization.str,
        },
    )
    assert response.status_code == 200
