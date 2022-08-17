import pytest
from base64 import b64encode


@pytest.mark.trio
async def test_recovery_ok(test_app, local_device, authenticated_client):
    response = await authenticated_client.post("/recovery/export", json={})
    body = await response.get_json()
    assert response.status_code == 200
    assert (
        body["file_name"]
        == f"resana-secure-recovery-{local_device.device.organization_id}-{local_device.device.short_user_display}.psrk"
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
async def test_recovery_invalid_passphrase(test_app, local_device, authenticated_client):
    response = await authenticated_client.post("/recovery/export", json={})
    body = await response.get_json()
    assert response.status_code == 200
    assert (
        body["file_name"]
        == f"resana-secure-recovery-{local_device.device.organization_id}-{local_device.device.short_user_display}.psrk"
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
