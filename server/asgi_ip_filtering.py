"""
Add IP filtering to a hypercorn trio app.

First configure the authorized networks using the following environement variables:

- `ASGI_AUTHORIZED_NETWORKS`: the ranges of allowed client IPs, as seen in the `x-real-ip` header
- `ASGI_AUTHORIZED_PROXIES`: the ranges of allowed connection IPs, as reported by the socket

Note: `ASGI_AUTHORIZED_PROXIES` is typically the IP range for the reverse proxy, that populates
the forwarded HTTP request with the `x-real-ip` header.

Example:

    export ASGI_AUTHORIZED_NETWORKS="142.251.0.0/16 143.0.0.0/24"
    export ASGI_AUTHORIZED_PROXYS="10.0.0.0/24 127.0.0.0/24"

Add the following lines to a file `sitecustomize.py` accessible through the python path:

    from asgi_ip_filtering import patch_hypercorn_trio_serve
    patch_hypercorn_trio_serve()
"""

import os
from functools import wraps
from ipaddress import ip_address, ip_network
from typing import Optional, Union, cast

import hypercorn
from hypercorn.trio import serve
from hypercorn.typing import (
    ASGI3Framework,
    ASGIReceiveCallable,
    ASGISendCallable,
    HTTPResponseBodyEvent,
    HTTPResponseStartEvent,
    HTTPScope,
    Scope,
    WebsocketCloseEvent,
    WebsocketScope,
)
from structlog import get_logger

logger = get_logger()


class AsgiIpFilteringMiddleware:

    ROUTES_REQUIRING_FILTERING = ["anonymous", "invited", "authenticated", "ws"]
    ENV_VAR_NAME_NETWORK = "ASGI_AUTHORIZED_NETWORKS"
    ENV_VAR_NAME_PROXY = "ASGI_AUTHORIZED_PROXIES"
    MESSAGE_REJECTED = (
        "The IP address {} is not part of the subnetworks authorized by "
        "the ASGI IP filtering middleware configuration."
    )

    def __init__(
        self,
        asgi_app: ASGI3Framework,
        authorized_networks: Optional[str] = None,
        authorized_proxies: Optional[str] = None,
    ):
        """
        Authorized networks and proxies are provided as a string of IPv4 or IPv6 networks
        (e.g `192.168.0.0/16` or `2001:db00::0/24`) separated with whitespace (spaces,
        tabs or newlines).

        If the `authorized_networks` argument is not provided, the environment variable
        `ASGI_AUTHORIZED_NETWORKS` is used.

        Similarly, if the `authorized_proxies` argument is not provided, the environment
        variable `ASGI_AUTHORIZED_PROXIES` is used.
        """
        self.asgi_app = asgi_app
        if authorized_networks is None:
            authorized_networks = os.environ.get(self.ENV_VAR_NAME_NETWORK)
        if authorized_networks is None:
            raise ValueError(
                "No authorized network configuration provided"
                f" (use `{self.ENV_VAR_NAME_NETWORK}` environment variable)"
            )
        if authorized_proxies is None:
            authorized_proxies = os.environ.get(self.ENV_VAR_NAME_PROXY)
        if authorized_proxies is None:
            raise ValueError(
                "No authorized proxy configuration provided"
                f" (use `{self.ENV_VAR_NAME_PROXY}` environment variable)"
            )
        self.authorized_networks = [ip_network(word) for word in authorized_networks.split()]
        self.authorized_proxies = [ip_network(word) for word in authorized_proxies.split()]
        logger.info(
            "IP filtering is enabled",
            authorized_networks=self.authorized_networks,
            authorized_proxies=self.authorized_proxies,
        )

    def is_network_authorized(self, host: str) -> bool:
        """
        Return `True` if the provided host is authorized, `False` otherwise.
        """
        try:
            host_ip = ip_address(host)
        except ValueError:
            return False
        return any(host_ip in network for network in self.authorized_networks)

    def is_proxy_authorized(self, proxy: str) -> bool:
        """
        Return `True` if the provided proxy is authorized, `False` otherwise.
        """
        try:
            proxy_ip = ip_address(proxy)
        except ValueError:
            return False
        return any(proxy_ip in proxy for proxy in self.authorized_proxies)

    def path_requires_ip_filtering(self, path: str) -> bool:
        """
        Return `True` if the route requires IP checking `False` otherwise.
        """
        try:
            empty, route_type, *_ = path.split("/")
        except ValueError:
            return False  # Not a route we're meant to check
        if empty != "":
            return False  # Can this even happen?
        return route_type in self.ROUTES_REQUIRING_FILTERING

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        """
        ASGI entry point for new connections.
        """
        # Ignore "lifespan" calls
        if scope["type"] not in ("http", "websocket"):
            return await self.asgi_app(scope, receive, send)

        # Ignore routes that do not require filtering
        scope = cast(Union[HTTPScope, WebsocketScope], scope)
        if not self.path_requires_ip_filtering(scope["path"]):
            return await self.asgi_app(scope, receive, send)

        # Check that client info is provided
        client = scope.get("client")
        if client is None:
            logger.info("No client information is provided", **scope)
            return await self.http_reject(scope, send)

        # Check that the proxy is authorized
        ip_proxy, _ = client
        if not self.is_proxy_authorized(ip_proxy):
            logger.info("A connection has been rejected", **scope)
            return await self.http_reject(scope, send, ip_proxy)

        # Check that the `x-real-ip` header is provided
        x_real_ip = dict(scope["headers"]).get(b"x-real-ip")
        if x_real_ip is None:
            logger.info("No x-real-ip information is provided", **scope)
            return await self.http_reject(scope, send)

        # Check that the network is authorized
        ip_host = x_real_ip.decode()
        if not self.is_network_authorized(ip_host):
            logger.info("A connection has been rejected", **scope)
            return await self.http_reject(scope, send, ip_host)

        return await self.asgi_app(scope, receive, send)

    async def http_reject(
        self,
        scope: Scope,
        send: ASGISendCallable,
        client_host: str = "<not provided>",
    ) -> None:
        """
        Reject the request with an `403` HTTP error code.
        """
        if scope["type"] == "websocket":
            close_event: WebsocketCloseEvent = {
                "type": "websocket.close",
                "code": 403,
                "reason": None,
            }
            await send(close_event)
            return

        assert scope["type"] == "http"
        content = self.MESSAGE_REJECTED.format(client_host).encode()
        content_length = f"{len(content)}".encode()
        start_event: HTTPResponseStartEvent = {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-length", content_length),
                (b"Content-Type", b"text/html; charset=UTF-8"),
            ],
        }
        await send(start_event)
        body_event: HTTPResponseBodyEvent = {
            "type": "http.response.body",
            "body": content,
            "more_body": False,
        }
        await send(body_event)


