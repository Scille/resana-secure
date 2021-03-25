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


@pytest.mark.trio
async def test_invalid_state(test_app, local_device, authenticated_client, device_invitation):
    claimer_client = test_app.test_client()
    token = device_invitation.token

    for url, json, client in [
        (f"/invitations/{token}/claimer/1-wait-peer-ready", {}, claimer_client),
        (f"/invitations/{token}/claimer/2-check-trust", {"greeter_sas": "ABCD"}, claimer_client),
        (f"/invitations/{token}/claimer/3-wait-peer-trust", {}, claimer_client),
        (f"/invitations/{token}/claimer/4-finalize", {"key": "Zm9v"}, claimer_client),
        (f"/invitations/{token}/greeter/2-wait-peer-trust", {}, authenticated_client),
        (
            f"/invitations/{token}/greeter/3-check-trust",
            {"claimer_sas": "ABCD"},
            authenticated_client,
        ),
        (f"/invitations/{token}/greeter/4-finalize", {}, authenticated_client),
    ]:
        with trio.fail_after(1):
            response = await client.post(url, json=json)
            body = await response.get_json()
            assert response.status_code == 409
            assert body == {"error": "invalid_state"}


@pytest.mark.trio
async def test_concurrent_requests_on_steps_0_and_1(
    test_app, authenticated_client, device_invitation
):
    claimer_done = 0

    with trio.fail_after(1):
        async with trio.open_nursery() as nursery:

            async def _claimer():
                nonlocal claimer_done
                claimer_client = test_app.test_client()
                response = await claimer_client.post(
                    f"/invitations/{device_invitation.token}/claimer/0-retreive-info", json={}
                )
                assert response.status_code == 200
                response = await claimer_client.post(
                    f"/invitations/{device_invitation.token}/claimer/1-wait-peer-ready", json={}
                )

                claimer_done += 1
                if claimer_client == 9:
                    # Our request has been cancelled by the last claimer
                    assert response.status_code == 409
                    # Act as the greeter so that the last remaining claimer
                    # won't be waiting forever
                    response = await authenticated_client.post(
                        f"/invitations/{device_invitation.token}/greeter/1-wait-peer-ready", json={}
                    )
                    assert response.status_code == 200

                elif claimer_client == 10:
                    # We are the last claimer
                    response.status_code == 200

                else:
                    # Our request has been cancelled by another claimer
                    assert response.status_code == 409

            for _ in range(10):
                nursery.start_soon(_claimer)

    assert claimer_done == 10


@pytest.mark.trio
async def test_cancel_step_request_then_retry(test_app, authenticated_client, device_invitation):
    claimer_client = test_app.test_client()

    # Step 0

    response = await claimer_client.post(
        f"/invitations/{device_invitation.token}/claimer/0-retreive-info", json={}
    )
    assert response.status_code == 200

    # Step 1

    async def _greeter(expected_status_code):
        response = await authenticated_client.post(
            f"/invitations/{device_invitation.token}/greeter/1-wait-peer-ready", json={}
        )
        assert response.status_code == expected_status_code

    async def _claimer():
        response = await claimer_client.post(
            f"/invitations/{device_invitation.token}/claimer/1-wait-peer-ready", json={}
        )
        body = await response.get_json()
        return response.status_code, body

    # Step 1, but cancelled before the end

    async with trio.open_nursery() as nursery:
        nursery.start_soon(_claimer)
        # Wait until request starts waiting for greeter to arrive
        await trio.testing.wait_all_tasks_blocked()
        nursery.cancel_scope.cancel()

    # Now retry the step 1, shouldn't succeed due to invalid state, but shouldn't cause deadlock either !

    with trio.fail_after(1):
        async with trio.open_nursery() as nursery:
            nursery.start_soon(_greeter, 409)
            status_code, body = (
                await _claimer()
            )  # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<< deadlock from here
            assert status_code == 409
            nursery.cancel_scope.cancel()

    # Go back to step 0, then retry step 1. This time everything should run fine.

    with trio.fail_after(1):
        async with trio.open_nursery() as nursery:
            # Greeter can start before we go back to step 0
            nursery.start_soon(_greeter, 200)

            response = await claimer_client.post(
                f"/invitations/{device_invitation.token}/claimer/0-retreive-info", json={}
            )
            assert response.status_code == 200

            status_code, body = await _claimer()
            assert status_code == 200
