# Testing
import pytest
from asgi_ip_filtering_by_organization import AsgiIpFilteringByOrganizationMiddleware
from quart import websocket
from quart.testing.connections import WebsocketDisconnectError
from quart.typing import TestClientProtocol
from quart_trio import QuartTrio

from parsec.serde import packb


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

    app.asgi_app = AsgiIpFilteringByOrganizationMiddleware(app.asgi_app, "My-Org 130.0.0.0/16 200.0.0.0/16")  # type: ignore[assignment]
    return app.test_client()


TEST_FILTERED_HTTP_ROUTES = (
    "/anonymous/My-Org",
    "/invited/My-Org",
    "/authenticated/My-Org",
    "/anonymous/My-Org/test",
    "/invited/My-Org/test",
    "/authenticated/My-Org/test",
)

TEST_UNFILTERED_HTTP_ROUTES = (
    "/",
    "/administration",
    "/administration/test",
    "/anonymous",
    "/invited",
    "/authenticated",
    "/anonymous/My-Org-2",
    "/invited/My-Org-2",
    "/authenticated/My-Org-2",
)

TEST_WS_ROUTES = (
    "/ws",
    "/ws/test",
)


@pytest.mark.trio
@pytest.mark.parametrize("route", TEST_FILTERED_HTTP_ROUTES + TEST_UNFILTERED_HTTP_ROUTES)
async def test_http_with_insider_ip(test_client: TestClientProtocol, route: str) -> None:
    response = await test_client.get(
        route,
        headers={"x-real-ip": "130.0.0.1"},
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"


@pytest.mark.trio
@pytest.mark.parametrize("route", TEST_UNFILTERED_HTTP_ROUTES)
async def test_unfiltered_http_with_outsider_ip(
    test_client: TestClientProtocol, route: str
) -> None:
    response = await test_client.get(
        route,
        headers={"x-real-ip": "133.0.0.1"},
    )
    assert response.status_code == 200
    assert (await response.data).decode() == "Hello World"


@pytest.mark.trio
@pytest.mark.parametrize("route", TEST_FILTERED_HTTP_ROUTES)
async def test_filtered_http_with_outsider_ip(test_client: TestClientProtocol, route: str) -> None:
    response = await test_client.get(
        route,
        headers={"x-real-ip": "133.0.0.1"},
    )
    assert response.status_code == 403
    assert response.content_type == "text/html; charset=UTF-8"
    expected = AsgiIpFilteringByOrganizationMiddleware.MESSAGE_REJECTED.format("133.0.0.1")
    assert (await response.data).decode() == expected


@pytest.mark.trio
async def test_unknown_route(test_client: TestClientProtocol) -> None:
    response = await test_client.get(
        "/unknown",
        headers={"x-real-ip": "130.0.0.1"},
    )
    assert response.status_code == 404

    response = await test_client.get(
        "/unknown",
        headers={"x-real-ip": "133.0.0.1"},
    )
    assert response.status_code == 404


@pytest.mark.trio
@pytest.mark.parametrize("route", TEST_WS_ROUTES)
async def test_asgi_ip_filtering_websocket(test_client: TestClientProtocol, route: str) -> None:
    # Websocket route
    async with test_client.websocket("/ws", headers={"x-real-ip": "130.0.0.1"}) as ws:
        assert await ws.receive() == "WS event"
        await ws.send(packb({"organization_id": "My-Org"}))
        assert await ws.receive() == "WS event 2"

    async with test_client.websocket("/ws", headers={"x-real-ip": "130.0.0.1"}) as ws:
        assert await ws.receive() == "WS event"
        await ws.send(packb({"organization_id": "My-Org-2"}))
        assert await ws.receive() == "WS event 2"

    with pytest.raises(WebsocketDisconnectError) as ctx:
        async with test_client.websocket("/ws", headers={"x-real-ip": "133.0.0.1"}) as ws:
            assert await ws.receive() == "WS event"
            await ws.send(packb({"organization_id": "My-Org"}))
            assert await ws.receive() == "WS event 2"
    assert ctx.value.args == (403,)

    async with test_client.websocket("/ws", headers={"x-real-ip": "133.0.0.1"}) as ws:
        assert await ws.receive() == "WS event"
        await ws.send(packb({"organization_id": "My-Org-2"}))
        assert await ws.receive() == "WS event 2"
