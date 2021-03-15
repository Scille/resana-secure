from resana_secure.ltcm import ComponentNotRegistered
import trio
from typing import Dict, Callable, Type, AsyncIterator
from functools import partial
from quart import current_app
from contextlib import asynccontextmanager

from parsec.api.protocol import InvitationType
from parsec.core.backend_connection import (
    backend_invited_cmds_factory,
    backend_authenticated_cmds_factory,
)
from parsec.core.types import LocalDevice, BackendInvitationAddr
from parsec.core.config import load_config, CoreConfig
from parsec.core.invite import claimer_retrieve_info, UserGreetInitialCtx, DeviceGreetInitialCtx


class LongTermCtxNotStarted(Exception):
    pass


class BaseLongTermCtx:
    def __init__(self, initial_ctx):
        self._in_progress_ctx = initial_ctx

    def update_in_progress_ctx(self, new_ctx):
        self._in_progress_ctx = new_ctx

    def get_in_progress_ctx(self):
        return self._in_progress_ctx

    def mark_as_terminated(self):
        self._in_progress_ctx = None

    @asynccontextmanager
    @classmethod
    async def start(
        cls, on_started: Callable, config: CoreConfig, addr: BackendInvitationAddr
    ) -> AsyncIterator["BaseLongTermCtx"]:
        raise NotImplementedError
        yield


class BaseInviteManager:
    _LONG_TERM_CTX_CLS: Type[BaseLongTermCtx]

    def __init__(self):
        self._addr_to_claim_ctx: Dict[BackendInvitationAddr, BaseLongTermCtx] = {}
        self._lock = trio.Lock()

    @asynccontextmanager
    async def start_ctx(
        self, addr: BackendInvitationAddr, **kwargs
    ) -> AsyncIterator[BaseLongTermCtx]:
        # The lock is needed here to avoid concurrent claim contexts with the same invitation
        async with self._lock:
            existing_handle = self._addr_to_claim_ctx.pop(addr, None)
            if existing_handle:
                try:
                    await current_app.ltcm.unregister_component(existing_handle)
                except ComponentNotRegistered:
                    pass

            config = load_config(current_app.config["CORE_CONFIG_DIR"])
            component_handle = await current_app.ltcm.register_component(
                partial(self._LONG_TERM_CTX_CLS.start, config=config, addr=addr, **kwargs)
            )
            self._addr_to_claim_ctx[addr] = component_handle

        # Note we don't protect against concurrent use of the claim context.
        # This is fine given claim contexts are immutables and the Parsec server
        # knows how to deal with concurrent requests.
        try:
            async with current_app.ltcm.acquire_component(component_handle) as component:
                yield component
        except ComponentNotRegistered as exc:
            # The component has probably crashed...
            raise LongTermCtxNotStarted from exc

        if component.get_in_progress_ctx() is None:
            try:
                await current_app.ltcm.unregister_component(component_handle)
            except ComponentNotRegistered:
                pass

    @asynccontextmanager
    async def retreive_ctx(self, addr: BackendInvitationAddr) -> AsyncIterator[BaseLongTermCtx]:
        # The lock is needed here to avoid concurrent claim contexts with the same invitation
        async with self._lock:
            try:
                component_handle = self._addr_to_claim_ctx[addr]
            except KeyError:
                raise LongTermCtxNotStarted

        # Note we don't protect against concurrent use of the claim context.
        # This is fine given claim contexts are immutables and the Parsec server
        # knows how to deal with concurrent requests.
        try:
            async with current_app.ltcm.acquire_component(component_handle) as component:
                yield component
        except ComponentNotRegistered as exc:
            # The component has probably crashed...
            raise LongTermCtxNotStarted from exc

        if component.get_in_progress_ctx() is None:
            try:
                await current_app.ltcm.unregister_component(component_handle)
            except ComponentNotRegistered:
                pass


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
    async def start(
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
