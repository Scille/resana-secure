"""
Add IP filtering to a hypercorn trio app.

First configure the authorized networks using the `ASGI_AUTHORIZED_NETWORKS` environement
variable:

    export ASGI_AUTHORIZED_NETWORKS="192.168.0.0/16 127.0.0.0/24"

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

    ENV_VAR_NAME_NETWORK = "ASGI_AUTHORIZED_NETWORKS"
    ENV_VAR_NAME_PROXY = "ASGI_AUTHORIZED_PROXIES"
    ENV_VAR_NAME_ORGANIZATION = "ASGI_AUTHORIZED_ORGANIZATION"
    MESSAGE_REJECTED = (
        "The IP address {} is not part of the subnetworks authorized by "
        "the ASGI IP filtering middleware configuration."
    )

    def __init__(
        self,
        asgi_app: ASGI3Framework,
        authorized_networks: Optional[str] = None,
        authorized_proxies: Optional[str] = None,
        authorized_ips_per_orgs: Optional[str] = None,
    ):
        """
        Authorized networks are provided as a string of IPv4 or IPv6 networks
        (e.g `192.168.0.0/16` or `2001:db00::0/24`) separated with whitespace
        (spaces, tabs or newlines).

        If the `authorized_networks` argument is not provided the environment
        variable `ASGI_AUTHORIZED_NETWORKS` is used.
        """
        self.asgi_app = asgi_app
        self.org_id = ""

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
        if authorized_ips_per_orgs is None:
            authorized_ips_per_orgs = os.environ.get(self.ENV_VAR_NAME_ORGANIZATION)
        if authorized_ips_per_orgs is None:
            raise ValueError(
                "No authorized ips per organization provided"
                f" (use `{self.ENV_VAR_NAME_ORGANIZATION}` environment variable)"
            )

        self.authorized_networks = [ip_network(word) for word in authorized_networks.split()]
        self.authorized_proxies = [ip_network(word) for word in authorized_proxies.split()]
        self.authorized_ips_per_org = {}
        for org in authorized_ips_per_orgs.split(";"):
            tmp_list = org.split(",")
            self.authorized_ips_per_org[tmp_list[0]] = [ip_network(word) for word in tmp_list[1:]]

        logger.info(
            "IP filtering is enabled",
            authorized_networks=self.authorized_networks,
            authorized_proxies=self.authorized_proxies,
        )

    def is_network_authorized(self, host: str, organization_id: Optional[str] = None) -> bool:
        """
        Return `True` if the provided host is authorized, `False` otherwise.
        """
        try:
            host_ip = ip_address(host)
        except ValueError:
            return False
        if organization_id:
            try:
                return any(
                    host_ip in network for network in (self.authorized_ips_per_org)[organization_id]
                )
            except KeyError:
                return False  # Which value to return if the org is not given ?
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

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        """
        ASGI entry point for new connections.
        """

        async def wrapped_receive():
            result = await receive()
            if "bytes" in result.keys() and b"organization_id" in result["bytes"]:
                import msgpack

                self.org_id = msgpack.unpackb(result["bytes"])["organization_id"]
            return result

        if scope["type"] in ("http", "websocket"):
            scope = cast(Union[HTTPScope, WebsocketScope], scope)
            client = scope.get("client")
            if client is None:
                logger.info("No client information is provided", **scope)
                return await self.http_reject(scope, send)
            ip_proxy, _ = client
            if not self.is_proxy_authorized(ip_proxy):
                logger.info("A connection has been rejected", **scope)
                return await self.http_reject(scope, send, ip_proxy)
            headers = scope.get("headers")
            if headers is None:
                logger.info("No header information is provided", **scope)
                return await self.http_reject(scope, send)
            # headers type is Iterable[Tuple[bytes, bytes]]
            x_real_ip = [(field, value) for (field, value) in headers if field == b"x-real-ip"]
            if not len(x_real_ip):
                logger.info("No x-real-ip information is provided", **scope)
                return await self.http_reject(scope, send)
            _, ip_host = x_real_ip[0]
            if ip_host is None:
                logger.info("No x-real-ip information is provided", **scope)
                return await self.http_reject(scope, send)
            if not self.is_network_authorized(ip_host.decode()):
                logger.info("A connection has been rejected", **scope)
                return await self.http_reject(scope, send, ip_host.decode())
            if self.org_id and not self.is_network_authorized(ip_host.decode(), self.org_id):
                return await self.http_reject(scope, send, ip_host.decode())

        if not self.org_id:
            return await self.asgi_app(scope, wrapped_receive, send)
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
    from quart_trio import QuartTrio
except ImportError:
    pass
else:

    @pytest.mark.trio
    async def test_asgi_ip_filtering() -> None:
        app = QuartTrio(__name__)

        @app.route("/")
        async def http_route() -> str:  # type: ignore[misc]
            return "Hello World"

        @app.websocket("/ws")
        async def ws_route() -> None:  # type: ignore[misc]
            await websocket.accept()
            await websocket.send("WS event")

        app.asgi_app = AsgiIpFilteringMiddleware(app.asgi_app, "130.0.0.0/24 131.0.0.0/24", "127.0.0.0/24 128.0.0.0/24", "Org, 130.0.0.0/24")  # type: ignore[assignment]

        client = app.test_client()

        # Regular route
        response = await client.get(
            "/",
            scope_base={"client": ("127.0.0.1", 1234), "headers": [(b"x-real-ip", b"130.0.0.1")]},
        )
        assert response.status_code == 200
        assert (await response.data).decode() == "Hello World"

        response = await client.get(
            "/",
            scope_base={"client": ("128.0.0.1", 1234), "headers": [(b"x-real-ip", b"131.0.0.1")]},
        )
        assert response.status_code == 200
        assert (await response.data).decode() == "Hello World"

        response = await client.get(
            "/",
            scope_base={"client": ("129.0.0.1", 1234), "headers": [(b"x-real-ip", b"130.0.0.1")]},
        )
        assert response.status_code == 403
        assert response.content_type == "text/html; charset=UTF-8"
        expected = AsgiIpFilteringMiddleware.MESSAGE_REJECTED.format("129.0.0.1")
        assert (await response.data).decode() == expected

        response = await client.get(
            "/",
            scope_base={"client": ("127.0.0.1", 1234), "headers": [(b"x-real-ip", b"132.0.0.1")]},
        )
        assert response.status_code == 403
        assert response.content_type == "text/html; charset=UTF-8"
        expected = AsgiIpFilteringMiddleware.MESSAGE_REJECTED.format("132.0.0.1")
        assert (await response.data).decode() == expected

        # Websocket route
        async with client.websocket("/ws", scope_base={"client": ("127.0.0.1", 1234), "headers": [(b"x-real-ip", b"130.0.0.1")]}) as ws:  # type: ignore[call-arg]
            assert await ws.receive() == "WS event"

        async with client.websocket("/ws", scope_base={"client": ("128.0.0.1", 1234), "headers": [(b"x-real-ip", b"131.0.0.1")]}) as ws:  # type: ignore[call-arg]
            assert await ws.receive() == "WS event"

        with pytest.raises(WebsocketDisconnectError) as ctx:
            async with client.websocket("/ws", scope_base={"client": ("129.0.0.1", 1234), "headers": [(b"x-real-ip", b"130.0.0.1")]}) as ws:  # type: ignore[call-arg]
                await ws.receive()
        assert ctx.value.args == (403,)

        with pytest.raises(WebsocketDisconnectError) as ctx:
            async with client.websocket("/ws", scope_base={"client": ("127.0.0.1", 1234), "headers": [(b"x-real-ip", b"132.0.0.1")]}) as ws:  # type: ignore[call-arg]
                await ws.receive()
        assert ctx.value.args == (403,)
