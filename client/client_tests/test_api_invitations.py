from __future__ import annotations

from unittest.mock import ANY

import pytest
from quart.typing import TestClientProtocol

from parsec._parsec import DateTime

from .conftest import LocalDeviceTestbed, TestAppProtocol


@pytest.mark.trio
async def test_create_list_delete_users_invitations(authenticated_client: TestClientProtocol):
    async def _check_invitations(expected_users):
        response = await authenticated_client.get("/invitations")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"users": expected_users, "device": None, "shamir_recoveries": []}
        return body

    # No invitations for a starter
    await _check_invitations([])

    # Add a first user invitation
    bob_invitation_created_on = None
    bob_invitation_token = None
    # User invitations are idempotent
    for i in range(2):
        response = await authenticated_client.post(
            "/invitations", json={"type": "user", "claimer_email": "bob@example.com"}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"token": ANY}
        if not bob_invitation_token:
            bob_invitation_token = body["token"]
        else:
            assert bob_invitation_token == body["token"]
        body = await _check_invitations(
            [
                {
                    "token": bob_invitation_token,
                    "created_on": bob_invitation_created_on or ANY,
                    "claimer_email": "bob@example.com",
                    "status": "IDLE",
                }
            ]
        )
        bob_invitation_created_on = body["users"][0]["created_on"]

    # Add another user invitation
    response = await authenticated_client.post(
        "/invitations", json={"type": "user", "claimer_email": "adam@example.com"}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"token": ANY}
    adam_invitation_token = body["token"]
    await _check_invitations(
        [
            {
                "token": bob_invitation_token,
                "created_on": bob_invitation_created_on,
                "claimer_email": "bob@example.com",
                "status": "IDLE",
            },
            {
                "token": adam_invitation_token,
                "created_on": ANY,
                "claimer_email": "adam@example.com",
                "status": "IDLE",
            },
        ]
    )

    # Delete user invitation
    response = await authenticated_client.delete(f"/invitations/{adam_invitation_token}")
    body = await response.get_json()
    assert response.status_code == 204
    assert body == {}
    await _check_invitations(
        [
            {
                "token": bob_invitation_token,
                "created_on": bob_invitation_created_on,
                "claimer_email": "bob@example.com",
                "status": "IDLE",
            }
        ]
    )
    # Deletion is not idempotent
    response = await authenticated_client.delete(f"/invitations/{adam_invitation_token}")
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "invitation_already_used"}


@pytest.mark.trio
async def test_create_list_delete_device_invitation(authenticated_client: TestClientProtocol):
    async def _check_invitations(expected_device):
        response = await authenticated_client.get("/invitations")
        body = await response.get_json()
        assert response.status_code == 200, body
        assert body == {"users": [], "device": expected_device, "shamir_recoveries": []}
        return body

    # No invitations for a starter
    await _check_invitations(None)

    # Device is idempotent
    invitation_created_on = None
    invitation_token = None
    for i in range(2):
        response = await authenticated_client.post("/invitations", json={"type": "device"})
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"token": ANY}
        if not invitation_token:
            invitation_token = body["token"]
        else:
            assert invitation_token == body["token"]
        body = await _check_invitations(
            {
                "token": invitation_token,
                "created_on": invitation_created_on or ANY,
                "status": "IDLE",
            }
        )
        invitation_created_on = body["device"]["created_on"]

    # Delete user invitation
    response = await authenticated_client.delete(f"/invitations/{invitation_token}")
    body = await response.get_json()
    assert response.status_code == 204
    assert body == {}
    await _check_invitations(None)
    # Deletion is not idempotent
    response = await authenticated_client.delete(f"/invitations/{invitation_token}")
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "invitation_already_used"}


