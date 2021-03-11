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
        json={"email": local_device.email, "key": b64encode(local_device.key).decode("ascii")},
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
    test_client.set_cookie(server_name="127.0.0.1", key="session", value=dummy_session_cookie)
    response = await test_client.get("/workspaces")
    assert response.status_code == 401


@pytest.mark.trio
async def test_authentication_unknown_email(test_app):
    test_client = test_app.test_client()

    response = await test_client.post("/auth", json={"email": "john@doe.com", "key": ""})
    assert response.status_code == 404


@pytest.mark.trio
async def test_authentication_bad_key(test_app, local_device):
    test_client = test_app.test_client()

    response = await test_client.post("/auth", json={"email": local_device.email, "key": ""})
    assert response.status_code == 404


@pytest.mark.trio
async def test_authentication_body_not_json(test_app, local_device):
    test_client = test_app.test_client()
    response = await test_client.post("/auth")
    assert response.status_code == 400


@pytest.fixture
def routes_samples(test_app):
    default_args_values = {
        "workspace_id": "c3acdcb2ede6437f89fb94da11d733f2",
        "file_id": "c0f0b18ee7634d01bd7ae9533d1222ef",
        "folder_id": "c0f0b18ee7634d01bd7ae9533d1222ef",
        "entry_id": "c0f0b18ee7634d01bd7ae9533d1222ef",
        "subpath": "foo/bar",  # TODO
        "apitoken": "7a0a3d1038bb4a22ba6d310abcc198d4",
    }
    routes = []
    for rule in test_app.app.url_map.iter_rules():
        args = {key: default_args_values[key] for key in rule.arguments}
        _, route = rule.build(args)
        for rule_method in rule.methods:
            routes.append((rule_method, route))
    return routes


@pytest.mark.trio
async def test_authenticated_routes(test_app, routes_samples):
    for method, route in routes_samples:
        if method == "OPTIONS":
            continue
        if "/claimer/" in route:
            continue
        test_client = test_app.test_client()
        response = await getattr(test_client, method.lower())(route)
        if route == "/":
            assert response.status_code == 200
        elif route == "/auth":
            assert response.status_code == 400
        else:
            assert response.status_code == 401


@pytest.mark.trio
async def test_cors_routes(test_app, client_origin, routes_samples):
    test_client = test_app.test_client()
    for method, route in routes_samples:
        if method == "OPTIONS":
            continue
        response = await test_client.options(
            route, headers={"Origin": client_origin, "Access-Control-Request-Method": method}
        )
        assert response.status_code == 200
        assert response.headers.get("Access-Control-Allow-Origin") == client_origin
        assert response.headers.get("Access-Control-Allow-Credentials") == "true"
        assert (
            response.headers.get("Access-Control-Allow-Methods")
            == "GET, HEAD, POST, OPTIONS, PUT, PATCH, DELETE"
        )

        # Test with bad origin
        response = await test_client.options(
            route, headers={"Origin": "https://dummy.org", "Access-Control-Request-Method": method}
        )
        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" not in response.headers
