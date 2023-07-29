from typing import Optional
from unittest.mock import ANY

import pytest
import trio
from quart.typing import TestAppProtocol, TestClientProtocol


class HumansTestBed:
    def __init__(self, test_app: TestAppProtocol, authenticated_client: TestClientProtocol):
        self.test_app = test_app
        self.authenticated_client = authenticated_client

    async def new_device(self, key: str):
        # First create the invitation
        response = await self.authenticated_client.post("/invitations", json={"type": "device"})
        body = await response.get_json()
        assert response.status_code == 200
        # Then do the actual claim/greet
        await self._do_invite(invitation_token=body["token"], key=key, claimer_email=None)

    async def new_user(self, email: str, key: str):
        # First create the invitation
        response = await self.authenticated_client.post(
            "/invitations", json={"type": "user", "claimer_email": email}
        )
        body = await response.get_json()
        assert response.status_code == 200
        # Then do the actual claim/greet
        await self._do_invite(invitation_token=body["token"], key=key, claimer_email=email)

    async def _do_invite(self, invitation_token: str, key: str, claimer_email: Optional[str]):
        claimer_client = self.test_app.test_client()
        greeter_sas_available = trio.Event()
        greeter_sas = None
        claimer_sas_available = trio.Event()
        claimer_sas = None

        async def _claimer():
            nonlocal claimer_sas

            # Step 0
            response = await claimer_client.post(
                f"/invitations/{invitation_token}/claimer/0-retrieve-info", json={}
            )
            assert response.status_code == 200

            # Step 1
            response = await claimer_client.post(
                f"/invitations/{invitation_token}/claimer/1-wait-peer-ready", json={}
            )
            assert response.status_code == 200

            await greeter_sas_available.wait()

            # Step 2
            response = await claimer_client.post(
                f"/invitations/{invitation_token}/claimer/2-check-trust",
                json={"greeter_sas": greeter_sas},
            )
            body = await response.get_json()
            assert response.status_code == 200
            claimer_sas = body["claimer_sas"]
            claimer_sas_available.set()

            # Step 3
            response = await claimer_client.post(
                f"/invitations/{invitation_token}/claimer/3-wait-peer-trust", json={}
            )
            assert response.status_code == 200

            # Step 4
            response = await claimer_client.post(
                f"/invitations/{invitation_token}/claimer/4-finalize", json={"key": key}
            )
            assert response.status_code == 200

        async def _greeter():
            nonlocal greeter_sas

            # Step 1
            response = await self.authenticated_client.post(
                f"/invitations/{invitation_token}/greeter/1-wait-peer-ready", json={}
            )
            body = await response.get_json()
            assert response.status_code == 200
            greeter_sas = body["greeter_sas"]
            greeter_sas_available.set()

            # Step 2
            response = await self.authenticated_client.post(
                f"/invitations/{invitation_token}/greeter/2-wait-peer-trust", json={}
            )
            assert response.status_code == 200

            await claimer_sas_available.wait()

            # Step 3
            response = await self.authenticated_client.post(
                f"/invitations/{invitation_token}/greeter/3-check-trust",
                json={"claimer_sas": claimer_sas},
            )
            assert response.status_code == 200

            # Step 4
            if claimer_email:
                json = {"granted_profile": "ADMIN", "claimer_email": claimer_email}
            else:
                json = {}
            response = await self.authenticated_client.post(
                f"/invitations/{invitation_token}/greeter/4-finalize", json=json
            )
            assert response.status_code == 200

        with trio.fail_after(1):
            async with trio.open_nursery() as nursery:
                nursery.start_soon(_claimer)
                nursery.start_soon(_greeter)


@pytest.fixture()
async def testbed(test_app: TestAppProtocol, authenticated_client: TestClientProtocol):
    return HumansTestBed(test_app, authenticated_client)


