# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2016-2021 Scille SAS

import os
import trio
import ssl
import certifi
import h11
from structlog import get_logger
from parsec.api.protocol.handshake import HandshakeOutOfBallparkError
from functools import partial
from base64 import b64encode
from async_generator import asynccontextmanager
from urllib.request import getproxies, proxy_bypass
from urllib.parse import urlsplit, SplitResult
from typing import Optional, Union, List, Tuple
import pypac

from parsec.crypto import SigningKey
from parsec.api.transport import USER_AGENT, Transport, TransportError, TransportClosedByPeer
from parsec.api.protocol import (
    DeviceID,
    ProtocolError,
    HandshakeError,
    BaseClientHandshake,
    AuthenticatedClientHandshake,
    InvitedClientHandshake,
    APIV1_AnonymousClientHandshake,
    APIV1_AdministrationClientHandshake,
    APIV1_AuthenticatedClientHandshake,
)
from parsec.core.types import (
    BackendAddr,
    BackendOrganizationAddr,
    BackendOrganizationBootstrapAddr,
    BackendInvitationAddr,
)
from parsec.core.backend_connection.exceptions import (
    BackendConnectionError,
    BackendNotAvailable,
    BackendConnectionRefused,
    BackendInvitationAlreadyUsed,
    BackendInvitationNotFound,
    BackendOutOfBallparkError,
    BackendProtocolError,
)


logger = get_logger()


async def apiv1_connect(
    addr: Union[BackendAddr, BackendOrganizationBootstrapAddr, BackendOrganizationAddr],
    device_id: Optional[DeviceID] = None,
    signing_key: Optional[SigningKey] = None,
    administration_token: Optional[str] = None,
    keepalive: Optional[int] = None,) -> Transport:
    """
    Raises:
        BackendConnectionError
    """
    handshake: BaseClientHandshake

    if administration_token:
        if not isinstance(addr, BackendAddr):
            raise BackendConnectionError(f"Invalid url format `{addr}`")
        handshake = APIV1_AdministrationClientHandshake(administration_token)

    elif not device_id:
        if isinstance(addr, BackendOrganizationBootstrapAddr):
            handshake = APIV1_AnonymousClientHandshake(addr.organization_id)
        elif isinstance(addr, BackendOrganizationAddr):
            handshake = APIV1_AnonymousClientHandshake(addr.organization_id, addr.root_verify_key)
        else:
            raise BackendConnectionError(
                f"Invalid url format `{addr}` "
                "(should be an organization url or organization bootstrap url)"
            )

    else:
        if not isinstance(addr, BackendOrganizationAddr):
            raise BackendConnectionError(
                f"Invalid url format `{addr}` (should be an organization url)"
            )

        if not signing_key:
            raise BackendConnectionError(f"Missing signing_key to connect as `{device_id}`")
        handshake = APIV1_AuthenticatedClientHandshake(
            addr.organization_id, device_id, signing_key, addr.root_verify_key
        )

    return await _connect(addr.hostname, addr.port, addr.use_ssl, keepalive, handshake)


async def connect_as_invited(addr: BackendInvitationAddr, keepalive: Optional[int] = None):
    handshake = InvitedClientHandshake(
        organization_id=addr.organization_id, invitation_type=addr.invitation_type, token=addr.token
    )
    return await _connect(addr.hostname, addr.port, addr.use_ssl, keepalive, handshake)


async def connect_as_authenticated(
    addr: BackendOrganizationAddr,
    device_id: DeviceID,
    signing_key: SigningKey,
    keepalive: Optional[int] = None,
):
    handshake = AuthenticatedClientHandshake(
        organization_id=addr.organization_id,
        device_id=device_id,
        user_signkey=signing_key,
        root_verify_key=addr.root_verify_key,
    )
    return await _connect(addr.hostname, addr.port, addr.use_ssl, keepalive, handshake)


