"""
Add IP filtering to a parsec server app (using hypercorn and trio).

The authorized networks are configured using the following environement variables:

- `ASGI_AUTHORIZED_PROXIES`: the ranges of allowed connection IPs, as reported by the socket
- `ASGI_AUTHORIZED_NETWORKS`: the ranges of allowed client IPs, as seen in the `x-real-ip` header
- `ASGI_AUTHORIZED_NETWORKS_BY_ORGANIZATION`: the ranges of allowed client IPs for a given organization,
  as seen in the `x-real-ip` header. It overrides the configuration in `ASGI_AUTHORIZED_NETWORKS`.

Note 1: `ASGI_AUTHORIZED_PROXIES` is typically the IP range for the reverse proxy, that populates
the forwarded HTTP request with the `x-real-ip` header.

Note 2: If `x-real-ip` is absent from the header, the client IP is considered to be the IP reported by
the socket directly.


Format for `ASGI_AUTHORIZED_NETWORKS` and `ASGI_AUTHORIZED_PROXIES`
-------------------------------------------------------------------

The format for the corresponding value is the following:

```
<NETWORK_RANGE_1> <NETWORK_RANGE_2> <...>
```

Notes:
- Extra white space characters and line feeds are ignored
- Networks are provided as a string of IPv4 or IPv6 networks (e.g `192.168.0.0/16` or `2001:db00::0/24`).

Example:

    export ASGI_AUTHORIZED_NETWORKS="142.251.0.0/16 143.0.0.0/24"
    export ASGI_AUTHORIZED_PROXYS="10.0.0.0/24 127.0.0.0/24"


Format for `ASGI_AUTHORIZED_NETWORKS_BY_ORGANIZATION`
-------------------------------------------------------

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


Configuring the middleware
--------------------------

Add the following lines to a file `sitecustomize.py` accessible through the python path:

    from asgi_ip_filtering import patch_hypercorn_trio_serve
    patch_hypercorn_trio_serve()

Or add the middleware directly in the code:

    from asgi_ip_filtering import
    from parsec.backend.asgi import BackendQuartTrio, app_factory
    [...]
    app: BackendQuartTrio = app_factory(*args, **kwargs)
    app.asgi_app = AsgiIpFilteringMiddleware(app.asgi_app)

"""

from __future__ import annotations

import os
from dataclasses import dataclass
from fnmatch import fnmatch
from functools import partial, wraps
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
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
    WebsocketReceiveEvent,
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


