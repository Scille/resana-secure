import trio
from uuid import UUID
from typing import Dict, Tuple, Callable, Any
from functools import partial
from quart import current_app
from contextlib import asynccontextmanager

from parsec.api.protocol import InvitationType
from parsec.core.backend_connection import backend_invited_cmds_factory
from parsec.core.types import BackendInvitationAddr
from parsec.core.logged_core import LoggedCore
from parsec.core.config import load_config, CoreConfig
from parsec.core.invite import claimer_retrieve_info


class ClaimNotStarted(Exception):
    pass


class ClaimLifeTimeCtx:
    def __init__(self, initial_ctx):
        self._in_progress_ctx = initial_ctx

    def update_in_progress_ctx(self, new_ctx):
        self._in_progress_ctx = new_ctx

    def get_in_progress_ctx(self):
        return self._in_progress_ctx

    def mark_as_terminated(self):
        self._in_progress_ctx = None

    @classmethod
    async def start(cls, on_started: Callable, config: CoreConfig, addr: BackendInvitationAddr):
        async with backend_invited_cmds_factory(
            addr=addr, keepalive=config.backend_connection_keepalive
        ) as cmds:
            initial_ctx = await claimer_retrieve_info(cmds)
            on_started(cls(initial_ctx))
            await trio.sleep_forever()


class ClaimersManager:
    def __init__(self):
        self._invitation_token_to_claim_ctx: Dict[BackendInvitationAddr, ClaimLifeTimeCtx] = {}
        self._lock = trio.Lock()

    @asynccontextmanager
    async def start_claiming_ctx(self, addr: BackendInvitationAddr) -> ClaimLifeTimeCtx:
        # The lock is needed here to avoid concurrent claim contexts with the same invitation
        async with self._lock:
            existing_handle = self._invitation_token_to_claim_ctx.pop(addr, None)
            if existing_handle:
                await current_app.ltcm.unregister_component(existing_handle)

            config = load_config(current_app.config["CORE_CONFIG_DIR"])
            component_handle = await current_app.ltcm.register_component(
                partial(ClaimLifeTimeCtx.start, config=config, addr=addr)
            )
            self._invitation_token_to_claim_ctx[addr] = component_handle

        # Note we don't protect against concurrent use of the claim context.
        # This is fine given claim contexts are immutables and the Parsec server
        # knows how to deal with concurrent requests.
        async with current_app.ltcm.acquire_component(component_handle) as component:
            yield component

        if component.get_in_progress_ctx() is None:
            await current_app.ltcm.unregister_component(component_handle)

    @asynccontextmanager
    async def retreive_claiming_ctx(self, addr: BackendInvitationAddr) -> ClaimLifeTimeCtx:
        # The lock is needed here to avoid concurrent claim contexts with the same invitation
        async with self._lock:
            try:
                component_handle = self._invitation_token_to_claim_ctx[addr]
            except KeyError:
                raise ClaimNotStarted

        # Note we don't protect against concurrent use of the claim context.
        # This is fine given claim contexts are immutables and the Parsec server
        # knows how to deal with concurrent requests.
        async with current_app.ltcm.acquire_component(component_handle) as component:
            yield component

        if component.get_in_progress_ctx() is None:
            await current_app.ltcm.unregister_component(component_handle)


class GreetLifeTimeCtx:
    def __init__(self, initial_ctx):
        self._in_progress_ctx = initial_ctx

    def update_in_progress_ctx(self, new_ctx):
        self._in_progress_ctx = new_ctx

    def get_in_progress_ctx(self):
        return self._in_progress_ctx

    def mark_as_terminated(self):
        self._in_progress_ctx = None

    @classmethod
    async def start(
        cls,
        on_started: Callable,
        greeters_nursery: trio.Nursery,
        core: LoggedCore,
        addr: BackendInvitationAddr,
    ):
        in_greeters_nursery_cancel_scope = None
        # Here we are in the nursery scope provided by LTCM for our component,
        # we need to jump into the greeters_nursery's scope so that our lifetime
        # is limited by both LTCM and the core we are relying on.
        with trio.CancelScope() as in_ltcm_nursery_cancel_scope:

            async def _start_in_greeters_nursery(task_status=trio.TASK_STATUS_IGNORED):
                nonlocal in_greeters_nursery_cancel_scope
                try:
                    with trio.CancelScope() as in_greeters_nursery_cancel_scope:
                        if addr.invitation_type == InvitationType.USER:
                            initial_ctx = await core.start_greeting_user(addr.token)
                        else:
                            initial_ctx = await core.start_greeting_device(addr.token)
                        on_started(cls(initial_ctx))
                        await trio.sleep_forever()
                finally:
                    in_ltcm_nursery_cancel_scope.cancel()

        greeters_nursery.start_soon(_start_in_greeters_nursery)
        try:
            await trio.sleep_forever()

        finally:
            if in_greeters_nursery_cancel_scope:
                in_greeters_nursery_cancel_scope.cancel()


class GreetersManager:
    def __init__(self):
        self._invitation_token_to_greet_ctx: Dict[UUID, Any] = {}
        self._lock = trio.Lock()
        self._greeters_nursery_per_core: Dict(int, Tuple[LoggedCore, trio.Nursery]) = {}

    def register_greeters_nursery(self, core, greeters_nursery):
        core_id = id(core)
        assert core_id not in self._greeters_nursery_per_core
        # Keep a reference on core take ensure this object won't be garbage
        # collected given id(...) only guarantee unicity for alive objects.
        self._greeters_nursery_per_core[core_id] = (core, greeters_nursery)

    def unregister_greeters_nursery(self, core):
        del self._greeters_nursery_per_core[id(core)]

    @asynccontextmanager
    async def start_greeting_ctx(
        self, core: LoggedCore, addr: BackendInvitationAddr
    ) -> GreetLifeTimeCtx:
        # TODO: handle exceptions
        # The lock is needed here to avoid concurrent claim contexts with the same invitation
        async with self._lock:
            try:
                _, greeters_nursery = self._greeters_nursery_per_core[id(core)]
            except KeyError:
                raise ClaimNotStarted  # TODO: better exception

            existing_handle = self._invitation_token_to_greet_ctx.pop(addr, None)
            if existing_handle:
                await current_app.ltcm.unregister_component(existing_handle)

            component_handle = await current_app.ltcm.register_component(
                partial(
                    GreetLifeTimeCtx.start, greeters_nursery=greeters_nursery, core=core, addr=addr
                )
            )
            self._invitation_token_to_greet_ctx[addr] = component_handle

        # Note we don't protect against concurrent use of the claim context.
        # This is fine given claim contexts are immutables and the Parsec server
        # knows how to deal with concurrent requests.
        async with current_app.ltcm.acquire_component(component_handle) as component:
            yield component

        if component.get_in_progress_ctx() is None:
            await current_app.ltcm.unregister_component(component_handle)

    @asynccontextmanager
    async def retreive_greeting_ctx(self, addr: BackendInvitationAddr) -> ClaimLifeTimeCtx:
        # The lock is needed here to avoid concurrent claim contexts with the same invitation
        async with self._lock:
            try:
                component_handle = self._invitation_token_to_greet_ctx[addr]
            except KeyError:
                raise ClaimNotStarted

        # Note we don't protect against concurrent use of the claim context.
        # This is fine given claim contexts are immutables and the Parsec server
        # knows how to deal with concurrent requests.
        async with current_app.ltcm.acquire_component(component_handle) as component:
            yield component

        if component.get_in_progress_ctx() is None:
            await current_app.ltcm.unregister_component(component_handle)