@pytest.mark.trio
async def test_create_list_delete_shamir_recovery_invitations(
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

    async def _check_invitations(client, expected_shamir_recoveries):
        response = await client.get("/invitations")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {
            "users": [],
            "device": None,
            "shamir_recoveries": expected_shamir_recoveries,
        }
        return body

    # No invitations for a starter
    for client in (alice_client, bob_client, carl_client, diana_client):
        await _check_invitations(client, [])

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

    # User invitations are idempotent
    alice_invitation_created_on: DateTime | None = None
    for i in range(2):
        response = await bob_client.post(
            "/invitations", json={"type": "shamir_recovery", "claimer_email": "alice@example.com"}
        )
        body = await response.get_json()
        assert response.status_code == 200, body

        if i == 0:
            alice_invitation_token = body["token"]
        else:
            assert alice_invitation_token == body["token"]
        assert body == {"token": alice_invitation_token}

        for client in (bob_client, carl_client, diana_client):
            body = await _check_invitations(
                client,
                [
                    {
                        "token": alice_invitation_token,
                        "created_on": ANY if i == 0 else alice_invitation_created_on,
                        "claimer_email": "alice@example.com",
                        "status": "IDLE",
                    }
                ],
            )
            alice_invitation_created_on = body["shamir_recoveries"][0]["created_on"]

        # Alice does not see the invitation though
        await _check_invitations(alice_client, [])

    # Add another recovery setup
    json = {
        "threshold": 3,
        "recipients": [
            {"email": "alice@example.com", "weight": 2},
            {"email": "carl@example.com", "weight": 1},
            {"email": "diana@example.com", "weight": 1},
        ],
    }
    response = await bob_client.post("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # And another invitation
    response = await alice_client.post(
        "/invitations", json={"type": "shamir_recovery", "claimer_email": "bob@example.com"}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"token": ANY}
    bob_invitation_token = body["token"]

    for client in (carl_client, diana_client):
        await _check_invitations(
            client,
            [
                {
                    "token": alice_invitation_token,
                    "created_on": alice_invitation_created_on,
                    "claimer_email": "alice@example.com",
                    "status": "IDLE",
                },
                {
                    "token": bob_invitation_token,
                    "created_on": ANY,
                    "claimer_email": "bob@example.com",
                    "status": "IDLE",
                },
            ],
        )

    # Alice only sees bob
    await _check_invitations(
        alice_client,
        [
            {
                "token": bob_invitation_token,
                "created_on": ANY,
                "claimer_email": "bob@example.com",
                "status": "IDLE",
            },
        ],
    )

    # Bob only sees alice
    await _check_invitations(
        bob_client,
        [
            {
                "token": alice_invitation_token,
                "created_on": alice_invitation_created_on,
                "claimer_email": "alice@example.com",
                "status": "IDLE",
            },
        ],
    )

    # Delete user invitation
    response = await authenticated_client.delete(f"/invitations/{alice_invitation_token}")
    body = await response.get_json()
    assert response.status_code == 204
    assert body == {}

    # Bob now sees nothing
    await _check_invitations(bob_client, [])

    # Other clients see Bob's invitation
    for client in (alice_client, carl_client, diana_client):
        await _check_invitations(
            client,
            [
                {
                    "token": bob_invitation_token,
                    "created_on": ANY,
                    "claimer_email": "bob@example.com",
                    "status": "IDLE",
                },
            ],
        )

    # Deletion is not idempotent
    response = await authenticated_client.delete(f"/invitations/{alice_invitation_token}")
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "invitation_already_used"}


@pytest.mark.trio
async def test_create_invalid_type(authenticated_client: TestClientProtocol):
    # Delete user invitation
    response = await authenticated_client.post("/invitations", json={"type": "dummy"})
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_data", "fields": ["type"]}


@pytest.mark.trio
async def test_invite_already_existing_user(
    authenticated_client: TestClientProtocol, local_device: LocalDeviceTestbed
):
    # Delete user invitation
    response = await authenticated_client.post(
        "/invitations", json={"type": "user", "claimer_email": local_device.email}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "claimer_already_member"}


@pytest.mark.trio
async def test_delete_invalid_invitation_token(authenticated_client: TestClientProtocol):
    # Delete user invitation
    response = await authenticated_client.delete("/invitations/not_a_valid_uuid")
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_token"}


@pytest.mark.trio
async def test_shamir_recovery_invitations_claimer_not_a_member(
    authenticated_client: TestClientProtocol,
):
    response = await authenticated_client.post(
        "/invitations", json={"type": "shamir_recovery", "claimer_email": "billy@example.com"}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "claimer_not_a_member"}


@pytest.mark.trio
async def test_shamir_recovery_invitations_no_shamir_recovery_setup(
    authenticated_client: TestClientProtocol,
    bob_user,
):
    response = await authenticated_client.post(
        "/invitations", json={"type": "shamir_recovery", "claimer_email": "bob@example.com"}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "no_shamir_recovery_setup"}
