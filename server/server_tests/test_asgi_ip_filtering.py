# Testing
import pytest
from asgi_ip_filtering import AsgiIpFilteringMiddleware
from quart import websocket
from quart.testing.connections import WebsocketDisconnectError, WebsocketResponseError
from quart.typing import TestClientProtocol
from quart_trio import QuartTrio


@pytest.fixture
def test_app() -> QuartTrio:
    app = QuartTrio(__name__)

    @app.route("/")
    async def base_route() -> str:
        return "Hello World"

    @app.route("/administration")
    async def administration_route() -> str:
        return "Hello World"

    @app.route("/administration/<arg>")
    async def administration_route_with_arg(arg: str) -> str:
        return "Hello World"

    @app.route("/anonymous")
    async def empty_anonymous_route() -> str:
        return "Hello World"

    @app.route("/anonymous/<org>")
    async def anonymous_route(org: str) -> str:
        return "Hello World"

    @app.route("/anonymous/<org>/<arg>")
    async def anonymous_route_with_arg(org: str, arg: str) -> str:
        return "Hello World"

    @app.route("/invited")
    async def empty_invited_route() -> str:
        return "Hello World"

    @app.route("/invited/<org>")
    async def invited_route(org: str) -> str:
        return "Hello World"

    @app.route("/invited/<org>/<arg>")
    async def invited_route_with_arg(org: str, arg: str) -> str:
        return "Hello World"

    @app.route("/authenticated")
    async def empty_authenticated_route() -> str:
        return "Hello World"

    @app.route("/authenticated/<org>")
    async def authenticated_route(org: str) -> str:
        return "Hello World"

    @app.route("/authenticated/<org>/<arg>")
    async def authenticated_route_with_arg(org: str, arg: str) -> str:
        return "Hello World"

    @app.websocket("/ws")
    async def ws_route() -> None:
        await websocket.accept()
        await websocket.send("WS event")
        await websocket.receive()
        await websocket.send("WS event 2")

    @app.websocket("/ws/<arg>")
    async def ws_route_with_arg(arg: str) -> None:
        await websocket.accept()
        await websocket.send("WS event")
        await websocket.receive()
        await websocket.send("WS event 2")

    return app


@pytest.fixture
def test_client(test_app: QuartTrio) -> TestClientProtocol:
    middleware = AsgiIpFilteringMiddleware(
        test_app.asgi_app,
        authorized_proxies="10.0.0.0/24 11.0.0.0/24",
        authorized_networks="130.0.0.0/24 131.0.0.0/24",
        authorized_networks_by_organization="",
    )
    test_app.asgi_app = middleware  # type: ignore[assignment]
    return test_app.test_client()


@pytest.fixture(
    params=[
        "/anonymous",
        "/invited",
        "/authenticated",
        "/anonymous/test",
        "/invited/test",
        "/authenticated/test",
    ]
)
def filtered_http_routes(request) -> str:
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


@pytest.fixture(params=["10.0.0.1", "11.0.0.1"], ids=["proxy1", "proxy2"])
def insider_local_ip(request):
    return request.param


@pytest.fixture
def outsider_local_ip():
    return "12.0.0.1"


@pytest.fixture(params=["130.0.0.1", "131.0.0.1"], ids=["network1", "network2"])
def insider_client_ip(request):
    return request.param


@pytest.fixture
def outsider_client_ip():
    return "132.0.0.1"


