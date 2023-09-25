# Testing
import pytest
from asgi_ip_filtering import AsgiIpFilteringMiddleware
from quart.testing.connections import WebsocketDisconnectError, WebsocketResponseError
from quart.typing import TestClientProtocol
from quart_trio import QuartTrio

from parsec.serde import packb
from server_tests.test_asgi_ip_filtering import test_app

__all__ = ["test_app"]


@pytest.fixture
def test_client(test_app: QuartTrio) -> TestClientProtocol:
    middleware = AsgiIpFilteringMiddleware(
        test_app.asgi_app,
        authorized_proxies="0.0.0.0/0",
        authorized_networks="130.0.0.0/16 131.0.0.0/16",
        authorized_networks_by_organization="""
Org-1 130.0.20.0/24 130.0.21.0/24;
Org-2 131.0.20.0/24 131.0.21.0/24;
""",
    )
    middleware.TEST_LOCAL_IP = "127.0.0.1"
    test_app.asgi_app = middleware  # type: ignore[assignment]
    return test_app.test_client()


IPS = {
    "outsider": "132.0.0.1",
    "no_org_network1": "130.0.19.1",
    "no_org_network2": "131.0.19.1",
    "org1_network1": "130.0.20.1",
    "org1_network2": "130.0.21.1",
    "org2_network1": "131.0.20.1",
    "org2_network2": "131.0.21.1",
}
NO_ORG_KEYS = ["no_org_network1", "no_org_network2"]
ORG1_KEYS = ["org1_network1", "org1_network2"]
ORG2_KEYS = ["org2_network1", "org2_network2"]
INSIDER_KEYS = NO_ORG_KEYS + ORG1_KEYS + ORG2_KEYS
OUTSIDER_KEYS = ["outsider"]
assert set(IPS) == set(INSIDER_KEYS + OUTSIDER_KEYS)
ORG1_OUTSIDER_KEYS = OUTSIDER_KEYS + NO_ORG_KEYS + ORG2_KEYS
ORG2_OUTSIDER_KEYS = OUTSIDER_KEYS + NO_ORG_KEYS + ORG1_KEYS


@pytest.fixture(params=IPS.values(), ids=list(IPS))
def any_ip(request) -> str:
    return request.param


@pytest.fixture(params=[IPS[key] for key in OUTSIDER_KEYS], ids=OUTSIDER_KEYS)
def outsider_client_ip(request) -> str:
    return request.param


@pytest.fixture(params=[IPS[key] for key in INSIDER_KEYS], ids=INSIDER_KEYS)
def insider_client_ip(request) -> str:
    return request.param


@pytest.fixture(params=[IPS[key] for key in NO_ORG_KEYS], ids=NO_ORG_KEYS)
def no_org_client_ip(request) -> str:
    return request.param


@pytest.fixture(params=[IPS[key] for key in ORG1_KEYS], ids=ORG1_KEYS)
def org1_client_ip(request) -> str:
    return request.param


@pytest.fixture(params=[IPS[key] for key in ORG2_KEYS], ids=ORG2_KEYS)
def org2_client_ip(request) -> str:
    return request.param


@pytest.fixture(params=[IPS[key] for key in ORG1_OUTSIDER_KEYS], ids=ORG1_OUTSIDER_KEYS)
def org1_outsider_client_ip(request) -> str:
    return request.param


@pytest.fixture(params=[IPS[key] for key in ORG2_OUTSIDER_KEYS], ids=ORG2_OUTSIDER_KEYS)
def org2_outsider_client_ip(request) -> str:
    return request.param


@pytest.fixture(
    params=[
        "/",
        "/administration",
        "/administration/test",
    ]
)
def unfiltered_http_routes(request) -> str:
    return request.param


@pytest.fixture(
    params=[
        "/anonymous",
        "/invited",
        "/authenticated",
    ]
)
def no_org_http_route(request) -> str:
    return request.param


@pytest.fixture(
    params=[
        "/anonymous/Org-1",
        "/anonymous/Org-1/test",
        "/invited/Org-1",
        "/invited/Org-1/test",
        "/authenticated/Org-1",
        "/authenticated/Org-1/test",
    ]
)
def org1_http_route(request) -> str:
    return request.param


@pytest.fixture(
    params=[
        "/anonymous/Org-2",
        "/anonymous/Org-2/test",
        "/invited/Org-2",
        "/invited/Org-2/test",
        "/authenticated/Org-2",
        "/authenticated/Org-2/test",
    ]
)
def org2_http_route(request) -> str:
    return request.param


