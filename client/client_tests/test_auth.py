import pytest
import re
from typing import List, Tuple, cast
from unittest.mock import ANY
from quart_trio.testing import TrioTestApp

from parsec.api.protocol import OrganizationID
from parsec.backend import BackendApp
from parsec.core.types import BackendAddr, BackendOrganizationBootstrapAddr
from parsec.core.local_device import list_available_devices

from .conftest import LocalDeviceTestbed

from resana_secure.cores_manager import (
    CoresManager,
    CoreDeviceInvalidPasswordError,
    CoreDeviceNotFoundError,
    CoreDeviceEncryptedKeyNotFoundError,
)
from resana_secure.app import ResanaApp
from resana_secure.crypto import encrypt_parsec_key


@pytest.mark.trio
async def test_authentication(test_app: TrioTestApp, local_device: LocalDeviceTestbed):
    test_client = test_app.test_client()

    # Test authenticated route without session token
    response = await test_client.get("/workspaces")
    body = await response.get_json()
    assert response.status_code == 401
    assert body == {"error": "authentication_requested"}

    # Now proceed to the auth
    response = await test_client.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": local_device.key,
            "organization": local_device.organization.str,
        },
    )
    body = await response.get_json()
    assert response.status_code == 200
    # Auth token is provided by the api...
    assert body == {"token": ANY}
    auth_token = body["token"]
    assert isinstance(auth_token, str)
    # ...and also set as cookie
    assert len(response.headers.get_all("set-cookie")) == 1
    match = re.match(
        r"^session=([a-zA-Z0-9.\-_]+); HttpOnly; Path=/; SameSite=Strict$",
        response.headers["set-cookie"],
    )
    assert match is not None

    # Session token allow us to use the authenticated route
    response = await test_client.get("/workspaces")
    assert response.status_code == 200

    # Accessing authentication route without the session token is still not allowed
    assert test_client.cookie_jar is not None
    test_client.cookie_jar.clear()
    response = await test_client.get("/workspaces")
    assert response.status_code == 401

    # Auth token allow us to use the authenticated route
    response = await test_client.get(
        "/workspaces", headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 200

    # Invalid token should be rejected
    response = await test_client.get("/workspaces", headers={"Authorization": "Bearer dummy"})
    assert response.status_code == 401

    dummy_session_cookie = "eyJsb2dnZWRfaW4iOiI1ODU5NWY1OTI1OTA0NGMyYTE1ODg4NGFlYzY5NGJkOCJ9.YDeKyQ.46LVu1VFkoZISHp-5xaXDK-sjDk"
    test_client.set_cookie(server_name="127.0.0.1", key="session", value=dummy_session_cookie)
    response = await test_client.get("/workspaces")
    assert response.status_code == 401


@pytest.mark.trio
async def test_multi_authentication(test_app: TrioTestApp, local_device: LocalDeviceTestbed):
    test_client = test_app.test_client()

    # First auth
    response = await test_client.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": local_device.key,
            "organization": local_device.organization.str,
        },
    )
    body = await response.get_json()
    assert response.status_code == 200
    token = body["token"]

    # Additional auth, should return the same token
    response = await test_client.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": local_device.key,
            "organization": local_device.organization.str,
        },
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body["token"] == token

    # Additional auth, but with invalid key
    response = await test_client.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": f"{local_device.key}dummy",
            "organization": local_device.organization.str,
        },
    )
    body = await response.get_json()
    assert response.status_code == 400

    # logout
    response = await test_client.delete("/auth")
    body = await response.get_json()
    assert response.status_code == 200
    # Cookie should be removed
    assert len(response.headers.get_all("set-cookie")) == 1
    assert (
        response.headers.get("set-cookie")
        == "session=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/"
    )


@pytest.mark.trio
async def test_logout_without_auth(test_app: TrioTestApp):
    test_client = test_app.test_client()

    response = await test_client.delete("/auth")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}