class AsgiIpFilteringMiddleware:
    TEST_LOCAL_IP: str = NotImplemented

    WEBSOCKET_ROUTE = "/ws"
    FILTERING_EXCLUDING_PATTERNS = ["/", "/administration", "/administration/*"]
    ENV_VAR_NAME_PROXY = "ASGI_AUTHORIZED_PROXIES"
    ENV_VAR_NAME_NETWORK = "ASGI_AUTHORIZED_NETWORKS"
    ENV_VAR_NAME_NETWORKS_BY_ORGANIZATION = "ASGI_AUTHORIZED_NETWORKS_BY_ORGANIZATION"
    NETWORK_REJECTED_MESSAGE = (
        "The client IP address {} is not part of the subnetworks authorized by "
        "the ASGI IP filtering middleware configuration."
    )
    PROXY_REJECTED_MESSAGE = (
        "The proxy IP address {} is not part of the subnetworks authorized by "
        "the ASGI IP filtering middleware configuration."
    )

    def __init__(
        self,
        asgi_app: ASGI3Framework,
        authorized_proxies: str | None = None,
        authorized_networks: str | None = None,
        authorized_networks_by_organization: str | None = None,
    ):
        """
        Authorized networks and proxies are provided as a string of IPv4 or IPv6 networks
        (e.g `192.168.0.0/16` or `2001:db00::0/24`) separated with whitespace (spaces,
        tabs or newlines).

        If the `authorized_networks` argument is not provided, the environment variable
        `ASGI_AUTHORIZED_NETWORKS` is used.

        Similarly, if the `authorized_proxies` argument is not provided, the environment
        variable `ASGI_AUTHORIZED_PROXIES` is used.

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

        If the `authorized_proxies` argument is not provided, the environment
        variable `ASGI_AUTHORIZED_PROXIES` is used.
        """
        self.asgi_app = asgi_app

        # This is the event returned to the server when the client is not authorized to
        # access an organization using the websocket. The server can then treat it as the
        # client being disconnected.
        self.websocket_disconnect_event: WebsocketDisconnectEvent = {
            "type": "websocket.disconnect",
            "code": 1000,
        }

        # Get the configuration for `authorized_proxies`, either through argument or environment variable
        if authorized_proxies is None:
            authorized_proxies = os.environ.get(self.ENV_VAR_NAME_PROXY)
        if authorized_proxies is None:
            raise ValueError(
                "No authorized proxy configuration provided"
                f" (use `{self.ENV_VAR_NAME_PROXY}` environment variable)"
            )
        self.authorized_proxies = [ip_network(word) for word in authorized_proxies.split()]

        # Get the configuration for `authorized_networks`, either through argument or environment variable
        if authorized_networks is None:
            authorized_networks = os.environ.get(self.ENV_VAR_NAME_NETWORK)
        if authorized_networks is None:
            raise ValueError(
                "No authorized network configuration provided"
                f" (use `{self.ENV_VAR_NAME_NETWORK}` environment variable)"
            )
        self.authorized_networks = [ip_network(word) for word in authorized_networks.split()]

        # Get the configuration for `authorized_networks_by_organization`, either through argument or environment variable
        if authorized_networks_by_organization is None:
            authorized_networks_by_organization = os.environ.get(
                self.ENV_VAR_NAME_NETWORKS_BY_ORGANIZATION
            )
        if authorized_networks_by_organization is None:
            raise ValueError(
                "No authorized network configuration provided"
                f" (use `{self.ENV_VAR_NAME_NETWORKS_BY_ORGANIZATION}` environment variable)"
            )
        splitted = [
            line.split() for line in authorized_networks_by_organization.split(";") if line.split()
        ]
        self.authorized_networks_by_organization = {
            OrganizationID(name): [ip_network(value) for value in values]
            for name, *values in splitted
        }

        # Logger is useful to make sure our configuration is properly applied.
        logger.info(
            "IP filtering is enabled",
            authorized_networks=self.authorized_networks,
            authorized_proxies=self.authorized_proxies,
        )

    def get_organization_from_path(self, path: str) -> str | None:
        """
        Return the organization as a string if it is present
        """
        try:
            empty, route_type, *args = path.split("/")
        except ValueError:
            return None
        if empty != "":
            return None
        if not args:
            return None
        organization, *_ = args
        return organization

    def get_authorized_networks_for_organization(
        self, organization: str | None
    ) -> list[IPv4Network | IPv6Network]:
        """
        Get the authorized network list to check for a given organization, or when no organization is available
        """
        # No organization provided, use default authorized networks
        if organization is None:
            return self.authorized_networks
        try:
            organization_id = OrganizationID(organization)
        # Invalid organization, use default authorized networks
        except ValueError:
            return self.authorized_networks
        specific_authorized_networks = self.authorized_networks_by_organization.get(organization_id)
        # If the organization is not configured, use default authorized networks
        if specific_authorized_networks is None:
            logger.warning("No specific configuration for organization `{organization}`")
            return self.authorized_networks
        return specific_authorized_networks

    def is_network_authorized(self, client_ip: str, organization: str | None) -> bool:
        """
        Return `True` if the provided client IP is authorized for the given organization, `False` otherwise.
        """
        try:
            client_address = ip_address(client_ip)
        except ValueError:
            return False
        authorized_networks = self.get_authorized_networks_for_organization(organization)
        return any(client_address in network for network in authorized_networks)

    def is_proxy_authorized(self, proxy: str) -> bool:
        """
        Return `True` if the provided proxy is authorized, `False` otherwise.
        """
        try:
            proxy_ip = ip_address(proxy)
        except ValueError:
            return False
        return any(proxy_ip in proxy for proxy in self.authorized_proxies)

    def path_excluded_from_filtering(self, path: str) -> bool:
        """
        Return `True` if the route is excluded from checking, `False` otherwise.
        """
        return any(fnmatch(path, pattern) for pattern in self.FILTERING_EXCLUDING_PATTERNS)

    def get_local_ip(self, scope: HTTPScope | WebsocketScope) -> str:
        """
        Get the local client IP, as reported by the socket
        """
        client = scope.get("client")
        # This only happens while testing
        if client is None:
            return self.TEST_LOCAL_IP
        local_ip, _ = client
        return local_ip

    def get_client_ip(self, scope: HTTPScope | WebsocketScope) -> str:
        """
        Get the actual client IP, as the one found in the `x-real-ip` header
        """
        x_real_ip = dict(scope["headers"]).get(b"x-real-ip")
        # The header is missing, it means the client connected without a proxy
        # So use the local IP as client IP
        if x_real_ip is None:
            return self.get_local_ip(scope)
        return x_real_ip.decode()

    def get_organization_from_websocket_receive_event(
        self, event: WebsocketReceiveEvent
    ) -> str | None:
        """
        Get the organization from the first websocket event the client sends to the server.

        Note: If the message is invalid (either because it's text, or invalid msgpack, or
        because it does not contain a valid organization), then `None` is returned.
        That means the IP filtering checks will be performed using the generic configuration.
        That's the behavior we want since the parsec app is already secured and able to deal
        with malformed messages.
        """
        # Not a byte message but a text message
        event_bytes = event.get("bytes")
        if event_bytes is None:
            return None
        # Not a msgpack message
        try:
            event_data = unpackb(event_bytes)
        except SerdePackingError:
            return None
        # No organization or not a string
        organization = event_data.get("organization_id")
        if not isinstance(organization, str):
            return None
        return organization

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
        scope = cast("HTTPScope | WebsocketScope", scope)
        if self.path_excluded_from_filtering(scope["path"]):
            return await self.asgi_app(scope, receive, send)

        # HTTP specific
        if scope["type"] == "http":

            # Check that the proxy is authorized
            local_ip = self.get_local_ip(scope)
            if not self.is_proxy_authorized(local_ip):
                logger.info(
                    "An HTTP connection has been rejected (proxy is not authorized)", **scope
                )
                return await self.http_reject(send, self.PROXY_REJECTED_MESSAGE.format(local_ip))

            # Check that the network is authorized
            client_ip = self.get_client_ip(scope)
            organization = self.get_organization_from_path(scope["path"])
            if not self.is_network_authorized(client_ip, organization=organization):
                logger.info(
                    "An HTTP connection has been rejected (network is not authorized)", **scope
                )
                return await self.http_reject(send, self.NETWORK_REJECTED_MESSAGE.format(client_ip))

        # Websocket specific
        else:
            assert scope["type"] == "websocket"

            # Check that the proxy is authorized
            local_ip = self.get_local_ip(scope)
            if not self.is_proxy_authorized(local_ip):
                logger.info(
                    "A websocket connection has been rejected (proxy is not authorized)", **scope
                )
                return await self.websocket_reject(send)

            # Not the websocket route, or no organization-specific configuration is provided
            if (
                scope["path"] != self.WEBSOCKET_ROUTE
                or not self.authorized_networks_by_organization
            ):

                # Check that the network is authorized
                client_ip = self.get_client_ip(scope)
                if not self.is_network_authorized(client_ip, organization=None):
                    logger.info(
                        "An websocket connection has been rejected (network is not authorized)",
                        **scope,
                    )
                    return await self.websocket_reject(send)

            # An organization-specific configuration is provided
            else:
                # Delay the network checks until the first websocket event is received
                scope = cast(WebsocketScope, scope)
                state = WrappedReceiveState()
                receive = partial(self.websocket_wrapped_receive, scope, receive, send, state)

        return await self.asgi_app(scope, receive, send)

    async def websocket_wrapped_receive(
        self,
        scope: WebsocketScope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
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

        # Websocket connection denied
        client_ip = self.get_client_ip(scope)
        organization = self.get_organization_from_websocket_receive_event(event)
        if not self.is_network_authorized(client_ip, organization):
            state.denied = True
            logger.info(
                "A websocket connection has been rejected (network is not authorized)",
                organization=organization,
                **scope,
            )
            await self.websocket_reject(send)
            return self.websocket_disconnect_event

        # Weboscket connection is authorized definitely only if the organization is provided
        # Otherwise, allow the event to pass through but keep checking
        if organization is not None:
            state.authorized = True
        return event

    async def websocket_reject(
        self,
        send: ASGISendCallable,
    ) -> None:
        """
        Close the socket with an `403` HTTP error code.
        """
        close_event: WebsocketCloseEvent = {
            "type": "websocket.close",
            "code": 403,
            "reason": None,
        }
        await send(close_event)
        return

    async def http_reject(
        self,
        send: ASGISendCallable,
        message: str,
    ) -> None:
        """
        Reject the request with an `403` HTTP error code.
        """
        content = message.encode()
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