def patch_hypercorn_trio_serve() -> None:
    """Monkeypatch `hypercorn.trio.serve`"""
    if hypercorn.trio.serve != serve:
        return

    @wraps(serve)
    async def patched_serve(app: ASGI3Framework, *args, **kwargs) -> None:  # type: ignore[no-untyped-def, misc]
        return await serve(AsgiIpFilteringMiddleware(app), *args, **kwargs)

    hypercorn.trio.serve = patched_serve  # type: ignore[assignment]


# Testing
try:
    import pytest
    from quart import websocket
    from quart.testing.connections import WebsocketDisconnectError
    from quart.typing import TestClientProtocol
    from quart_trio import QuartTrio
except ImportError:
    pass
else:

    @pytest.fixture
    def test_client() -> TestClientProtocol:
        app = QuartTrio(__name__)

        @app.route("/")
        async def base_route() -> str:  # type: ignore[misc]
            return "Hello World"

        @app.route("/administration")
        async def administration_route() -> str:  # type: ignore[misc]
            return "Hello World"

        @app.route("/administration/<arg>")
        async def administration_route_with_arg(arg: str) -> str:  # type: ignore[misc]
            return "Hello World"

        @app.route("/anonymous")
        async def anonymous_route() -> str:  # type: ignore[misc]
            return "Hello World"

        @app.route("/anonymous/<arg>")
        async def anonymous_route_with_arg(arg: str) -> str:  # type: ignore[misc]
            return "Hello World"

        @app.route("/invited")
        async def invited_route() -> str:  # type: ignore[misc]
            return "Hello World"

        @app.route("/invited/<arg>")
        async def invited_route_with_arg(arg: str) -> str:  # type: ignore[misc]
            return "Hello World"

        @app.route("/authenticated")
        async def authenticated_route() -> str:  # type: ignore[misc]
            return "Hello World"

        @app.route("/authenticated/<arg>")
        async def authenticated_route_with_arg(arg: str) -> str:  # type: ignore[misc]
            return "Hello World"

        @app.websocket("/ws")
        async def ws_route() -> None:  # type: ignore[misc]
            await websocket.accept()
            await websocket.send("WS event")

        @app.websocket("/ws/<arg>")
        async def ws_route_with_arg(arg: str) -> None:  # type: ignore[misc]
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