@pytest.mark.trio
async def test_logout_without_session_cookie(
    test_app: TrioTestApp, local_device: LocalDeviceTestbed
):
    # This client will contain the session cookie as soon as the auth query is done
    test_client_with_cookie = test_app.test_client()
    response = await test_client_with_cookie.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": local_device.key,
            "organization": local_device.organization.str,
        },
    )
    body = await response.get_json()
    assert response.status_code == 200
    auth_token = body["token"]

    test_client_without_cookie = test_app.test_client()
    response = await test_client_without_cookie.delete(
        "/auth", headers={"Authorization": f"Bearer {auth_token}"}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    response = await test_client_without_cookie.get(
        "/workspaces", headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 401
    response = await test_client_with_cookie.get(
        "/workspaces", headers={"Authorization": f"Bearer {auth_token}"}
    )
    assert response.status_code == 401


@pytest.mark.trio
async def test_authentication_unknown_email(
    test_app: TrioTestApp, local_device: LocalDeviceTestbed
):
    test_client = test_app.test_client()
    response = await test_client.post(
        "/auth",
        json={
            "email": "john@doe.com",
            "key": "",
            "organization": local_device.organization.str,
        },
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "device_not_found"}


@pytest.mark.trio
async def test_authentication_bad_key(test_app: TrioTestApp, local_device: LocalDeviceTestbed):
    test_client = test_app.test_client()
    response = await test_client.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": "",
            "organization": local_device.organization.str,
        },
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_key"}


@pytest.mark.trio
async def test_authentication_missing_organization_id(
    test_app: TrioTestApp, local_device: LocalDeviceTestbed
):
    # OrgID is not mandatory for now, so this should work
    test_client = test_app.test_client()
    response = await test_client.post(
        "/auth",
        json={"email": local_device.email, "key": local_device.key},
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"token": ANY}
    token = body["token"]

    # Try with the org
    response = await test_client.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": local_device.key,
            "organization": local_device.organization.str,
        },
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"token": ANY}

    assert body["token"] == token


@pytest.mark.trio
async def test_authentication_bad_organization_id(
    test_app: TrioTestApp, local_device: LocalDeviceTestbed
):
    test_client = test_app.test_client()
    response = await test_client.post(
        "/auth",
        json={"email": local_device.email, "key": local_device.key, "organization": ""},
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_data", "fields": ["organization"]}

    response = await test_client.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": local_device.key,
            "organization": "Not a valid org id",
        },
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_data", "fields": ["organization"]}


@pytest.mark.trio
async def test_authentication_unknown_organization_id(
    test_app: TrioTestApp, local_device: LocalDeviceTestbed
):
    test_client = test_app.test_client()
    response = await test_client.post(
        "/auth",
        json={
            "email": local_device.email,
            "key": local_device.key,
            "organization": "UnknownOrg",
        },
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "device_not_found"}


@pytest.mark.trio
@pytest.mark.parametrize("kind", ["missing_header", "bad_header", "bad_body", "missing_body"])
async def test_authentication_body_not_json(test_app: TrioTestApp, kind: str):
    test_client = test_app.test_client()
    if kind == "missing_body":
        data = None
    elif kind == "bad_body":
        data = b"<not_json>"
    else:
        data = b"{}"
    if kind == "missing_header":
        headers = {}
    elif kind == "bad_header":
        headers = {"Content-Type": "application/dummy"}
    else:
        headers = {"Content-Type": "application/json"}
    response = await test_client.post("/auth", headers=headers, data=data)
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "json_body_expected"}


@pytest.fixture
def routes_samples(test_app: TrioTestApp):
    default_args_values = {
        "workspace_id": "c3acdcb2ede6437f89fb94da11d733f2",
        "file_id": "c0f0b18ee7634d01bd7ae9533d1222ef",
        "folder_id": "c0f0b18ee7634d01bd7ae9533d1222ef",
        "entry_id": "c0f0b18ee7634d01bd7ae9533d1222ef",
        "subpath": "foo/bar",  # TODO
        "apitoken": "7a0a3d1038bb4a22ba6d310abcc198d4",
        "email": "bob@example.com",
    }
    routes = []
    for rule in test_app.app.url_map.iter_rules():
        args = {key: default_args_values[key] for key in rule.arguments}
        url = rule.build(args)
        assert url is not None
        _, route = url
        assert rule.methods is not None
        for rule_method in rule.methods:
            routes.append((rule_method, route))
    return routes


@pytest.mark.trio
async def test_authenticated_routes(test_app: TrioTestApp, routes_samples: List[Tuple[str, str]]):
    for method, route in routes_samples:
        if method == "OPTIONS":
            continue
        if "/claimer/" in route:
            continue
        if route == "/recovery/import":
            continue
        test_client = test_app.test_client()
        response = await getattr(test_client, method.lower())(route)
        if route == "/" and method in ("GET", "HEAD"):
            assert response.status_code == 200
        elif route == "/auth" and method == "POST":
            assert response.status_code == 400
        elif route == "/organization/bootstrap" and method == "POST":
            assert response.status_code == 400
        elif route == "/auth" and method == "DELETE":
            assert response.status_code == 200
        else:
            assert response.status_code == 401


@pytest.mark.trio
async def test_cors_routes(
    test_app: TrioTestApp, client_origin: str, routes_samples: List[Tuple[str, str]]
):
    test_client = test_app.test_client()
    for method, route in routes_samples:
        if method == "OPTIONS":
            continue
        response = await test_client.options(
            route,
            headers={"Origin": client_origin, "Access-Control-Request-Method": method},
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
            route,
            headers={
                "Origin": "https://dummy.org",
                "Access-Control-Request-Method": method,
            },
        )
        assert response.status_code == 200
        assert "Access-Control-Allow-Origin" not in response.headers


