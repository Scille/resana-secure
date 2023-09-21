# Testing
import pytest
from asgi_ip_filtering import AsgiIpFilteringMiddleware
from quart import websocket
from quart.testing.connections import WebsocketDisconnectError
from quart.typing import TestClientProtocol
from quart_trio import QuartTrio


@pytest.fixture
def test_client() -> TestClientProtocol:
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
    async def anonymous_route() -> str:
        return "Hello World"

    @app.route("/anonymous/<arg>")
    async def anonymous_route_with_arg(arg: str) -> str:
        return "Hello World"

    @app.route("/invited")
    async def invited_route() -> str:
        return "Hello World"

    @app.route("/invited/<arg>")
    async def invited_route_with_arg(arg: str) -> str:
        return "Hello World"

    @app.route("/authenticated")
    async def authenticated_route() -> str:
        return "Hello World"

    @app.route("/authenticated/<arg>")
    async def authenticated_route_with_arg(arg: str) -> str:
        return "Hello World"

    @app.websocket("/ws")
    async def ws_route() -> None:
        await websocket.accept()
        await websocket.send("WS event")

    @app.websocket("/ws/<arg>")
    async def ws_route_with_arg(arg: str) -> None:
        await websocket.accept()
        await websocket.send("WS event")

    app.asgi_app = AsgiIpFilteringMiddleware(app.asgi_app, "130.0.0.0/24 131.0.0.0/24", "127.0.0.0/24 128.0.0.0/24")  # type: ignore[assignment]
    return app.test_client()


TEST_FILTERED_HTTP_ROUTES = (
    "/anonymous",
    "/invited",
    "/authenticated",
    "/anonymous/test",
    "/invited/test",
    "/authenticated/test",
)

TEST_UNFILTERED_HTTP_ROUTES = (
    "/",
    "/administration",
    "/administration/test",
)

TEST_WS_ROUTES = (
    "/ws",
    "/ws/test",
)


@pytest.mark.trio
@pytest.mark.parametrize("route", TEST_FILTERED_HTTP_ROUTES + TEST_UNFILTERED_HTTP_ROUTES)
async def test_asgi_ip_filtering_http_with_insider_ip(
    test_client: TestClientProtocol, route: str
) -> None:
    response = await test_client.get(
        route,
        scope_base={
            "client": ("127.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"130.0.0.1")],
        },
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"

    response = await test_client.get(
        route,
        scope_base={
            "client": ("128.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"131.0.0.1")],
        },
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"


@pytest.mark.trio
@pytest.mark.parametrize("route", TEST_UNFILTERED_HTTP_ROUTES)
async def test_asgi_ip_filtering_unfiltered_http_with_outsider_ip(
    test_client: TestClientProtocol, route: str
) -> None:
    response = await test_client.get(
        route,
        scope_base={
            "client": ("129.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"130.0.0.1")],
        },
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"

    response = await test_client.get(
        route,
        scope_base={
            "client": ("128.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"132.0.0.1")],
        },
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"


@pytest.mark.trio
@pytest.mark.parametrize("route", TEST_FILTERED_HTTP_ROUTES)
async def test_asgi_ip_filtering_filtered_http_with_outsider_ip(
    test_client: TestClientProtocol, route: str
) -> None:
    response = await test_client.get(
        route,
        scope_base={
            "client": ("129.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"130.0.0.1")],
        },
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.MESSAGE_REJECTED.format("129.0.0.1")
    assert (await response.data).decode() == expected

    response = await test_client.get(
        route,
        scope_base={
            "client": ("127.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"132.0.0.1")],
        },
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringMiddleware.MESSAGE_REJECTED.format("132.0.0.1")
    assert (await response.data).decode() == expected


@pytest.mark.trio
async def test_asgi_ip_filtering_unknown_route(test_client: TestClientProtocol) -> None:
    response = await test_client.get(
        "/unknown",
        scope_base={
            "client": ("127.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"130.0.0.1")],
        },
    )
    assert response.status_code == 404

    response = await test_client.get(
        "/unknown",
        scope_base={
            "client": ("128.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"131.0.0.1")],
        },
    )
    assert response.status_code == 404

    response = await test_client.get(
        "/unknown",
        scope_base={
            "client": ("129.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"130.0.0.1")],
        },
    )
    assert response.status_code == 404

    response = await test_client.get(
        "/unknown",
        scope_base={
            "client": ("128.0.0.1", 1234),
            "headers": [(b"x-real-ip", b"132.0.0.1")],
        },
    )
    assert response.status_code == 404


@pytest.mark.trio
@pytest.mark.parametrize("route", TEST_WS_ROUTES)
async def test_asgi_ip_filtering_websocket(test_client: TestClientProtocol, route: str) -> None:
    # Websocket route
    async with test_client.websocket(route, scope_base={"client": ("127.0.0.1", 1234), "headers": [(b"x-real-ip", b"130.0.0.1")]}) as ws:  # type: ignore[call-arg]
        assert await ws.receive() == "WS event"

    async with test_client.websocket(route, scope_base={"client": ("128.0.0.1", 1234), "headers": [(b"x-real-ip", b"131.0.0.1")]}) as ws:  # type: ignore[call-arg]
        assert await ws.receive() == "WS event"

    with pytest.raises(WebsocketDisconnectError) as ctx:
        async with test_client.websocket(route, scope_base={"client": ("129.0.0.1", 1234), "headers": [(b"x-real-ip", b"130.0.0.1")]}) as ws:  # type: ignore[call-arg]
            await ws.receive()
    assert ctx.value.args == (403,)

    with pytest.raises(WebsocketDisconnectError) as ctx:
        async with test_client.websocket(route, scope_base={"client": ("127.0.0.1", 1234), "headers": [(b"x-real-ip", b"132.0.0.1")]}) as ws:  # type: ignore[call-arg]
            await ws.receive()
    assert ctx.value.args == (403,)