async def _connect(
    hostname: str,
    port: int,
    use_ssl: bool,
    keepalive: Optional[int],
    handshake: BaseClientHandshake,
) -> Transport:
    stream = await _maybe_connect_through_proxy(hostname, port, use_ssl)

    if not stream:
        logger.debug("Using direct (no proxy) connection", hostname=hostname, port=port)
        try:
            stream = await trio.open_tcp_stream(hostname, port)

        except OSError as exc:
            logger.warning(
                "Impossible to connect to backend", hostname=hostname, port=port, exc_info=exc
            )
            raise BackendNotAvailable(exc) from exc

    if use_ssl:
        logger.debug("Using TLS to secure connection", hostname=hostname)
        stream = _upgrade_stream_to_ssl(stream, hostname)

    try:
        transport = await Transport.init_for_client(stream, host=hostname)
        transport.keepalive = keepalive

    except TransportError as exc:
        logger.warning("Connection lost during transport creation", exc_info=exc)
        raise BackendNotAvailable(exc) from exc

    try:
        await _do_handshake(transport, handshake)

    except BackendOutOfBallparkError:
        transport.logger.info("Abort handshake due to the system clock being out of sync")
        await transport.aclose()
        raise

    except Exception as exc:
        transport.logger.warning("Connection lost during handshake", exc_info=exc)
        await transport.aclose()
        raise

    return transport


def cook_basic_auth_header(username: str, password: str) -> str:
    step1 = f"{username}:{password}".encode("utf8")
    step2 = b64encode(step1).decode("ascii")
    return f"Basic {step2}"


# Global vars to easily set up proxy from config file or cli params


__force_proxy_pac_url = None


def force_proxy_pac_url(url: str) -> None:
    global __force_proxy_pac_url
    __force_proxy_pac_url = url


__force_proxy_url = None


def force_proxy_url(url: str) -> None:
    global __force_proxy_url
    __force_proxy_url = url


def _build_http_url(hostname: str, port: int, use_ssl: bool) -> str:
    if use_ssl:
        url = f"https://{hostname}"
        if port != 443:
            url += f":{port}"
    else:
        url = f"http://{hostname}"
        if port != 80:
            url += f":{port}"
    return url


async def _get_proxy_from_pac_config(hostname: str, port: int, use_ssl: bool) -> Optional[str]:
    # Hack to disable check on content-type (given server migh not be well
    # configured, and `get_pac` silently fails on wrong content-type by returing None)
    # Also disable WPAD protocol to retrieve PAC from DNS given it produce annoying
    # WARNING logs (and it shouldn't be needed for Resana-Secure anyway)
    get_pac_kwargs: dict = {"from_dns": False, "allowed_content_types": {""}}
    if __force_proxy_pac_url:
        get_pac_kwargs["url"] = __force_proxy_pac_url
        logger.debug(
            "Retreiving .PAC proxy config url from forced location", pac_url=__force_proxy_pac_url
        )
    elif __force_proxy_url:
        # Don' try to superstep the forced config !
        return None
    else:
        logger.debug("Retreiving .PAC proxy config url from system")
    try:
        pacfile = await trio.to_thread.run_sync(
            partial(pypac.get_pac, **get_pac_kwargs)
        )
    except Exception as exc:
        logger.warning("Error while retrieving .PAC proxy config", exc_info=exc)
        return None

    if not pacfile:
        return None

    url = _build_http_url(hostname, port, use_ssl)
    try:
        proxies = pacfile.find_proxy_for_url(url, hostname)
        logger.debug("Found proxies info in .PAC proxy config", target_url=url, proxies=proxies)
        proxies = [p.strip() for p in proxies.split(";")]
        if len(proxies) > 1:
            logger.warning(
                "Found multiple proxies info in .PAC proxy config for target, only the first one is going to be used !",
                target_url=url,
                proxies=proxies,
            )
        # We don't handle multiple proxies so keep the first correct one and pray !
        for proxy in proxies:
            if proxy in ("DIRECT", ""):
                # PAC explicitly told us not to use a proxy
                return ""
            elif proxy:
                # Should be of style `PROXY 8.8.8.8:9999`
                proxy_type, proxy_netloc = proxy.strip().split()
                proxy_type = proxy_type.upper()
                if proxy_type in ("PROXY", "HTTP"):
                    return f"http://{proxy_netloc}"
                elif proxy_type == "HTTPS":
                    return f"https://{proxy_netloc}"
                else:
                    logger.warning(
                        "Unsupported proxy type requested by .PAC proxy config",
                        proxy=proxy,
                        target_url=url,
                    )

        else:
            return None

    except Exception as exc:
        logger.warning("Error while using .PAC proxy config", target_url=url, exc_info=exc)
        return None


