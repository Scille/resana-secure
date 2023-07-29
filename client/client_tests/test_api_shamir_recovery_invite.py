import trio
import pytest
from base64 import b64encode

from .conftest import TestAppProtocol, TestClientProtocol, LocalDeviceTestbed


@pytest.mark.trio
@pytest.mark.parametrize(
    "alice_retrieves_before_finalize",
    (False, True),
    ids=("alice_does_not_retrieve_before_finalize", "alice_retrieves_before_finalize"),
)
@pytest.mark.parametrize(
    "alice_retrieves_before_next_recipient",
    (False, True),
    ids=("alice_does_not_retrieve_before_next_recipient", "alice_retrieves_before_next_recipient"),
)
async def test_shamir_recovery_claim(
    test_app: TestAppProtocol,
    authenticated_client: TestClientProtocol,
    bob_user: LocalDeviceTestbed,
    carl_user: LocalDeviceTestbed,
    diana_user: LocalDeviceTestbed,
    alice_retrieves_before_finalize: str,
    alice_retrieves_before_next_recipient: str,
):
    claimer_client = test_app.test_client()
    alice_client = authenticated_client
    bob_client = await bob_user.authenticated_client(test_app)
    carl_client = await carl_user.authenticated_client(test_app)
    diana_client = await diana_user.authenticated_client(test_app)

    # Alice create a new setup
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

    # Bob creates an invitation
    response = await bob_client.post(
        "/invitations", json={"type": "shamir_recovery", "claimer_email": "alice@example.com"}
    )
    body = await response.get_json()
    assert response.status_code == 200, body
    token = body["token"]

    # Carl list the invitations
    response = await carl_client.get("/invitations")
    body = await response.get_json()
    assert response.status_code == 200, body
    (invitation,) = body["shamir_recoveries"]
    assert invitation["token"] == token

    # Concurrent context for Alice + Carl and Alice + Diana
    async with trio.open_nursery() as nursery:
        carl_greeter_sas: str = ""
        alice_claimer_sas_1: str = ""
        alice_claimer_sas_2: str = ""
        alice_claimer_sas_1_ready = trio.Event()
        alice_claimer_sas_2_ready = trio.Event()
        carl_greeter_sas_ready = trio.Event()
        diana_greeter_sas_ready = trio.Event()
        first_alice_claim_done = trio.Event()
        carl_greet_done = trio.Event()

        async def carl_greets():
            nonlocal carl_greeter_sas

            response = await carl_client.post(f"/invitations/{token}/greeter/1-wait-peer-ready")
            body = await response.get_json()
            assert response.status_code == 200, body
            carl_greeter_sas = body["greeter_sas"]
            carl_greeter_sas_ready.set()

            response = await carl_client.post(f"/invitations/{token}/greeter/2-wait-peer-trust")
            body = await response.get_json()
            assert response.status_code == 200, body
            candidate_claimer_sas = body["candidate_claimer_sas"]
            await alice_claimer_sas_2_ready.wait()
            assert alice_claimer_sas_2 in candidate_claimer_sas

            response = await carl_client.post(
                f"/invitations/{token}/greeter/3-check-trust",
                json={"claimer_sas": alice_claimer_sas_2},
            )
            body = await response.get_json()
            assert response.status_code == 200, body
            assert body == {}

            response = await carl_client.post(
                f"/invitations/{token}/greeter/4-finalize",
            )
            body = await response.get_json()
            assert response.status_code == 200, body
            assert body == {}
            carl_greet_done.set()

        nursery.start_soon(carl_greets)

        # Alice starts the claimer process from a new machine
        response = await claimer_client.post(
            f"/invitations/{token}/claimer/0-retrieve-info", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {
            "type": "shamir_recovery",
            "threshold": 5,
            "enough_shares": False,
            "recipients": [
                {
                    "email": "bob@example.com",
                    "weight": 2,
                    "retrieved": False,
                },
                {
                    "email": "carl@example.com",
                    "weight": 3,
                    "retrieved": False,
                },
                {
                    "email": "diana@example.com",
                    "weight": 2,
                    "retrieved": False,
                },
            ],
        }

        # Alice decides to start with Diana

        async def alice_claims():
            nonlocal alice_claimer_sas_1

            response = await claimer_client.post(
                f"/invitations/{token}/claimer/1-wait-peer-ready",
                json={"greeter_email": "diana@example.com"},
            )
            body = await response.get_json()
            assert response.status_code == 200, body
            candidate_greeter_sas = body["candidate_greeter_sas"]
            await diana_greeter_sas_ready.wait()
            assert diana_greeter_sas in candidate_greeter_sas

            response = await claimer_client.post(
                f"/invitations/{token}/claimer/2-check-trust",
                json={"greeter_sas": diana_greeter_sas},
            )
            body = await response.get_json()
            assert response.status_code == 200, body
            alice_claimer_sas_1 = body["claimer_sas"]
            alice_claimer_sas_1_ready.set()

            response = await claimer_client.post(
                f"/invitations/{token}/claimer/3-wait-peer-trust",
            )
            body = await response.get_json()
            assert response.status_code == 200, body
            assert not body["enough_shares"]

            first_alice_claim_done.set()

        nursery.start_soon(alice_claims)

        # Diana joins the party
        response = await diana_client.get("/invitations")
        body = await response.get_json()
        assert response.status_code == 200, body
        (invitation,) = body["shamir_recoveries"]
        assert invitation["token"] == token

        response = await diana_client.post(f"/invitations/{token}/greeter/1-wait-peer-ready")
        body = await response.get_json()
        assert response.status_code == 200, body
        assert body["type"] == "shamir_recovery"
        diana_greeter_sas = body["greeter_sas"]
        diana_greeter_sas_ready.set()

        # Bob is drunk
        # Make sure he cannot interfere with diana's invite, even on the same app
        response = await bob_client.post(f"/invitations/{token}/greeter/2-wait-peer-trust")
        body = await response.get_json()
        assert response.status_code == 409, body

        response = await diana_client.post(f"/invitations/{token}/greeter/2-wait-peer-trust")
        body = await response.get_json()
        assert response.status_code == 200, body
        candidate_claimer_sas = body["candidate_claimer_sas"]
        await alice_claimer_sas_1_ready.wait()
        assert alice_claimer_sas_1 in candidate_claimer_sas

        response = await diana_client.post(
            f"/invitations/{token}/greeter/3-check-trust", json={"claimer_sas": alice_claimer_sas_1}
        )
        body = await response.get_json()
        assert response.status_code == 200, body
        assert body == {}

        response = await diana_client.post(
            f"/invitations/{token}/greeter/4-finalize",
        )
        body = await response.get_json()
        assert response.status_code == 200, body
        assert body == {}

        await first_alice_claim_done.wait()

        # Diana is done, Alice might or might not get back to step 0
        if alice_retrieves_before_next_recipient:
            response = await claimer_client.post(
                f"/invitations/{token}/claimer/0-retrieve-info", json={}
            )
            body = await response.get_json()
            assert response.status_code == 200
            assert body == {
                "type": "shamir_recovery",
                "threshold": 5,
                "enough_shares": False,
                "recipients": [
                    {
                        "email": "bob@example.com",
                        "weight": 2,
                        "retrieved": False,
                    },
                    {
                        "email": "carl@example.com",
                        "weight": 3,
                        "retrieved": False,
                    },
                    {
                        "email": "diana@example.com",
                        "weight": 2,
                        "retrieved": True,
                    },
                ],
            }

        # Alice continues with Carl who is still waiting
        response = await claimer_client.post(
            f"/invitations/{token}/claimer/1-wait-peer-ready",
            json={"greeter_email": "carl@example.com"},
        )
        body = await response.get_json()
        assert response.status_code == 200, body
        candidate_greeter_sas = body["candidate_greeter_sas"]
        await carl_greeter_sas_ready.wait()
        assert carl_greeter_sas in candidate_greeter_sas

        response = await claimer_client.post(
            f"/invitations/{token}/claimer/2-check-trust", json={"greeter_sas": carl_greeter_sas}
        )
        body = await response.get_json()
        assert response.status_code == 200, body
        alice_claimer_sas_2 = body["claimer_sas"]
        alice_claimer_sas_2_ready.set()

        response = await claimer_client.post(
            f"/invitations/{token}/claimer/3-wait-peer-trust",
        )
        body = await response.get_json()
        assert response.status_code == 200, body
        assert body["enough_shares"]
        await carl_greet_done.wait()

    if alice_retrieves_before_finalize:
        response = await claimer_client.post(
            f"/invitations/{token}/claimer/0-retrieve-info", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {
            "type": "shamir_recovery",
            "threshold": 5,
            "enough_shares": True,
            "recipients": [
                {
                    "email": "bob@example.com",
                    "weight": 2,
                    "retrieved": False,
                },
                {
                    "email": "carl@example.com",
                    "weight": 3,
                    "retrieved": True,
                },
                {
                    "email": "diana@example.com",
                    "weight": 2,
                    "retrieved": True,
                },
            ],
        }

    # Alice has enough shares to finalize
    new_password = "my-brand-new-password"
    new_password_b64 = b64encode(new_password.encode()).decode("ascii")
    response = await claimer_client.post(
        f"/invitations/{token}/claimer/4-finalize",
        json={"key": new_password_b64},
    )
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}

    # The invitation has been deleted
    response = await carl_client.get("/invitations")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body["shamir_recoveries"] == []

    # Alice can log with her new device
    test_client = test_app.test_client()

    response = await test_client.post(
        "/auth",
        json={
            "email": "alice@example.com",
            "key": new_password_b64,
            "organization": bob_user.organization.str,
        },
    )
    assert response.status_code == 200


@pytest.mark.trio
async def test_shamir_recovery_claim_retrieve_info_interrupts_ongoing_operation(
    test_app: TestAppProtocol,
    authenticated_client: TestClientProtocol,
    bob_user: LocalDeviceTestbed,
    carl_user: LocalDeviceTestbed,
):
    claimer_client = test_app.test_client()
    alice_client = authenticated_client
    bob_client = await bob_user.authenticated_client(test_app)
    carl_client = await carl_user.authenticated_client(test_app)

    # Alice create a new setup
    json = {
        "threshold": 2,
        "recipients": [
            {"email": "bob@example.com", "weight": 1},
            {"email": "carl@example.com", "weight": 1},
        ],
    }
    response = await alice_client.post("/recovery/shamir/setup", json=json)
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Bob creates an invitation
    response = await bob_client.post(
        "/invitations", json={"type": "shamir_recovery", "claimer_email": "alice@example.com"}
    )
    body = await response.get_json()
    assert response.status_code == 200, body
    token = body["token"]

    # Carl list the invitations
    response = await carl_client.get("/invitations")
    body = await response.get_json()
    assert response.status_code == 200, body
    (invitation,) = body["shamir_recoveries"]
    assert invitation["token"] == token

    # Alice retrieves the info
    response = await claimer_client.post(f"/invitations/{token}/claimer/0-retrieve-info", json={})
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "type": "shamir_recovery",
        "threshold": 2,
        "enough_shares": False,
        "recipients": [
            {
                "email": "bob@example.com",
                "weight": 1,
                "retrieved": False,
            },
            {
                "email": "carl@example.com",
                "weight": 1,
                "retrieved": False,
            },
        ],
    }

    # Greet/claim process
    async with trio.open_nursery() as nursery:
        carl_greeter_sas: str = ""
        alice_claimer_sas: str = ""
        carl_greeter_sas_ready = trio.Event()
        alice_claimer_sas_ready = trio.Event()
        alice_waits_for_peer_trust = trio.Event()

        async def alice_claims():
            nonlocal alice_claimer_sas

            response = await claimer_client.post(
                f"/invitations/{token}/claimer/1-wait-peer-ready",
                json={"greeter_email": "carl@example.com"},
            )
            body = await response.get_json()
            assert response.status_code == 200, body
            candidate_greeter_sas = body["candidate_greeter_sas"]

            await carl_greeter_sas_ready.wait()
            assert carl_greeter_sas in candidate_greeter_sas

            response = await claimer_client.post(
                f"/invitations/{token}/claimer/2-check-trust",
                json={"greeter_sas": carl_greeter_sas},
            )
            body = await response.get_json()
            assert response.status_code == 200, body
            alice_claimer_sas = body["claimer_sas"]
            alice_claimer_sas_ready.set()

            alice_waits_for_peer_trust.set()
            response = await claimer_client.post(
                f"/invitations/{token}/claimer/3-wait-peer-trust",
            )
            body = await response.get_json()

            # The step 3 has been interrupted
            assert response.status_code == 409, body
            assert body == {"error": "invalid_state"}

        async def carl_greets():
            nonlocal carl_greeter_sas

            response = await carl_client.post(f"/invitations/{token}/greeter/1-wait-peer-ready")
            body = await response.get_json()
            assert response.status_code == 200, body
            carl_greeter_sas = body["greeter_sas"]
            carl_greeter_sas_ready.set()

            response = await carl_client.post(f"/invitations/{token}/greeter/2-wait-peer-trust")
            body = await response.get_json()
            assert response.status_code == 200, body

        nursery.start_soon(alice_claims)
        nursery.start_soon(carl_greets)

        # Make sure `3-wait-peer-trust` starts first
        await alice_waits_for_peer_trust.wait()
        await trio.sleep(0.01)

        # Alice should be able to perform a new step 0 to reset the process
        response = await claimer_client.post(
            f"/invitations/{token}/claimer/0-retrieve-info", json={}
        )
        body = await response.get_json()
        assert response.status_code == 200
