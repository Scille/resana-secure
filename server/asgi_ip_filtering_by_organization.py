"""
Add IP filtering by parsec organization to a parsec server.

First configure the authorized networks for different organizations using the
`ASGI_AUTHORIZED_NETWORKS_FOR_ORGANIZATIONS` environment variable.

The format for the corresponding value is the following:
```
<ORGANIZATION_ID_1> <NETWORK_RANGE_1> <NETWORK_RANGE_2> <...>;
<ORGANIZATION_ID_2> <NETWORK_RANGE_3> <NETWORK_RANGE_4> <...>;
<...>
```

Notes:
- Line feeds are ignored but added here for visibility.
- Extra white spaces and empty lines are also ignored.
- Last semicolon is optional.
- Networks are provided as a string of IPv4 or IPv6 networks (e.g `192.168.0.0/16` or `2001:db00::0/24`).

Example:

    export ASGI_AUTHORIZED_NETWORKS='''
    Org1 142.251.0.0/16 143.0.0.0/24;
    Org2 242.251.0.0/16 243.0.0.0/24;
    '''

Add the following lines to a file `sitecustomize.py` accessible through the python path:

    from asgi_ip_filtering_by_organization import patch_hypercorn_trio_serve
    patch_hypercorn_trio_serve()
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import partial, wraps
from ipaddress import IPv4Address, IPv6Address, ip_address, ip_network
from typing import cast

import hypercorn
from hypercorn.trio import serve
from hypercorn.typing import (
    ASGI3Framework,
    ASGIReceiveCallable,
    ASGIReceiveEvent,
    ASGISendCallable,
    HTTPResponseBodyEvent,
    HTTPResponseStartEvent,
    HTTPScope,
    Scope,
    WebsocketCloseEvent,
    WebsocketDisconnectEvent,
    WebsocketScope,
)
from structlog import get_logger

from parsec._parsec import OrganizationID
from parsec.serde import SerdePackingError, unpackb

logger = get_logger()


@dataclass
class WrappedReceiveState:
    authorized: bool = False
    denied: bool = False


class AsgiIpFilteringByOrganizationMiddleware:

    ROUTES_REQUIRING_FILTERING = ["anonymous", "invited", "authenticated", "ws"]
    ENV_VAR_NAME_NETWORKS_BY_ORGANIZATION = "ASGI_AUTHORIZED_NETWORKS_BY_ORGANIZATION"
    MESSAGE_REJECTED = (
        "The IP address {} is not part of the subnetworks authorized by "
        "the ASGI IP filtering middleware configuration."
    )

    def __init__(
        self,
        asgi_app: ASGI3Framework,
        authorized_networks_by_organization: str | None = None,
    ):
        """
        The format for the `authorized_networks_by_organization` argument is the following:
        ```
        <ORGANIZATION_ID_1> <NETWORK_RANGE_1> <NETWORK_RANGE_2> <...>;
        <ORGANIZATION_ID_2> <NETWORK_RANGE_3> <NETWORK_RANGE_4> <...>;
        <...>
        ```

        Notes:
        - Line feeds are ignored but added here for visibility.
        - Extra white spaces and empty lines are also ignored.
        - Last semicolon is optional.
        - Networks are provided as a string of IPv4 or IPv6 networks (e.g `192.168.0.0/16` or `2001:db00::0/24`).

        Example:

            authorized_networks_by_organization = '''
            Org1 142.251.0.0/16 143.0.0.0/24;
            Org2 242.251.0.0/16 243.0.0.0/24;
            '''
        """
        self.asgi_app = asgi_app

        # This is the event returned to the server when the client is not authorized to
        # access an organization using the websocket. The server can then treat it as the
        # client being disconnected.
        self.websocket_disconnect_event: WebsocketDisconnectEvent = {
            "type": "websocket.disconnect",
            "code": 1000,
        }

        # Get the configuration, either through argument or environment variable
        if authorized_networks_by_organization is None:
            authorized_networks_by_organization = os.environ.get(
                self.ENV_VAR_NAME_NETWORKS_BY_ORGANIZATION
            )
        if authorized_networks_by_organization is None:
            raise ValueError(
                "No authorized network configuration provided"
                f" (use `{self.ENV_VAR_NAME_NETWORKS_BY_ORGANIZATION}` environment variable)"
            )

        # Parse configuration string
        rows = [
            line.split() for line in authorized_networks_by_organization.split(";") if line.split()
        ]
        self.authorized_networks_by_organization = {
            OrganizationID(name): [ip_network(value) for value in values] for name, *values in rows
        }

        # Logger is useful to make sure our configuration is properly applied.
        logger.info(
            "IP filtering by organization is enabled",
            authorized_networks_by_organization=self.authorized_networks_by_organization,
        )

    def is_network_authorized(
        self, organization_string: str, host: IPv4Address | IPv6Address
    ) -> bool:
        """
        Return `True` if the provided host is authorized, `False` otherwise.
        """
        try:
            organization = OrganizationID(organization_string)
        except ValueError:
            return False
        try:
            authorized_networks = self.authorized_networks_by_organization[organization]
        except KeyError:
            # Organization without configuration are allowed by default
            return True
        return any(host in network for network in authorized_networks)

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
        return route_type.lower() in self.ROUTES_REQUIRING_FILTERING

    def is_http_path_authorized(
        self,
        path: str,
        host_ip: IPv4Address | IPv6Address,
    ) -> bool:
        """
        Return `True` if the provided route is authorized, `False` otherwise.
        """
        if not self.path_requires_ip_filtering(path):
            # If the path does not require filtering, it is authorized
            return True
        try:
            _, _, organization_string, *_ = path.split("/")
        except ValueError:
            # Path stops before providing the organization (e.g. `/authenticated`)
            # Let's allow it
            return True
        return self.is_network_authorized(organization_string, host_ip)

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        """
        ASGI entry point for new connections.
        """
        # Ignore anything not HTTP or websocket
        if scope["type"] not in ("http", "websocket"):
            return await self.asgi_app(scope, receive, send)

        # Ignore routes that do not require filtering
        scope = cast("HTTPScope | WebsocketScope", scope)
        if not self.path_requires_ip_filtering(scope["path"]):
            return await self.asgi_app(scope, receive, send)

        # Check that `x-real-ip` is provided
        x_real_ip = dict(scope["headers"]).get(b"x-real-ip")
        if x_real_ip is None:
            logger.info("No x-real-ip information is provided", **scope)
            return await self.http_reject(scope, send)

        # Check that `x-real-ip` has a valid ip address
        try:
            host_ip = ip_address(x_real_ip.decode())
        except ValueError:
            logger.info("Header x-real-ip does not contain a valid IP address", **scope)
            return await self.http_reject(scope, send)

        # With HTTP requests, check the path
        if scope["type"] == "http":
            scope = cast(HTTPScope, scope)
            if not self.is_http_path_authorized(scope["path"], host_ip):
                logger.info("An HTTP connection has been rejected", **scope)
                return await self.http_reject(scope, send, str(host_ip))
            return await self.asgi_app(scope, receive, send)

        # With websockets, wrap the receiver
        assert scope["type"] == "websocket"
        scope = cast(WebsocketScope, scope)
        state = WrappedReceiveState()
        wrapped_receive = partial(
            self.websocket_wrapped_receive, scope, receive, send, host_ip, state
        )
        return await self.asgi_app(scope, wrapped_receive, send)

    async def websocket_wrapped_receive(
        self,
        scope: WebsocketScope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
        host_ip: IPv4Address | IPv6Address,
        state: WrappedReceiveState,
    ) -> ASGIReceiveEvent:
        event = await receive()

        # Not a receive event
        if event["type"] != "websocket.receive":
            return event

        # Already denied
        if state.denied:
            return self.websocket_disconnect_event

        # Already authorized
        if state.authorized:
            return event

        # Not a byte message but a test message
        event_bytes = event.get("bytes")
        if event_bytes is None:
            return event

        # Not a msgpack message, weird
        try:
            event_data = unpackb(event_bytes)
        except SerdePackingError:
            return event

        # No organization id, weird
        organization_string = event_data.get("organization_id")
        if organization_string is None:
            return event

        # Websocket connection denied
        if not self.is_network_authorized(organization_string, host_ip):
            state.denied = True
            logger.info(
                "A websocket connection has been rejected",
                organization=organization_string,
                **scope,
            )
            await self.http_reject(scope, send, str(host_ip))
            return self.websocket_disconnect_event

        # Webosocket connection authorized
        state.authorized = True
        return event

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
        return await serve(AsgiIpFilteringByOrganizationMiddleware(app), *args, **kwargs)

    hypercorn.trio.serve = patched_serve  # type: ignore[assignment]
