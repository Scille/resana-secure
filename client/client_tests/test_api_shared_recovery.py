import pytest
from quart.typing import TestAppProtocol, TestClientProtocol

from .conftest import LocalDeviceTestbed, RemoteDeviceTestbed


@pytest.mark.trio
async def test_shamir_recovery_setup(
    test_app: TestAppProtocol,
    bob_user: LocalDeviceTestbed,
    carl_user: LocalDeviceTestbed,
    diana_user: LocalDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    alice_client = authenticated_client
    bob_client = await bob_user.authenticated_client(test_app)
    carl_client = await carl_user.authenticated_client(test_app)
    diana_client = await diana_user.authenticated_client(test_app)

    # No client sees any setup
    for client in (alice_client, bob_client, carl_client, diana_client):
        response = await client.get("/recovery/shamir/setup/others")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"setups": []}

    # Create a new shared recovery device
    json = {
        "threshold": 3,
        "recipients": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 1},
            {"email": "diana@example.com", "weight": 1},
        ],
    }
    response = await alice_client.post("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Check current configuration
    response = await alice_client.get("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "device_label": "alice's desktop",
        "threshold": 3,
        "recipients": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 1},
            {"email": "diana@example.com", "weight": 1},
        ],
    }

    # Alice does not see her own setup
    response = await alice_client.get("/recovery/shamir/setup/others")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"setups": []}

    # All recipients can see the setup
    for client in (bob_client, carl_client, diana_client):
        response = await client.get("/recovery/shamir/setup/others")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {
            "setups": [
                {
                    "email": "alice@example.com",
                    "label": "Alice",
                    "device_label": "alice's desktop",
                    "threshold": 3,
                    "recipients": [
                        {"email": "bob@example.com", "weight": 2},
                        {"email": "carl@example.com", "weight": 1},
                        {"email": "diana@example.com", "weight": 1},
                    ],
                    "my_weight": 2 if client is bob_client else 1,
                }
            ],
        }

    # Setup can be recreated
    json = {
        "threshold": 5,
        "recipients": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 3},
            {"email": "diana@example.com", "weight": 2},
        ],
    }
    response = await alice_client.post("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Check current configuration
    response = await alice_client.get("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "device_label": "alice's desktop",
        "threshold": 5,
        "recipients": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 3},
            {"email": "diana@example.com", "weight": 2},
        ],
    }

    # Alice still does not see her own setup
    response = await alice_client.get("/recovery/shamir/setup/others")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"setups": []}

    # All recipients can see the new setup
    for client in (bob_client, carl_client, diana_client):
        response = await client.get("/recovery/shamir/setup/others")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {
            "setups": [
                {
                    "email": "alice@example.com",
                    "label": "Alice",
                    "device_label": "alice's desktop",
                    "threshold": 5,
                    "recipients": [
                        {"email": "bob@example.com", "weight": 2},
                        {"email": "carl@example.com", "weight": 3},
                        {"email": "diana@example.com", "weight": 2},
                    ],
                    "my_weight": 3 if client is carl_client else 2,
                }
            ],
        }

    # Remove shared recovery setup
    response = await alice_client.delete("/recovery/shamir/setup")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}

    # Check current configuration
    response = await alice_client.get("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "not_setup"}

    # No client sees any setup
    for client in (alice_client, bob_client, carl_client, diana_client):
        response = await client.get("/recovery/shamir/setup/others")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"setups": []}

    # Deletion is idempotent
    response = await alice_client.delete("/recovery/shamir/setup")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}

    # Check current configuration
    response = await alice_client.get("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "not_setup"}


@pytest.mark.trio
async def test_shamir_recovery_setup_invalid_nested_types(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    json = {
        "threshold": "x",
        "recipients": [
            {"email": "alice", "weight": 2},
            {"email": "bob@example.com", "weight": 1},
            {"email": "carl@example.com", "weight": "y"},
        ],
    }
    response = await authenticated_client.post("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {
        "error": "bad_data",
        "fields": ["threshold", "recipients.[0].email", "recipients.[2].weight"],
    }


@pytest.mark.trio
async def test_shamir_recovery_setup_users_not_found(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed,
    bob_user: RemoteDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    json = {
        "threshold": 3,
        "recipients": [
            {"email": "bob@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 1},
            {"email": "diana@example.com", "weight": 1},
        ],
    }
    response = await authenticated_client.post("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"emails": ["carl@example.com", "diana@example.com"], "error": "users_not_found"}


@pytest.mark.trio
async def test_shamir_recovery_setup_user_in_recipients(
    test_app: TestAppProtocol,
    local_device: LocalDeviceTestbed,
    carl_user: RemoteDeviceTestbed,
    diana_user: RemoteDeviceTestbed,
    authenticated_client: TestClientProtocol,
):
    json = {
        "threshold": 3,
        "recipients": [
            {"email": "alice@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 1},
            {"email": "diana@example.com", "weight": 1},
        ],
    }
    response = await authenticated_client.post("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "invalid_configuration"}
