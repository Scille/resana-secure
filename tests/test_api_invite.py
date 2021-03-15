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
@pytest.mark.parametrize("type", ["user", "device"])
async def test_claim_ok(test_app, local_device, authenticated_client, type):
    claimer_client = test_app.test_client()
    greeter_sas_available = trio.Event()
    greeter_sas = None
    claimer_sas_available = trio.Event()
    claimer_sas = None

    # First create the invitation
    if type == "user":
        claimer_email = "bob@example.com"
        response = await authenticated_client.post(
            "/invitations", json={"type": "user", "claimer_email": claimer_email}
        )
        body = await response.get_json()
        assert response.status_code == 200
        invitation = InvitationInfo("user", claimer_email, body["token"])
    else:
        response = await authenticated_client.post("/invitations", json={"type": "device"})
        body = await response.get_json()
        assert response.status_code == 200
        invitation = InvitationInfo("device", None, body["token"])

    new_device_email = (
        invitation.claimer_email if type == "user" else local_device.device.human_handle.email
    )
    new_device_key = b"P@ssw0rd."

    async def _claimer():
        nonlocal claimer_sas

        # Step 0
        response = await claimer_client.post(
            f"/invitations/{invitation.token}/claimer/0-retreive-info", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"type": type, "greeter_email": local_device.device.human_handle.email}

        # Step 1
        response = await claimer_client.post(
            f"/invitations/{invitation.token}/claimer/1-wait-peer-ready", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"candidate_greeter_sas": [ANY, ANY, ANY, ANY]}

        await greeter_sas_available.wait()
        assert greeter_sas in body["candidate_greeter_sas"]

        # Step 2
        response = await claimer_client.post(
            f"/invitations/{invitation.token}/claimer/2-check-trust",
            json={"greeter_sas": greeter_sas},
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"claimer_sas": ANY}
        claimer_sas = body["claimer_sas"]
        claimer_sas_available.set()

        # Step 3
        response = await claimer_client.post(
            f"/invitations/{invitation.token}/claimer/3-wait-peer-trust", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {}

        # Step 4
        response = await claimer_client.post(
            f"/invitations/{invitation.token}/claimer/4-finalize",
            json={"key": b64encode(new_device_key).decode("ascii")},
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {}

    async def _greeter():
        nonlocal greeter_sas

        # Step 1
        response = await authenticated_client.post(
            f"/invitations/{invitation.token}/greeter/1-wait-peer-ready", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        if type == "user":
            assert body == {"type": "user", "greeter_sas": ANY}
        else:
            assert body == {"type": "device", "greeter_sas": ANY}
        greeter_sas = body["greeter_sas"]
        greeter_sas_available.set()

        # Step 2
        response = await authenticated_client.post(
            f"/invitations/{invitation.token}/greeter/2-wait-peer-trust", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"candidate_claimer_sas": [ANY, ANY, ANY, ANY]}

        await claimer_sas_available.wait()
        assert claimer_sas in body["candidate_claimer_sas"]

        # Step 3
        response = await authenticated_client.post(
            f"/invitations/{invitation.token}/greeter/3-check-trust",
            json={"claimer_sas": claimer_sas},
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {}

        # Step 4
        if type == "user":
            json = {"granted_profile": "ADMIN", "claimer_email": invitation.claimer_email}
        else:
            json = {"granted_profile": "ADMIN"}
        response = await authenticated_client.post(
            f"/invitations/{invitation.token}/greeter/4-finalize", json=json
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

    # And the new user should be visible
    if type == "user":
        response = await authenticated_client.get("/humans")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {
            "total": 2,
            "users": [
                {
                    "created_on": ANY,
                    "human_handle": {"email": "bob@example.com", "label": "-unknown-"},
                    "profile": "ADMIN",
                    "revoked_on": None,
                    "user_id": ANY,
                },
                {
                    "created_on": ANY,
                    "human_handle": {"email": "alice@example.com", "label": "Alice"},
                    "profile": "ADMIN",
                    "revoked_on": None,
                    "user_id": ANY,
                },
            ],
        }

    # New user should be able to connect
    response = await claimer_client.post(
        "/auth", json={"email": new_device_email, "key": b64encode(new_device_key).decode("ascii")}
    )
    assert response.status_code == 200