@pytest.mark.trio
async def test_unfiltered_http_routes(
    test_client: TestClientProtocol, unfiltered_http_routes: str, any_ip: str
) -> None:
    response = await test_client.get(
        unfiltered_http_routes,
        headers={"x-real-ip": any_ip},
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"


@pytest.mark.trio
async def test_no_org_http_routes_with_insider_ip(
    test_client: TestClientProtocol, no_org_http_route: str, insider_client_ip: str
) -> None:
    response = await test_client.get(
        no_org_http_route,
        headers={"x-real-ip": insider_client_ip},
    )
    assert (await response.data).decode() == "Hello World"
    assert response.status_code == 200


@pytest.mark.trio
async def test_no_org_http_routes_with_outsider_ip(
    test_client: TestClientProtocol, no_org_http_route: str, outsider_client_ip: str
) -> None:
    response = await test_client.get(
        no_org_http_route,
        headers={"x-real-ip": outsider_client_ip},
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.NETWORK_REJECTED_MESSAGE.format(outsider_client_ip)
    assert (await response.data).decode() == expected


@pytest.mark.trio
async def test_org1_http_routes_with_org1_ip(
    test_client: TestClientProtocol, org1_http_route: str, org1_client_ip: str
) -> None:
    response = await test_client.get(
        org1_http_route,
        headers={"x-real-ip": org1_client_ip},
    )
    assert (await response.data).decode() == "Hello World"
    assert response.status_code == 200


@pytest.mark.trio
async def test_org1_http_routes_without_org1_ip(
    test_client: TestClientProtocol, org1_http_route: str, org1_outsider_client_ip: str
) -> None:
    response = await test_client.get(
        org1_http_route,
        headers={"x-real-ip": org1_outsider_client_ip},
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.NETWORK_REJECTED_MESSAGE.format(org1_outsider_client_ip)
    assert (await response.data).decode() == expected


@pytest.mark.trio
async def test_org2_http_routes_with_org2_ip(
    test_client: TestClientProtocol, org2_http_route: str, org2_client_ip: str
) -> None:
    response = await test_client.get(
        org2_http_route,
        headers={"x-real-ip": org2_client_ip},
    )
    assert (await response.data).decode() == "Hello World"
    assert response.status_code == 200


@pytest.mark.trio
async def test_org2_http_routes_without_org2_ip(
    test_client: TestClientProtocol, org2_http_route: str, org2_outsider_client_ip: str
) -> None:
    response = await test_client.get(
        org2_http_route,
        headers={"x-real-ip": org2_outsider_client_ip},
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.NETWORK_REJECTED_MESSAGE.format(org2_outsider_client_ip)
    assert (await response.data).decode() == expected


@pytest.mark.trio
async def test_unknown_http_route_with_insider_ip(
    test_client: TestClientProtocol, insider_client_ip: str
) -> None:
    response = await test_client.get(
        "/unknown",
        headers={"x-real-ip": insider_client_ip},
    )
    assert response.status_code == 404


@pytest.mark.trio
async def test_unknown_http_route_with_outsider_ip(
    test_client: TestClientProtocol, outsider_client_ip: str
) -> None:
    response = await test_client.get(
        "/unknown",
        headers={"x-real-ip": outsider_client_ip},
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.NETWORK_REJECTED_MESSAGE.format(outsider_client_ip)
    assert (await response.data).decode() == expected


@pytest.mark.trio
async def test_unknown_ws_route_with_insider_ip(
    test_client: TestClientProtocol,
    insider_client_ip: str,
) -> None:
    route = "/unknown"

    with pytest.raises(WebsocketResponseError) as ctx_response:
        async with test_client.websocket(route, headers={"x-real-ip": insider_client_ip}) as ws:
            await ws.receive()
    assert ctx_response.value.response.status_code == 404


@pytest.mark.trio
async def test_unknown_ws_route_with_outsider_ip(
    test_client: TestClientProtocol,
    outsider_client_ip: str,
) -> None:
    route = "/unknown"

    with pytest.raises(WebsocketDisconnectError) as ctx_disconnect:
        async with test_client.websocket(route, headers={"x-real-ip": outsider_client_ip}) as ws:
            await ws.receive()
    assert ctx_disconnect.value.args == (403,)


@pytest.mark.trio
async def test_websocket_org1_with_org1_ip(test_client: TestClientProtocol, org1_client_ip) -> None:
    route = "/ws"
    async with test_client.websocket(route, headers={"x-real-ip": org1_client_ip}) as ws:
        assert await ws.receive() == "WS event"
        await ws.send(packb({"organization_id": "Org-1"}))
        assert await ws.receive() == "WS event 2"


@pytest.mark.trio
async def test_websocket_org2_with_org2_ip(test_client: TestClientProtocol, org2_client_ip) -> None:
    route = "/ws"
    async with test_client.websocket(route, headers={"x-real-ip": org2_client_ip}) as ws:
        assert await ws.receive() == "WS event"
        await ws.send(packb({"organization_id": "Org-2"}))
        assert await ws.receive() == "WS event 2"


@pytest.mark.trio
async def test_websocket_org1_without_org1_ip(
    test_client: TestClientProtocol, org1_outsider_client_ip
) -> None:
    route = "/ws"
    with pytest.raises(WebsocketDisconnectError) as ctx:
        async with test_client.websocket(
            route, headers={"x-real-ip": org1_outsider_client_ip}
        ) as ws:
            assert await ws.receive() == "WS event"
            await ws.send(packb({"organization_id": "Org-1"}))
            assert await ws.receive() == "WS event 2"
    assert ctx.value.args == (403,)


@pytest.mark.trio
async def test_websocket_org2_without_org2_ip(
    test_client: TestClientProtocol, org2_outsider_client_ip
) -> None:
    route = "/ws"
    with pytest.raises(WebsocketDisconnectError) as ctx:
        async with test_client.websocket(
            route, headers={"x-real-ip": org2_outsider_client_ip}
        ) as ws:
            assert await ws.receive() == "WS event"
            await ws.send(packb({"organization_id": "Org-2"}))
            assert await ws.receive() == "WS event 2"
    assert ctx.value.args == (403,)
