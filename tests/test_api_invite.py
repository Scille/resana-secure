import trio
import pytest
from base64 import b64encode
from unittest.mock import ANY
from collections import namedtuple


InvitationInfo = namedtuple("InvitationInfo", "type,claimer_email,token")


@pytest.fixture
async def user_invitation(authenticated_client):
    claimer_email = "bob@example.com"
    response = await authenticated_client.post(
        "/invitations", json={"type": "user", "claimer_email": claimer_email}
    )
    body = await response.get_json()
    assert response.status_code == 200
    return InvitationInfo("user", claimer_email, body["token"])


@pytest.fixture
async def device_invitation(authenticated_client):
    response = await authenticated_client.post("/invitations", json={"type": "device"})
    body = await response.get_json()
    assert response.status_code == 200
    return InvitationInfo("device", None, body["token"])


@pytest.mark.trio
async def test_claim_user(test_app, local_device, authenticated_client, user_invitation):
    claimer_client = test_app.test_client()
    claimer_email = "bob@example.com"
    greeter_sas_available = trio.Event()
    greeter_sas = None
    claimer_sas_available = trio.Event()
    claimer_sas = None
    claimer_key = b"P@ssw0rd."

    async def _claimer():
        nonlocal claimer_sas

        # Step 0
        response = await claimer_client.post(
            f"/invitations/{user_invitation.token}/claimer/0-retreive-info", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"type": "user", "greeter_email": local_device.device.human_handle.email}

        # Step 1
        response = await claimer_client.post(
            f"/invitations/{user_invitation.token}/claimer/1-wait-peer-ready", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"candidate_greeter_sas": [ANY, ANY, ANY, ANY]}

        await greeter_sas_available.wait()
        assert greeter_sas in body["candidate_greeter_sas"]

        # Step 2
        response = await claimer_client.post(
            f"/invitations/{user_invitation.token}/claimer/2-check-trust",
            json={"greeter_sas": greeter_sas},
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"claimer_sas": ANY}
        claimer_sas = body["claimer_sas"]
        claimer_sas_available.set()

        # Step 3
        response = await claimer_client.post(
            f"/invitations/{user_invitation.token}/claimer/3-wait-peer-trust", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {}

        # Step 4
        response = await claimer_client.post(
            f"/invitations/{user_invitation.token}/claimer/4-finalize",
            json={"key": b64encode(claimer_key).decode("ascii")},
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {}

    async def _greeter():
        nonlocal greeter_sas

        # Step 1
        response = await authenticated_client.post(
            f"/invitations/{user_invitation.token}/greeter/1-wait-peer-ready", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"type": "user", "greeter_sas": ANY}
        greeter_sas = body["greeter_sas"]
        greeter_sas_available.set()

        # Step 2
        response = await authenticated_client.post(
            f"/invitations/{user_invitation.token}/greeter/2-wait-peer-trust", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"candidate_claimer_sas": [ANY, ANY, ANY, ANY]}

        await claimer_sas_available.wait()
        assert claimer_sas in body["candidate_claimer_sas"]

        # Step 3
        response = await authenticated_client.post(
            f"/invitations/{user_invitation.token}/greeter/3-check-trust",
            json={"claimer_sas": claimer_sas},
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {}

        # Step 4
        response = await authenticated_client.post(
            f"/invitations/{user_invitation.token}/greeter/4-finalize",
            json={"granted_profile": "ADMIN", "claimer_email": claimer_email},
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {}

    with trio.fail_after(1):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(_claimer)
            nursery.start_soon(_greeter)

    # Now the invitation should no longer be visible
    response = await authenticated_client.get("/invitations")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"users": [], "device": None}

    # # And the new user should be visible
    # response = await authenticated_client.get("/humans")
    # body = await response.get_json()
    # assert response.status_code == 200

    # New user should be able to connect
    response = await claimer_client.post(
        "/auth", json={"email": claimer_email, "key": b64encode(claimer_key).decode("ascii")}
    )
    assert response.status_code == 200