def _get_proxy_from_os_config(hostname: str, port: int, use_ssl: bool) -> Optional[str]:
    if __force_proxy_url:
        logger.debug("Retreiving proxy from forced location", proxy_url=__force_proxy_url)
        return __force_proxy_url
    elif __force_proxy_pac_url:
        # Don' try to superstep the forced config !
        return None
    else:
        logger.debug("Retreiving proxy from system")

    # Proxy config is accessed two times here: first to check proxy bypass,
    # then to retrieve the proxy url. This is okay enough given proxy config
    # is not supposed to change that often.

    if not proxy_bypass(hostname):
        return None

    proxy_type = "https" if use_ssl else "http"
    proxy_url = getproxies().get(proxy_type)

    return proxy_url


async def _maybe_connect_through_proxy(
    hostname: str, port: int, use_ssl: bool
) -> Optional[trio.abc.Stream]:
    target_url = _build_http_url(hostname, port, use_ssl)

    # First try to get proxy from the infamous PAC config system
    proxy_url = await _get_proxy_from_pac_config(hostname, port, use_ssl)
    if proxy_url:
        logger.debug("Got proxy from .PAC config", proxy_url=proxy_url, target_url=target_url)
    elif proxy_url == "":
        logger.debug("Got .PAC config explictly specifying direct access", target_url=target_url)

    # Fallback on direct proxy url config in environ variables & Windows registers table
    if proxy_url is None:  # `proxy_url == ""` explicitly indicates no proxy should be use
        proxy_url = _get_proxy_from_os_config(hostname, port, use_ssl)
        if proxy_url:
            logger.debug("Got proxy", proxy_url=proxy_url, target_url=target_url)

    if proxy_url in (None, ""):
        return None

    logger.debug("Using proxy to connect", proxy_url=proxy_url, target_url=target_url)

    # A proxy has been retrieved, parse it url and handle potential auth

    try:
        proxy = urlsplit(proxy_url)
        # Typing helper, as result could be SplitResultBytes if we have provided bytes instead of str
        assert isinstance(proxy, SplitResult)
    except ValueError as exc:
        logger.warning(
            "Invalid proxy url, switching to no proxy",
            proxy_url=proxy_url,
            target_url=target_url,
            exc_info=exc,
        )
        # Invalid url
        return None
    if proxy.port:
        proxy_port = proxy.port
    else:
        proxy_port = 443 if proxy.scheme == "https" else 80
    if not proxy.hostname:
        logger.warning(
            "Missing required hostname in proxy url, switching to no proxy",
            proxy_url=proxy_url,
            target_url=target_url,
        )
        return None

    proxy_headers: List[Tuple[str, str]] = []
    if proxy.username is not None and proxy.password is not None:
        logger.debug("Using `Proxy-Authorization` header with proxy", username=proxy.username)
        proxy_headers.append(
            ("Proxy-Authorization", cook_basic_auth_header(proxy.username, proxy.password))
        )

    # Connect to the proxy

    stream: trio.abc.Stream
    try:
        stream = await trio.open_tcp_stream(proxy.hostname, proxy_port)

    except OSError as exc:
        logger.warning(
            "Impossible to connect to proxy",
            proxy_hostname=proxy.hostname,
            proxy_port=proxy_port,
            target_url=target_url,
            exc_info=exc,
        )
        raise BackendNotAvailable(exc) from exc

    if proxy.scheme == "https":
        logger.debug("Using TLS to secure proxy connection", hostname=proxy.hostname)
        stream = _upgrade_stream_to_ssl(stream, proxy.hostname)

    # Ask the proxy to connect the actual host

    conn = h11.Connection(our_role=h11.CLIENT)

    async def send(event):
        data = conn.send(event)
        await stream.send_all(data)

    async def next_event():
        while True:
            event = conn.next_event()
            if event is h11.NEED_DATA:
                # Note there is no need to handle 100 continue here given we are client
                # (see https://h11.readthedocs.io/en/v0.10.0/api.htm1l#flow-control)
                data = await stream.receive_some(2048)
                conn.receive_data(data)
                continue
            return event

    host = f"{hostname}:{port}"
    try:
        req = h11.Request(
            method="CONNECT",
            target=host,
            headers=[
                # According to RFC7230 (https://datatracker.ietf.org/doc/html/rfc7230#section-5.4)
                # Client must provide Host header, but the proxy must replace it
                # with the host information of the request-target. So in theory
                # we could set any dummy value for the Host header here !
                ("Host", host),
                # User-Agent is not a mandatory header, however http proxy are
                # half-broken shenanigans and get suspicious if it is missing
                ("User-Agent", USER_AGENT),
                *proxy_headers,
            ],
        )
        logger.debug("Sending CONNECT to proxy", proxy_url=proxy_url, req=req)
        await send(req)
        answer = await next_event()
        logger.debug("Receiving CONNECT answer from proxy", proxy_url=proxy_url, answer=answer)
        if not isinstance(answer, h11.Response) or not 200 <= answer.status_code < 300:
            logger.warning(
                "Bad answer from proxy to CONNECT request",
                proxy_url=proxy_url,
                target_host=host,
                target_url=target_url,
                answer_status=answer.status_code,
            )
            raise BackendNotAvailable("Bad answer from proxy")
        # Successful CONNECT should reset the connection's statemachine
        answer = await next_event()
        while not isinstance(answer, h11.PAUSED):
            logger.debug(
                "Receiving additional answer to our CONNECT from proxy",
                proxy_url=proxy_url,
                answer=answer,
            )
            answer = await next_event()

    except trio.BrokenResourceError as exc:
        logger.warning(
            "Proxy has unexpectedly closed the connection",
            proxy_url=proxy_url,
            target_host=host,
            target_url=target_url,
            exc_info=exc,
        )
        raise BackendNotAvailable("Proxy has unexpectedly closed the connection") from exc

    return stream


