import pytest
from quart.typing import TestAppProtocol, TestClientProtocol

from .conftest import LocalDeviceTestbed, RemoteDeviceTestbed


@pytest.mark.trio
async def test_shared_recovery_setup_ok(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed,
    bob_user: RemoteDeviceTestbed,
    carl_user: RemoteDeviceTestbed,
    diana_user: RemoteDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    # Create a new shared recovery device
    json = {
        "threshold": 3,
        "users": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 1},
            {"email": "diana@example.com", "weight": 1},
        ],
    }
    response = await authenticated_client.post("/recovery/shared/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Check current configuration
    response = await authenticated_client.get("/recovery/shared/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "device_label": "alice's desktop",
        "threshold": 3,
        "users": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 1},
            {"email": "diana@example.com", "weight": 1},
        ],
    }

    # Setup can be recreated
    json = {
        "threshold": 5,
        "users": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 3},
            {"email": "diana@example.com", "weight": 2},
        ],
    }
    response = await authenticated_client.post("/recovery/shared/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Check current configuration
    response = await authenticated_client.get("/recovery/shared/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "device_label": "alice's desktop",
        "threshold": 5,
        "users": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 3},
            {"email": "diana@example.com", "weight": 2},
        ],
    }

    # Remove shared recovery setup
    response = await authenticated_client.delete("/recovery/shared/setup")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}

    # Check current configuration
    response = await authenticated_client.get("/recovery/shared/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "not_setup"}

    # Deletion is idempotent
    response = await authenticated_client.delete("/recovery/shared/setup")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}

    # Check current configuration
    response = await authenticated_client.get("/recovery/shared/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "not_setup"}


@pytest.mark.trio
async def test_shared_recovery_setup_invalid_nested_types(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    json = {
        "threshold": "x",
        "users": [
            {"email": "alice", "weight": 2},
            {"email": "bob@example.com", "weight": 1},
            {"email": "carl@example.com", "weight": "y"},
        ],
    }
    response = await authenticated_client.post("/recovery/shared/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {
        "error": "bad_data",
        "fields": ["threshold", "users.[0].email", "users.[2].weight"],
    }


@pytest.mark.trio
async def test_shared_recovery_setup_users_not_found(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed,
    bob_user: RemoteDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    json = {
        "threshold": 3,
        "users": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 1},
            {"email": "diana@example.com", "weight": 1},
        ],
    }
    response = await authenticated_client.post("/recovery/shared/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"emails": ["carl@example.com", "diana@example.com"], "error": "users_not_found"}


@pytest.mark.trio
async def test_shared_recovery_setup_user_in_recipients(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed,
    carl_user: RemoteDeviceTestbed,
    diana_user: RemoteDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    json = {
        "threshold": 3,
        "users": [
            {"email": "alice@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 1},
            {"email": "diana@example.com", "weight": 1},
        ],
    }
    response = await authenticated_client.post("/recovery/shared/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "invalid_configuration"}
