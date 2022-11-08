from resana_secure.ltcm import ComponentNotRegistered
import trio
from typing import Dict, Type, AsyncIterator
from functools import partial
from quart import current_app, g
from contextlib import asynccontextmanager

from parsec.api.protocol import InvitationType
from parsec.core.backend_connection import (
    backend_invited_cmds_factory,
    backend_authenticated_cmds_factory,
)
from parsec.core.types import LocalDevice, BackendInvitationAddr
from parsec.core.config import CoreConfig
from parsec.core.invite import claimer_retrieve_info, UserGreetInitialCtx, DeviceGreetInitialCtx


class LongTermCtxNotStarted(Exception):
    pass


class BaseLongTermCtx:
    def __init__(self, initial_ctx):
        self._in_progress_ctx = initial_ctx
        self._lock = trio.Lock()

    def update_in_progress_ctx(self, new_ctx):
        self._in_progress_ctx = new_ctx

    def get_in_progress_ctx(self):
        return self._in_progress_ctx

    def mark_as_terminated(self):
        self._in_progress_ctx = None

    @asynccontextmanager
    @classmethod
    async def start(
        cls, config: CoreConfig, addr: BackendInvitationAddr
    ) -> AsyncIterator["BaseLongTermCtx"]:
        raise NotImplementedError
        yield  # Needed to respect return type


class BaseInviteManager:
    _LONG_TERM_CTX_CLS: Type[BaseLongTermCtx]

    def __init__(self):
        self._addr_to_claim_ctx: Dict[BackendInvitationAddr, BaseLongTermCtx] = {}

    @asynccontextmanager
    async def start_ctx(
        self, addr: BackendInvitationAddr, **kwargs
    ) -> AsyncIterator[BaseLongTermCtx]:
        component_handle = await g.ltcm.register_component(
            partial(
                self._LONG_TERM_CTX_CLS.start,
                config=current_app.config["CORE_CONFIG"],
                addr=addr,
                **kwargs
            )
        )

        # Register the component and teardown any previous one
        old_component_handle = self._addr_to_claim_ctx.get(addr)
        if old_component_handle:
            await self._stop_ctx(addr, old_component_handle)
        self._addr_to_claim_ctx[addr] = component_handle

        try:
            async with g.ltcm.acquire_component(component_handle) as component:
                # LTCM allow concurrent access to the component, however our
                # invitation components rely on a single backend transport
                # connection so we need a lock here to avoid concurrent
                # operations on it
                async with component._lock:
                    yield component

        except ComponentNotRegistered as exc:
            # The component has probably crashed...
            raise LongTermCtxNotStarted from exc

        if component.get_in_progress_ctx() is None:
            await self._stop_ctx(addr, component_handle)

    async def _stop_ctx(self, addr, component_handle):
        try:
            await g.ltcm.unregister_component(component_handle)
        except ComponentNotRegistered:
            pass
        removed_component_handle = self._addr_to_claim_ctx.pop(addr, None)
        if removed_component_handle is not None and removed_component_handle != component_handle:
            # Ooops ! The component we've been asked to stop has already been
            # replaced by another one in the addr to claim dict, just pretent
            # we did nothing and move and ;-)
            self._addr_to_claim_ctx[addr] = removed_component_handle

    @asynccontextmanager
    async def retreive_ctx(self, addr: BackendInvitationAddr) -> AsyncIterator[BaseLongTermCtx]:
        try:
            component_handle = self._addr_to_claim_ctx[addr]
        except KeyError:
            raise LongTermCtxNotStarted

        try:
            async with g.ltcm.acquire_component(component_handle) as component:
                # LTCM allow concurrent access to the component, however our
                # invitation components rely on a single backend transport
                # connection so we need a lock here to avoid concurrent
                # operations on it
                async with component._lock:
                    yield component

        except ComponentNotRegistered as exc:
            # The component has probably crashed...
            raise LongTermCtxNotStarted from exc

        if component.get_in_progress_ctx() is None:
            await self._stop_ctx(addr, component_handle)


class ClaimLongTermCtx(BaseLongTermCtx):
    @classmethod
    @asynccontextmanager
    async def start(
        cls, config: CoreConfig, addr: BackendInvitationAddr
    ) -> AsyncIterator["ClaimLongTermCtx"]:
        async with backend_invited_cmds_factory(
            addr=addr, keepalive=config.backend_connection_keepalive
        ) as cmds:
            initial_ctx = await claimer_retrieve_info(cmds)
            yield cls(initial_ctx)


class ClaimersManager(BaseInviteManager):
    _LONG_TERM_CTX_CLS = ClaimLongTermCtx


class GreetLongTermCtx(BaseLongTermCtx):
    @classmethod
    @asynccontextmanager
    async def start(  # type: ignore[override]
        cls, config: CoreConfig, device: LocalDevice, addr: BackendInvitationAddr
    ) -> AsyncIterator["GreetLongTermCtx"]:
        async with backend_authenticated_cmds_factory(
            addr=device.organization_addr,
            device_id=device.device_id,
            signing_key=device.signing_key,
            keepalive=config.backend_connection_keepalive,
        ) as cmds:

            if addr.invitation_type == InvitationType.USER:
                initial_ctx = UserGreetInitialCtx(cmds=cmds, token=addr.token)
                in_progress_ctx = await initial_ctx.do_wait_peer()
            else:
                initial_ctx = DeviceGreetInitialCtx(cmds=cmds, token=addr.token)
                in_progress_ctx = await initial_ctx.do_wait_peer()

            yield cls(in_progress_ctx)


class GreetersManager(BaseInviteManager):
    _LONG_TERM_CTX_CLS = GreetLongTermCtx