def _upgrade_stream_to_ssl(raw_stream: trio.abc.Stream, hostname: str) -> trio.abc.Stream:
    # The ssl context should be generated once and stored into the config
    # however this is tricky (should ssl configuration be stored per device ?)

    # Don't load default system certificates and rely on our own instead.
    # This is because system certificates are less reliable (and system
    # certificates are tried first, so they can lead to a failure even if
    # we bundle a valid certificate...)
    # Certifi provides Mozilla's carefully curated collection of Root Certificates.
    ssl_context = ssl.create_default_context(
        purpose=ssl.Purpose.SERVER_AUTH, cadata=certifi.contents()
    )

    # Also provide custom certificates if any
    cafile = os.environ.get("SSL_CAFILE")
    if cafile:
        ssl_context.load_verify_locations(cafile)

    return trio.SSLStream(raw_stream, ssl_context, server_hostname=hostname)


async def _do_handshake(transport: Transport, handshake):
    try:
        challenge_req = await transport.recv()
        answer_req = handshake.process_challenge_req(challenge_req)
        await transport.send(answer_req)
        result_req = await transport.recv()
        handshake.process_result_req(result_req)

    except TransportError as exc:
        raise BackendNotAvailable(exc) from exc

    except HandshakeOutOfBallparkError as exc:
        raise BackendOutOfBallparkError(exc) from exc

    except HandshakeError as exc:
        if str(exc) == "Invalid handshake: Invitation not found":
            raise BackendInvitationNotFound(str(exc)) from exc
        elif str(exc) == "Invalid handshake: Invitation already deleted":
            raise BackendInvitationAlreadyUsed(str(exc)) from exc
        else:
            raise BackendConnectionRefused(str(exc)) from exc

    except ProtocolError as exc:
        transport.logger.exception("Protocol error during handshake")
        raise BackendProtocolError(exc) from exc


class TransportPool:
    def __init__(self, connect_cb, max_pool):
        self._connect_cb = connect_cb
        self._transports = []
        self._closed = False
        self._lock = trio.Semaphore(max_pool)

    @asynccontextmanager
    async def acquire(self, force_fresh=False):
        """
        Raises:
            BackendConnectionError
            trio.ClosedResourceError: if used after having being closed
        """
        async with self._lock:
            transport = None
            if not force_fresh:
                try:
                    # Fifo style to retrieve oldest first
                    transport = self._transports.pop(0)
                except IndexError:
                    pass

            if not transport:
                if self._closed:
                    raise trio.ClosedResourceError()

                transport = await self._connect_cb()

            try:
                yield transport

            except TransportClosedByPeer:
                raise

            except Exception:
                await transport.aclose()
                raise

            else:
                self._transports.append(transport)