@pytest.mark.trio
async def test_find_and_revoke_humans(
    testbed: HumansTestBed, authenticated_client: TestClientProtocol
):
    await testbed.new_user(email="bob@example.com", key="P@ssw0rd.")
    await testbed.new_user(email="bob2@example.com", key="P@ssw0rd.")
    await testbed.new_user(email="mallory@example.com", key="P@ssw0rd.")
    await testbed.new_device(key="P@ssw0rd.")

    # List all humans
    response = await authenticated_client.get("/humans")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "total": 4,
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
                "human_handle": {"email": "bob2@example.com", "label": "-unknown-"},
                "profile": "ADMIN",
                "revoked_on": None,
                "user_id": ANY,
            },
            {
                "created_on": ANY,
                "human_handle": {"email": "mallory@example.com", "label": "-unknown-"},
                "profile": "ADMIN",
                "revoked_on": ANY,
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
    users = {x["human_handle"]["email"]: x for x in body["users"]}

    # Filter the view on humans
    response = await authenticated_client.get("/humans?query=bob")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "total": 2,
        "users": [
            {
                "created_on": users["bob@example.com"]["created_on"],
                "human_handle": {"email": "bob@example.com", "label": "-unknown-"},
                "profile": "ADMIN",
                "revoked_on": None,
                "user_id": users["bob@example.com"]["user_id"],
            },
            {
                "created_on": users["bob2@example.com"]["created_on"],
                "human_handle": {"email": "bob2@example.com", "label": "-unknown-"},
                "profile": "ADMIN",
                "revoked_on": None,
                "user_id": users["bob2@example.com"]["user_id"],
            },
        ],
    }

    # Revoke a user
    response = await authenticated_client.post("/humans/bob@example.com/revoke", json={})
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Check the user is revoked
    response = await authenticated_client.get("/humans")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "total": 4,
        "users": [
            {
                "created_on": users["bob@example.com"]["created_on"],
                "human_handle": {"email": "bob@example.com", "label": "-unknown-"},
                "profile": "ADMIN",
                "revoked_on": ANY,
                "user_id": users["bob@example.com"]["user_id"],
            },
            {
                "created_on": users["bob2@example.com"]["created_on"],
                "human_handle": {"email": "bob2@example.com", "label": "-unknown-"},
                "profile": "ADMIN",
                "revoked_on": None,
                "user_id": users["bob2@example.com"]["user_id"],
            },
            {
                "created_on": users["mallory@example.com"]["created_on"],
                "human_handle": {"email": "mallory@example.com", "label": "-unknown-"},
                "profile": "ADMIN",
                "revoked_on": None,
                "user_id": users["mallory@example.com"]["user_id"],
            },
            {
                "created_on": users["alice@example.com"]["created_on"],
                "human_handle": {"email": "alice@example.com", "label": "Alice"},
                "profile": "ADMIN",
                "revoked_on": users["alice@example.com"]["revoked_on"],
                "user_id": users["alice@example.com"]["user_id"],
            },
        ],
    }
    assert isinstance(body["users"][0]["revoked_on"], str)

    # Check the user is revoked
    response = await authenticated_client.get("/humans?omit_revoked=true")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "total": 3,
        "users": [
            {
                "created_on": users["bob2@example.com"]["created_on"],
                "human_handle": {"email": "bob2@example.com", "label": "-unknown-"},
                "profile": "ADMIN",
                "revoked_on": None,
                "user_id": users["bob2@example.com"]["user_id"],
            },
            {
                "created_on": users["mallory@example.com"]["created_on"],
                "human_handle": {"email": "mallory@example.com", "label": "-unknown-"},
                "profile": "ADMIN",
                "revoked_on": None,
                "user_id": users["mallory@example.com"]["user_id"],
            },
            {
                "created_on": users["alice@example.com"]["created_on"],
                "human_handle": {"email": "alice@example.com", "label": "Alice"},
                "profile": "ADMIN",
                "revoked_on": users["alice@example.com"]["revoked_on"],
                "user_id": users["alice@example.com"]["user_id"],
            },
        ],
    }


@pytest.mark.trio
@pytest.mark.parametrize(
    "bad_param", ["page=dummy", "page=", "per_page=dummy", "per_page=", "omit_revoked=dummy"]
)
async def test_bad_find_humans(authenticated_client: TestClientProtocol, bad_param: str):
    response = await authenticated_client.get(f"/humans?{bad_param}")
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_arguments", "fields": ANY}


@pytest.mark.trio
async def test_revoke_unknown(authenticated_client: TestClientProtocol):
    response = await authenticated_client.post("/humans/unknown@example.com/revoke", json={})
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_email"}
