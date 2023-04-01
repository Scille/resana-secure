import pytest
import base64
from pathlib import Path
from quart.typing import TestAppProtocol

from parsec.api.protocol import OrganizationID
from parsec.backend import BackendApp
from parsec.backend.organization import generate_bootstrap_token
from parsec.core.local_device import list_available_devices
from parsec.core.types import BackendAddr, BackendOrganizationBootstrapAddr
from parsec._parsec import SequesterSigningKeyDer


@pytest.fixture
def default_org_id():
    return OrganizationID("BlackMesa")


@pytest.fixture
async def created_org_token(
    test_app: TestAppProtocol, running_backend: BackendApp, default_org_id: OrganizationID
):
    bootstrap_token = generate_bootstrap_token()
    await running_backend.organization.create(default_org_id, bootstrap_token=bootstrap_token)
    return bootstrap_token


@pytest.fixture
async def org_bootstrap_addr(
    backend_addr: BackendAddr, created_org_token: str, default_org_id: OrganizationID
):
    return BackendOrganizationBootstrapAddr.build(backend_addr, default_org_id, created_org_token)


@pytest.mark.trio
async def test_bootstrap_organization(
    test_app: TestAppProtocol,
    core_config_dir: Path,
    org_bootstrap_addr: BackendOrganizationBootstrapAddr,
):
    test_client = test_app.test_client()

    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
        },
    )

    assert response.status_code == 200
    body = await response.get_json()
    assert body == {}
    available_devices = list_available_devices(core_config_dir)
    assert len(available_devices) == 1
    assert available_devices[0].organization_id.str == org_bootstrap_addr.organization_id.str
    assert available_devices[0].human_handle is not None
    assert available_devices[0].human_handle.email == "gordon.freeman@blackmesa.nm"


@pytest.mark.trio
async def test_bootstrap_organization_not_created(
    test_app: TestAppProtocol, running_backend: BackendApp, backend_addr: BackendAddr
):
    test_client = test_app.test_client()

    org_bootstrap_addr = BackendOrganizationBootstrapAddr.build(
        backend_addr, OrganizationID("OrgID"), "a" * 64
    )

    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
        },
    )

    assert response.status_code == 404
    body = await response.get_json()
    assert body == {"error": "unknown_organization"}


@pytest.mark.trio
async def test_bootstrap_organization_backend_offline(
    test_app: TestAppProtocol, backend_addr: BackendAddr
):
    test_client = test_app.test_client()

    org_bootstrap_addr = BackendOrganizationBootstrapAddr.build(
        backend_addr, OrganizationID("OrgID"), "a" * 64
    )

    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
        },
    )

    assert response.status_code == 503
    body = await response.get_json()
    assert body == {"error": "offline"}


@pytest.mark.trio
async def test_organization_already_bootstrapped(
    test_app: TestAppProtocol, org_bootstrap_addr: BackendOrganizationBootstrapAddr
):
    test_client = test_app.test_client()

    # Bootstrap
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
        },
    )
    assert response.status_code == 200

    # Trying to bootstrap the same org
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
        },
    )

    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "organization_already_bootstrapped"}


@pytest.mark.trio
async def test_bootstrap_organization_invalid_email(
    test_app: TestAppProtocol, org_bootstrap_addr: BackendOrganizationBootstrapAddr
):
    test_client = test_app.test_client()

    # Not str
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": 42,
            "key": "abcd",
        },
    )

    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "bad_data", "fields": ["email"]}

    # Not a valid email
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "[a]",
            "key": "abcd",
        },
    )

    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "bad_data", "fields": ["email"]}


@pytest.mark.trio
async def test_bootstrap_organization_invalid_key(
    test_app: TestAppProtocol, org_bootstrap_addr: BackendOrganizationBootstrapAddr
):
    test_client = test_app.test_client()

    # Not str
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": 42,
        },
    )

    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "bad_data", "fields": ["key"]}


@pytest.mark.trio
async def test_bootstrap_organization_invalid_url(test_app):
    test_client = test_app.test_client()

    # Not str
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": "parsec://a.b",
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
        },
    )

    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "bad_data", "fields": ["organization_url"]}

    # Not a valid BackendOrganizationBootstrapAddr
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": "parsec://a.b",
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
        },
    )

    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "bad_data", "fields": ["organization_url"]}


@pytest.mark.trio
@pytest.mark.parametrize("method", ["GET", "HEAD", "PUT", "DELETE", "PATCH"])
async def test_bootstrap_organization_invalid_method(
    test_app: TestAppProtocol, org_bootstrap_addr: BackendOrganizationBootstrapAddr, method: str
):
    test_client = test_app.test_client()

    response = await getattr(test_client, method.lower())(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
        },
    )

    assert response.status_code == 405
    body = await response.get_json()
    assert body is None


@pytest.mark.trio
@pytest.mark.parametrize("kind", ["missing_header", "bad_header", "bad_body", "missing_body"])
async def test_bootstrap_body_not_json(test_app: TestAppProtocol, kind: str):
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

    response = await test_client.post("/organization/bootstrap", headers=headers, data=data)
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "json_body_expected"}


@pytest.mark.trio
async def test_bootstrap_organization_with_sequester_key(
    test_app: TestAppProtocol,
    core_config_dir: Path,
    org_bootstrap_addr: BackendOrganizationBootstrapAddr,
    running_backend: BackendApp,
):
    test_client = test_app.test_client()
    _, seq_verify_key = SequesterSigningKeyDer.generate_pair(size_in_bits=1024)

    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
            "sequester_verify_key": base64.b64encode(seq_verify_key.dump()).decode(),
        },
    )

    assert response.status_code == 200
    body = await response.get_json()
    assert body == {}
    available_devices = list_available_devices(core_config_dir)
    assert len(available_devices) == 1
    assert available_devices[0].organization_id.str == org_bootstrap_addr.organization_id.str
    assert available_devices[0].human_handle is not None
    assert available_devices[0].human_handle.email == "gordon.freeman@blackmesa.nm"

    organization = await running_backend.organization.get(org_bootstrap_addr.organization_id)
    assert organization.sequester_authority is not None
    assert organization.sequester_authority.verify_key_der.dump() == seq_verify_key.dump()


@pytest.mark.trio
async def test_bootstrap_organization_invalid_sequester_key(
    test_app: TestAppProtocol, org_bootstrap_addr: BackendOrganizationBootstrapAddr
):
    test_client = test_app.test_client()

    # Not str
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
            "sequester_verify_key": 42,
        },
    )

    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "bad_data", "fields": ["sequester_verify_key"]}

    # Not base64
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
            "sequester_verify_key": "a#",
        },
    )

    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "bad_data", "fields": ["sequester_verify_key"]}

    # Not a valid key
    response = await test_client.post(
        "/organization/bootstrap",
        json={
            "organization_url": org_bootstrap_addr.to_url(),
            "email": "gordon.freeman@blackmesa.nm",
            "key": "abcd",
            "sequester_verify_key": base64.b64encode(b"nihilanth").decode(),
        },
    )

    assert response.status_code == 400
    body = await response.get_json()
    assert body == {"error": "bad_data", "fields": ["sequester_verify_key"]}