@pytest.mark.trio
async def test_unfiltered_http_with_insider_ip(
    test_client: TestClientProtocol,
    unfiltered_http_routes: str,
    insider_client_ip: str,
    insider_local_ip: str,
) -> None:
    response = await test_client.get(
        unfiltered_http_routes,
        scope_base={
            "client": (insider_local_ip, 1234),
            "headers": [(b"x-real-ip", insider_client_ip.encode())],
        },
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"


@pytest.mark.trio
async def test_unfiltered_http_with_outsider_ip(
    test_client: TestClientProtocol,
    unfiltered_http_routes: str,
    insider_local_ip: str,
    insider_client_ip: str,
    outsider_local_ip: str,
    outsider_client_ip: str,
) -> None:
    response = await test_client.get(
        unfiltered_http_routes,
        scope_base={
            "client": (outsider_local_ip, 1234),
            "headers": [(b"x-real-ip", insider_client_ip.encode())],
        },
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"

    response = await test_client.get(
        unfiltered_http_routes,
        scope_base={
            "client": (insider_local_ip, 1234),
            "headers": [(b"x-real-ip", outsider_client_ip.encode())],
        },
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"


@pytest.mark.trio
async def test_filtered_http_with_insider_ip(
    test_client: TestClientProtocol,
    filtered_http_routes: str,
    insider_client_ip: str,
    insider_local_ip: str,
) -> None:
    response = await test_client.get(
        filtered_http_routes,
        scope_base={
            "client": (insider_local_ip, 1234),
            "headers": [(b"x-real-ip", insider_client_ip.encode())],
        },
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"


@pytest.mark.trio
async def test_filtered_http_with_outsider_ip(
    test_client: TestClientProtocol,
    filtered_http_routes: str,
    insider_local_ip: str,
    insider_client_ip: str,
    outsider_local_ip: str,
    outsider_client_ip: str,
) -> None:
    response = await test_client.get(
        filtered_http_routes,
        scope_base={
            "client": (outsider_local_ip, 1234),
            "headers": [(b"x-real-ip", insider_client_ip.encode())],
        },
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.PROXY_REJECTED_MESSAGE.format(outsider_local_ip)
    assert (await response.data).decode() == expected

    response = await test_client.get(
        filtered_http_routes,
        scope_base={
            "client": (insider_local_ip, 1234),
            "headers": [(b"x-real-ip", outsider_client_ip.encode())],
        },
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.NETWORK_REJECTED_MESSAGE.format(outsider_client_ip)
    assert (await response.data).decode() == expected


@pytest.mark.trio
async def test_unknown_route_with_insider_ip(
    test_client: TestClientProtocol,
    insider_local_ip: str,
    insider_client_ip: str,
) -> None:
    route = "/unknown"

    response = await test_client.get(
        route,
        scope_base={
            "client": (insider_local_ip, 1234),
            "headers": [(b"x-real-ip", insider_client_ip.encode())],
        },
    )
    assert response.status_code == 404


@pytest.mark.trio
async def test_unknown_route_with_outsider_ip(
    test_client: TestClientProtocol,
    insider_local_ip: str,
    insider_client_ip: str,
    outsider_local_ip: str,
    outsider_client_ip: str,
) -> None:
    route = "/unknown"

    response = await test_client.get(
        route,
        scope_base={
            "client": (outsider_local_ip, 1234),
            "headers": [(b"x-real-ip", insider_client_ip.encode())],
        },
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.PROXY_REJECTED_MESSAGE.format(outsider_local_ip)
    assert (await response.data).decode() == expected

    response = await test_client.get(
        route,
        scope_base={
            "client": (insider_local_ip, 1234),
            "headers": [(b"x-real-ip", outsider_client_ip.encode())],
        },
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.NETWORK_REJECTED_MESSAGE.format(outsider_client_ip)
    assert (await response.data).decode() == expected


@pytest.mark.trio
async def test_unknown_ws_route_with_insider_ip(
    test_client: TestClientProtocol,
    insider_local_ip: str,
    insider_client_ip: str,
) -> None:
    route = "/unknown"

    with pytest.raises(WebsocketResponseError) as ctx_response:
        scope_base = {
            "client": (insider_local_ip, 1234),
            "headers": [(b"x-real-ip", insider_client_ip.encode())],
        }
        async with test_client.websocket(route, scope_base=scope_base) as ws:  # type: ignore[call-arg]
            await ws.receive()
    assert ctx_response.value.response.status_code == 404


@pytest.mark.trio
async def test_unknown_ws_route_with_outsider_ip(
    test_client: TestClientProtocol,
    insider_local_ip: str,
    insider_client_ip: str,
    outsider_local_ip: str,
    outsider_client_ip: str,
) -> None:
    route = "/unknown"

    with pytest.raises(WebsocketDisconnectError) as ctx_disconnect:
        scope_base = {
            "client": (outsider_local_ip, 1234),
            "headers": [(b"x-real-ip", insider_client_ip.encode())],
        }
        async with test_client.websocket(route, scope_base=scope_base) as ws:  # type: ignore[call-arg]
            await ws.receive()
    assert ctx_disconnect.value.args == (403,)

    with pytest.raises(WebsocketDisconnectError) as ctx_disconnect:
        scope_base = {
            "client": (insider_local_ip, 1234),
            "headers": [(b"x-real-ip", outsider_client_ip.encode())],
        }
        async with test_client.websocket(route, scope_base=scope_base) as ws:  # type: ignore[call-arg]
            await ws.receive()
    assert ctx_disconnect.value.args == (403,)


@pytest.mark.trio
async def test_websocket_with_insider_ip(
    test_client: TestClientProtocol,
    insider_local_ip: str,
    insider_client_ip: str,
) -> None:
    route = "/ws"

    scope_base = {
        "client": (insider_local_ip, 1234),
        "headers": [(b"x-real-ip", insider_client_ip.encode())],
    }
    async with test_client.websocket(route, scope_base=scope_base) as ws:  # type: ignore[call-arg]
        assert await ws.receive() == "WS event"
        await ws.send("something")
        assert await ws.receive() == "WS event 2"


@pytest.mark.trio
async def test_websocket_with_outsider_ip(
    test_client: TestClientProtocol,
    insider_local_ip: str,
    insider_client_ip: str,
    outsider_local_ip: str,
    outsider_client_ip: str,
) -> None:
    route = "/ws"
    with pytest.raises(WebsocketDisconnectError) as ctx:
        scope_base = {
            "client": (outsider_local_ip, 1234),
            "headers": [(b"x-real-ip", insider_client_ip.encode())],
        }
        async with test_client.websocket(route, scope_base=scope_base) as ws:  # type: ignore[call-arg]
            await ws.receive()
            await ws.send("something")
            await ws.receive()
    assert ctx.value.args == (403,)

    with pytest.raises(WebsocketDisconnectError) as ctx:
        scope_base = {
            "client": (insider_local_ip, 1234),
            "headers": [(b"x-real-ip", outsider_client_ip.encode())],
        }
        async with test_client.websocket(route, scope_base=scope_base) as ws:  # type: ignore[call-arg]
            await ws.receive()
            await ws.send("something")
            await ws.receive()
    assert ctx.value.args == (403,)
