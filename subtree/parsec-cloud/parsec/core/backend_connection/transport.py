# Parsec Cloud (https://parsec.cloud) Copyright (c) AGPLv3 2016-2021 Scille SAS

import os
import trio
import ssl
import certifi
import h11
from structlog import get_logger
from typing import Optional
from parsec.api.protocol.handshake import HandshakeOutOfBallparkError
from base64 import b64encode
from async_generator import asynccontextmanager
from urllib.request import getproxies, proxy_bypass
from urllib.parse import urlsplit, SplitResult

from parsec.crypto import SigningKey
from parsec.api.transport import Transport, TransportError, TransportClosedByPeer
from parsec.api.protocol import (
    DeviceID,
    ProtocolError,
    HandshakeError,
    BaseClientHandshake,
    AuthenticatedClientHandshake,
    InvitedClientHandshake,
    APIV1_AnonymousClientHandshake,
)
from parsec.core.types import (
    BackendOrganizationAddr,
    BackendOrganizationBootstrapAddr,
    BackendInvitationAddr,
)
from parsec.core.backend_connection.exceptions import (
    BackendNotAvailable,
    BackendConnectionRefused,
    BackendInvitationAlreadyUsed,
    BackendInvitationNotFound,
    BackendOutOfBallparkError,
    BackendProtocolError,
)


logger = get_logger()


async def apiv1_connect(
    addr: BackendOrganizationBootstrapAddr, keepalive: Optional[int] = None
) -> Transport:
    """
    Raises:
        BackendConnectionError
    """
    handshake = APIV1_AnonymousClientHandshake(addr.organization_id)
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
        try:
            stream = await trio.open_tcp_stream(hostname, port)

        except OSError as exc:
            logger.warning(
                "Impossible to connect to backend", hostname=hostname, port=port, exc_info=exc
            )
            raise BackendNotAvailable(exc) from exc

    if use_ssl:
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


async def _maybe_connect_through_proxy(
    hostname: str, port: int, use_ssl: bool
) -> Optional[trio.abc.Stream]:
    # Proxy config is accessed two times here: first to check proxy bypass,
    # then to retrieve the proxy url. This is okay enough given proxy config
    # is not supposed to change that often.

    if proxy_bypass(hostname):
        return None

    proxy_type = "https" if use_ssl else "http"
    proxy_url = getproxies().get(proxy_type)
    if not proxy_url:
        return None
    try:
        proxy = urlsplit(proxy_url)
        # Typing helper, as result could be SplitResultBytes if we have provided bytes instead of str
        assert isinstance(proxy, SplitResult)
    except ValueError:
        # Invalid url
        return None
    if proxy.port:
        proxy_port = proxy.port
    else:
        proxy_port = 443 if proxy.scheme == "https" else 80
    if not proxy.hostname:
        return None
    proxy_headers = []
    if proxy.username is not None and proxy.password is not None:
        proxy_headers.append(
            ("Proxy-Authorization", cook_basic_auth_header(proxy.username, proxy.password))
        )

    # Connect to the proxy

    stream: trio.abc.Stream
    try:
        stream = await trio.open_tcp_stream(proxy.hostname, proxy_port)

    except OSError as exc:
        logger.warning("Impossible to connect to proxy", reason=exc)
        raise BackendNotAvailable(exc) from exc

    if proxy.scheme == "https":
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
                data = await stream.receive_some(2048)
                conn.receive_data(data)
                continue
            return event

    host = f"{hostname}:{port}"
    try:
        await send(
            h11.Request(
                method="CONNECT",
                target=host,
                headers=[
                    # According to RFC7230 (https://datatracker.ietf.org/doc/html/rfc7230#section-5.4)
                    # Client must provide Host header, but the proxy must replace it
                    # with the host information of the request-target. So in theory
                    # we could set any dummy value for the Host header here !
                    ("Host", host),
                    *proxy_headers,
                ],
            )
        )
        answer = await next_event()
        if not isinstance(answer, h11.Response) or not 200 <= answer.status_code < 300:
            logger.warning("Bad answer from proxy", answer=answer, target_host=host)
            raise BackendNotAvailable("Bad answer from proxy")

    except trio.BrokenResourceError as exc:
        logger.warning(
            "Proxy has unexpectedly closed the connection", exc_info=exc, target_host=host
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
