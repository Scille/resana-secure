import pytest
import trio
from functools import partial
from collections import namedtuple
from base64 import b64encode

from parsec.api.protocol import OrganizationID, HumanHandle
from parsec.core.types import BackendOrganizationBootstrapAddr, BackendAddr
from parsec.backend import backend_app_factory
from parsec.backend.config import BackendConfig, MockedBlockStoreConfig
from parsec.core.invite import bootstrap_organization
from parsec.core.backend_connection import apiv1_backend_anonymous_cmds_factory
from parsec.core.local_device import save_device_with_password

from resana_secure.app import app_factory


@pytest.fixture(scope="session")
def client_origin():
    return "https://resana.numerique.gouv.fr"


class BackendAddrRegisterer:
    def __init__(self):
        self.backend_addr_defined = trio.Event()
        self.backend_addr = None

    def register(self, backend_addr):
        self.backend_addr = backend_addr
        self.backend_addr_defined.set()

    async def get(self):
        await self.backend_addr_defined.wait()
        return self.backend_addr


@pytest.fixture
def _backend_addr_register(request):
    registerer = BackendAddrRegisterer()
    # Use a dummy URL (port 0 should trigger error when used !) if current
    # test doesn't use `running_backend` fixture
    if "running_backend" not in request.fixturenames:
        registerer.register(BackendAddr(hostname="127.0.0.1", port=0, use_ssl=False))

    return registerer


@pytest.fixture
async def backend_addr(_backend_addr_register):
    return await _backend_addr_register.get()


@pytest.fixture
async def test_app(core_config_dir, client_origin, backend_addr):
    async with app_factory(
        config_dir=core_config_dir,
        client_allowed_origins=[client_origin],
        backend_addr=backend_addr,
    ) as app:
        async with app.test_app() as test_app:
            yield test_app


@pytest.fixture
async def authenticated_client(test_app, local_device):
    test_client = test_app.test_client()

    response = await test_client.post(
        "/auth",
        json={"email": local_device.email, "key": b64encode(local_device.key).decode("ascii")},
    )
    assert response.status_code == 200
    # Note cookie is automatically added to test_client's cookie jar
    return test_client


@pytest.fixture
async def running_backend(_backend_addr_register):
    config = BackendConfig(
        administration_token="s3cr3t",
        db_min_connections=1,
        db_max_connections=5,
        db_first_tries_number=1,
        db_first_tries_sleep=1,
        debug=False,
        db_url="MOCKED",
        blockstore_config=MockedBlockStoreConfig(),
        email_config=None,
        backend_addr=None,
        forward_proto_enforce_https=None,
        ssl_context=False,
        spontaneous_organization_bootstrap=True,
        organization_bootstrap_webhook_url=None,
    )
    async with backend_app_factory(config) as backend:
        async with trio.open_service_nursery() as nursery:
            host = "127.0.0.1"
            listeners = await nursery.start(
                partial(trio.serve_tcp, backend.handle_client, port=0, host=host)
            )
            _, port = listeners[0].socket.getsockname()
            backend_addr = BackendAddr(hostname=host, port=port, use_ssl=False)
            _backend_addr_register.register(backend_addr)
            yield backend_addr
            nursery.cancel_scope.cancel()


@pytest.fixture
def core_config_dir(tmp_path):
    return tmp_path / "core_config_dir"


LocalDeviceTestbed = namedtuple("LocalDeviceTestbed", "device,email,key")


@pytest.fixture
async def local_device(running_backend, backend_addr, core_config_dir):
    organization_id = OrganizationID("CoolOrg")
    device_label = "alice's desktop"
    key = b"P@ssw0rd."
    password = b64encode(key).decode("ascii")  # TODO should implement&use `save_device_with_key`
    human_handle = HumanHandle(email="alice@example.com", label="Alice")
    bootstrap_addr = BackendOrganizationBootstrapAddr.build(
        backend_addr=backend_addr, organization_id=organization_id
    )

    async with apiv1_backend_anonymous_cmds_factory(addr=bootstrap_addr) as cmds:
        new_device = await bootstrap_organization(
            cmds=cmds, human_handle=human_handle, device_label=device_label
        )
        save_device_with_password(config_dir=core_config_dir, device=new_device, password=password)
    return LocalDeviceTestbed(device=new_device, email=human_handle.email, key=key)