@pytest.mark.trio
async def test_multi_org_authentication(
    test_app: TrioTestApp, backend_addr: BackendAddr, running_backend: BackendApp
):
    test_client = test_app.test_client()

    ORG_IDS = [OrganizationID("Org1"), OrganizationID("Org2"), OrganizationID("Org3")]
    EMAIL = "gordon.freeman@blackmesa.nm"
    PASSWORD = "abcd"

    addrs = [BackendOrganizationBootstrapAddr.build(backend_addr, org_id) for org_id in ORG_IDS]

    # Create 3 different orgs using the same email
    for backend_addr in addrs:
        response = await test_client.post(
            "/organization/bootstrap",
            json={
                "organization_url": backend_addr.to_url(),
                "email": EMAIL,
                "key": PASSWORD,
            },
        )

    assert response.status_code == 200

    tokens = []
    # If everything goes according to plan, each auth should return
    # a different token
    for org_id in ORG_IDS:
        response = await test_client.post(
            "/auth",
            json={
                "email": EMAIL,
                "key": PASSWORD,
                "organization": org_id.str,
            },
        )
        assert response.status_code == 200
        body = await response.get_json()
        assert body["token"] not in tokens
        tokens.append(body["token"])

    assert len(tokens) == 3


@pytest.mark.trio
@pytest.mark.parametrize("use_org_id", [True, False])
async def test_encrypted_key_auth(
    test_app: TrioTestApp, backend_addr: BackendAddr, running_backend: BackendApp, use_org_id
):
    test_client = test_app.test_client()

    ORG_ID = OrganizationID("OrgID")
    EMAIL = "zana@wraeclast.nz"
    USER_PASSWORD = "Still sane, Exile?"
    PARSEC_KEY = (
        "But at least you're done now, right, Exile? You'll leave the Atlas alone... right?"
    )
    ENCRYPTED_KEY = encrypt_parsec_key(USER_PASSWORD, PARSEC_KEY)

    org_backend_addr = BackendOrganizationBootstrapAddr.build(backend_addr, ORG_ID)

    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_backend_addr.to_url(),
            "email": EMAIL,
            "key": PARSEC_KEY,
        },
    )
    assert response.status_code == 200

    app = cast(ResanaApp, test_app.app)

    devices = list_available_devices(app.core_config.config_dir)
    assert len(devices) == 1
    device = devices[0]
    assert not (device.key_file_path.parent / f"{device.slughash}.enc_key").exists()

    # Auth using user_password as key should fail
    response = await test_client.post(
        "/auth",
        json={
            "email": EMAIL,
            "key": USER_PASSWORD,
            "organization": ORG_ID.str if use_org_id else None,
        },
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_key"}

    # Auth using parsec_key as key should work
    response = await test_client.post(
        "/auth",
        json={
            "email": EMAIL,
            "key": PARSEC_KEY,
            "organization": ORG_ID.str if use_org_id else None,
        },
    )
    body = await response.get_json()
    assert response.status_code == 200
    # Logout
    response = await test_client.delete(
        "/auth", headers={"Authorization": f"Bearer {body['token']}"}
    )

    assert not (device.key_file_path.parent / f"{device.slughash}.enc_key").exists()

    cores_manager: CoresManager = app.cores_manager

    # Try to login with a device that does not exists
    with pytest.raises(CoreDeviceNotFoundError):
        await cores_manager.login(
            email="b@c.d", organization_id=ORG_ID, user_password=USER_PASSWORD
        )

    # Try to login while offline using only the user password
    with pytest.raises(CoreDeviceEncryptedKeyNotFoundError):
        await cores_manager.login(email=EMAIL, organization_id=ORG_ID, user_password=USER_PASSWORD)

    # Auth using encrypted_key and user_password should work
    response = await test_client.post(
        "/auth",
        json={
            "email": EMAIL,
            "encrypted_key": ENCRYPTED_KEY,
            "user_password": USER_PASSWORD,
            "organization": ORG_ID.str if use_org_id else None,
        },
    )
    body = await response.get_json()
    assert response.status_code == 200
    # Logout
    response = await test_client.delete(
        "/auth", headers={"Authorization": f"Bearer {body['token']}"}
    )

    assert (device.key_file_path.parent / f"{device.slughash}.enc_key").exists()

    # Now we should be able to log in offline
    token = await cores_manager.login(
        email=EMAIL, organization_id=ORG_ID if use_org_id else None, user_password=USER_PASSWORD
    )
    assert token is not None

    # Also try to login offline with an incorrect password for good measure
    with pytest.raises(CoreDeviceInvalidPasswordError):
        await cores_manager.login(
            email=EMAIL, organization_id=ORG_ID, user_password="IncorrectPassword"
        )
