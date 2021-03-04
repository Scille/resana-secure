import trio
import pytest
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
async def test_claim_user(test_app, authenticated_client, user_invitation):
    claimer_client = test_app.test_client()
    greeter_sas_available = trio.Event()
    greeter_sas = None
    claimer_sas_available = trio.Event()
    claimer_sas = None

    async def _claimer():
        # Step 1
        response = await claimer_client.post(
            f"/invitations/{user_invitation.token}/claimer/1-wait-peer-ready"
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"type": "user", "candidate_greeter_sas": [ANY, ANY, ANY, ANY]}
        await greeter_sas_available.wait()
        assert greeter_sas in body["candidate_greeter_sas"]

        # Step 2

    async def _greeter():
        # Step 1
        response = await authenticated_client.post(
            f"/invitations/{user_invitation.token}/greeter/1-wait-peer-ready"
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"type": "user", "greeter_sas": ANY}
        nonlocal greeter_sas
        greeter_sas = body["greeter_sas"]
        greeter_sas_available.set()

        # Step 2

    with trio.fail_after(1):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(_claimer)
            nursery.start_soon(_greeter)
