import pytest
from unittest.mock import ANY


@pytest.mark.trio
async def test_create_list_delete_users_invitations(authenticated_client):
    async def _check_invitations(expected_users):
        response = await authenticated_client.get("/invitations")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"users": expected_users, "device": None}
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
async def test_create_list_delete_device_invitation(authenticated_client):
    async def _check_invitations(expected_device):
        response = await authenticated_client.get("/invitations")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"users": [], "device": expected_device}
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
async def test_create_invalid_type(authenticated_client):
    # Delete user invitation
    response = await authenticated_client.post("/invitations", json={"type": "dummy"})
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_data", "fields": ["type"]}


@pytest.mark.trio
async def test_invite_already_existing_user(authenticated_client, local_device):
    # Delete user invitation
    response = await authenticated_client.post(
        "/invitations", json={"type": "user", "claimer_email": local_device.email}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "claimer_already_member"}


@pytest.mark.trio
async def test_delete_invalid_invitation_token(authenticated_client):
    # Delete user invitation
    response = await authenticated_client.delete("/invitations/not_a_valid_uuid")
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_token"}
