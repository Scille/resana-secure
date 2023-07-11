import pytest
from base64 import b64encode
from tempfile import mkstemp
import pathlib
from quart.typing import TestAppProtocol, TestClientProtocol
from parsec._parsec import save_recovery_device

from pathlib import Path
import os
from .conftest import LocalDeviceTestbed , LocalDeviceTestbed2


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
    response = await anonymous_client.post(
        "/auth",
        json={
            "email": local_device.device.human_handle.email,
            "key": "new_key",
            "organization": local_device.organization.str,
        },
    )
    assert response.status_code == 200


@pytest.mark.trio
async def test_recovery_with_big_number_of_device(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed2,
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
    nb_of_device_to_make = 20
    device_info_list = []
    file_to_not_rename = []
    # If you set rename_or_not to True it will assume there is device already on the folder then will delete the "bad" one 

    # If you set rename_or_not to False it will assume there is no device and they are set to be created so it won't make the same device twice

    rename_or_not = True
    for i in range(nb_of_device_to_make):
        email_device_id = local_device.device.human_handle.email + local_device.organization.str
        # This way of code work like this it assume that there is already X device created at start and it loop through each of them and check for the device email and id and store the device position if the unique to ensure the device won't get deleted

        if email_device_id not in device_info_list and rename_or_not == True:
            file_to_not_rename.append(i)
            device_info_list.append(email_device_id)
        
        # This way of code is "different" it assume that at the start there is 0 devices so if the user try to create X times the same device it will check if the same device has already been created
        
        if email_device_id not in device_info_list and rename_or_not == False:
            response = await anonymous_client.post(
                "/recovery/import",
                json={
                    "recovery_device_file_content": body["file_content"],
                    "recovery_device_passphrase": body["passphrase"],
                    "new_device_key": b64encode(new_device_key).decode("ascii"),
                },
            )
            device_info_list.append(email_device_id)
        elif rename_or_not == True:
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
    folder_path = str(local_device.config_dir) + "/devices"
    file_list = [file.name for file in Path(folder_path).iterdir() if file.is_file()]

    if rename_or_not == True:
        assert nb_of_device_to_make == len(file_list) - 1
    
    if rename_or_not == True:
        for i, file_name in enumerate(file_list):
            old_name = folder_path + "/" + file_name
            new_name = folder_path + "/" + file_name.replace(".keys","_backup.txt")
            if i not in file_to_not_rename:
                os.rename(old_name,new_name)
    response = await anonymous_client.post(
        "/auth",
        json={
            "email": local_device.device.human_handle.email,
            "key": b64encode(new_device_key).decode("ascii"),
            "organization": local_device.organization.str,
        },
    )
    assert response.status_code == 200