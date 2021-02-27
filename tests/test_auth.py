import pytest
import re
from base64 import b64encode


@pytest.mark.trio
async def test_authentication(test_app, local_device):
    test_client = test_app.test_client()

    # Test authenticated route without session token
    response = await test_client.get("/workspaces")
    assert response.status_code == 401

    # Now proceed to the auth
    response = await test_client.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": b64encode(local_device.key).decode("ascii"),
        },
    )
    assert response.status_code == 200
    assert len(response.headers.get_all("set-cookie")) == 1
    match = re.match(
        r"^session=([a-zA-Z0-9.\-_]+); HttpOnly; Path=/; SameSite=Strict$",
        response.headers.get("set-cookie"),
    )
    assert match is not None

    # Session token allow us to use the authenticated route
    response = await test_client.get("/workspaces")
    assert response.status_code == 200

    # Accessing authentication route without the session token is still not allowed
    test_client.cookie_jar.clear()
    response = await test_client.get("/workspaces")
    assert response.status_code == 401

    # Invalid token should be rejected
    dummy_session_cookie = "eyJsb2dnZWRfaW4iOiI1ODU5NWY1OTI1OTA0NGMyYTE1ODg4NGFlYzY5NGJkOCJ9.YDeKyQ.46LVu1VFkoZISHp-5xaXDK-sjDk"
    test_client.set_cookie(
        server_name="127.0.0.1", key="session", value=dummy_session_cookie
    )
    response = await test_client.get("/workspaces")
    assert response.status_code == 401


@pytest.mark.trio
async def test_authentication_unknown_email(test_app):
    test_client = test_app.test_client()

    response = await test_client.post(
        "/auth", json={"email": "john@doe.com", "key": ""}
    )
    assert response.status_code == 404


@pytest.mark.trio
async def test_authentication_bad_key(test_app, local_device):
    test_client = test_app.test_client()

    response = await test_client.post(
        "/auth", json={"email": local_device.email, "key": ""}
    )
    assert response.status_code == 404


@pytest.mark.trio
@pytest.mark.parametrize(
    "route,method",
    [
        ("/workspaces", "GET"),
        ("/workspaces", "POST"),
        ("/workspaces/sync", "POST"),
        ("/workspaces/c3acdcb2ede6437f89fb94da11d733f2", "PATCH"),
        ("/workspaces/c3acdcb2ede6437f89fb94da11d733f2/share", "GET"),
        ("/workspaces/c3acdcb2ede6437f89fb94da11d733f2/share", "PATCH"),
    ],
)
async def test_authenticated_routes(test_app, route, method):
    test_client = test_app.test_client()

    response = await getattr(test_client, method.lower())(route)
    assert response.status_code == 401
