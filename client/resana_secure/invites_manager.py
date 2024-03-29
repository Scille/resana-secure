from __future__ import annotations

from contextlib import asynccontextmanager
from functools import partial
from typing import AsyncIterator, Dict, Type

import trio

from parsec.api.protocol import InvitationType
from parsec.core.backend_connection import (
    backend_authenticated_cmds_factory,
    backend_invited_cmds_factory,
)
from parsec.core.config import CoreConfig
from parsec.core.invite import (
    DeviceGreetInitialCtx,
    ShamirRecoveryClaimInitialCtx,
    ShamirRecoveryClaimInProgress1Ctx,
    ShamirRecoveryClaimInProgress2Ctx,
    ShamirRecoveryClaimInProgress3Ctx,
    ShamirRecoveryClaimPreludeCtx,
    ShamirRecoveryGreetInitialCtx,
    UserGreetInitialCtx,
    claimer_retrieve_info,
)
from parsec.core.types import BackendInvitationAddr, LocalDevice
from resana_secure.ltcm import ComponentNotRegistered

from .app import current_app


class LongTermCtxNotStarted(Exception):
    pass


class BaseLongTermCtx:
    def __init__(self, initial_ctx: object) -> None:
        self._in_progress_ctx: object = initial_ctx
        self._lock: trio.Lock = trio.Lock()

    def update_in_progress_ctx(self, new_ctx: object) -> None:
        self._in_progress_ctx = new_ctx

    def get_in_progress_ctx(self) -> object:
        return self._in_progress_ctx

    def mark_as_terminated(self) -> None:
        self._in_progress_ctx = None

    @asynccontextmanager
    @classmethod
    async def start(
        cls, config: CoreConfig, addr: BackendInvitationAddr, previous_component: BaseLongTermCtx
    ) -> AsyncIterator["BaseLongTermCtx"]:
        raise NotImplementedError
        yield  # Needed to respect return type


class BaseInviteManager:
    _LONG_TERM_CTX_CLS: Type[BaseLongTermCtx]

    def __init__(self) -> None:
        self._addr_to_claim_ctx: Dict[BackendInvitationAddr, int] = {}

    @asynccontextmanager
    async def start_ctx(
        self,
        addr: BackendInvitationAddr,
        **kwargs: object,
    ) -> AsyncIterator[BaseLongTermCtx]:
        old_component_handle = self._addr_to_claim_ctx.get(addr)

        component_handle = await current_app.ltcm.register_component(
            partial(
                self._LONG_TERM_CTX_CLS.start,
                config=current_app.resana_config.core_config,
                addr=addr,
                **kwargs,
            ),
            replacing=old_component_handle,
        )

        # Register the component and teardown any previous one
        if old_component_handle:
            await self._stop_ctx(addr, old_component_handle)
        self._addr_to_claim_ctx[addr] = component_handle

        try:
            async with current_app.ltcm.acquire_component(component_handle) as component:
                # LTCM allow concurrent access to the component, however our
                # invitation components rely on a single backend transport
                # connection so we need a lock here to avoid concurrent
                # operations on it
                assert isinstance(component, BaseLongTermCtx)
                async with component._lock:
                    yield component

        except ComponentNotRegistered as exc:
            # The component has probably crashed...
            raise LongTermCtxNotStarted from exc

        if component.get_in_progress_ctx() is None:
            await self._stop_ctx(addr, component_handle)

    async def _stop_ctx(self, addr: BackendInvitationAddr, component_handle: int) -> None:
        try:
            await current_app.ltcm.unregister_component(component_handle)
        except ComponentNotRegistered:
            pass
        removed_component_handle = self._addr_to_claim_ctx.pop(addr, None)
        if removed_component_handle is not None and removed_component_handle != component_handle:
            # Ooops ! The component we've been asked to stop has already been
            # replaced by another one in the addr to claim dict, just pretent
            # we did nothing and move on ;-)
            self._addr_to_claim_ctx[addr] = removed_component_handle

    @asynccontextmanager
    async def retrieve_ctx(self, addr: BackendInvitationAddr) -> AsyncIterator[BaseLongTermCtx]:
        try:
            component_handle = self._addr_to_claim_ctx[addr]
        except KeyError:
            raise LongTermCtxNotStarted

        try:
            async with current_app.ltcm.acquire_component(component_handle) as component:
                # LTCM allow concurrent access to the component, however our
                # invitation components rely on a single backend transport
                # connection so we need a lock here to avoid concurrent
                # operations on it
                assert isinstance(component, BaseLongTermCtx)
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
        cls,
        config: CoreConfig,
        addr: BackendInvitationAddr,
        previous_component: BaseLongTermCtx | None = None,
    ) -> AsyncIterator["ClaimLongTermCtx"]:
        async with backend_invited_cmds_factory(
            addr=addr, keepalive=config.backend_connection_keepalive
        ) as cmds:
            initial_ctx = await claimer_retrieve_info(cmds)

            # In the case of a shamir recovery
            if (
                isinstance(initial_ctx, ShamirRecoveryClaimPreludeCtx)
                and previous_component is not None
            ):
                previous_ctx = previous_component.get_in_progress_ctx()

                # Get previous prelude
                if isinstance(previous_ctx, ShamirRecoveryClaimPreludeCtx):
                    previous_prelude = previous_ctx
                elif isinstance(
                    previous_ctx,
                    (
                        ShamirRecoveryClaimInitialCtx,
                        ShamirRecoveryClaimInProgress1Ctx,
                        ShamirRecoveryClaimInProgress2Ctx,
                        ShamirRecoveryClaimInProgress3Ctx,
                    ),
                ):
                    previous_prelude = previous_ctx.prelude
                else:
                    previous_prelude = None

                # Patch new prelude
                if previous_prelude is not None:
                    initial_ctx.recovered = previous_prelude.recovered

            yield cls(initial_ctx)


class ClaimersManager(BaseInviteManager):
    _LONG_TERM_CTX_CLS = ClaimLongTermCtx


class GreetLongTermCtx(BaseLongTermCtx):
    @classmethod
    @asynccontextmanager
    async def start(  # type: ignore[override]
        cls,
        config: CoreConfig,
        device: LocalDevice,
        addr: BackendInvitationAddr,
        previous_component: BaseLongTermCtx | None = None,
    ) -> AsyncIterator[GreetLongTermCtx]:
        async with backend_authenticated_cmds_factory(
            addr=device.organization_addr,
            device_id=device.device_id,
            signing_key=device.signing_key,
            keepalive=config.backend_connection_keepalive,
        ) as cmds:

            if addr.invitation_type == InvitationType.USER:
                user_initial_ctx = UserGreetInitialCtx(cmds=cmds, token=addr.token)
                user_in_progress_ctx = await user_initial_ctx.do_wait_peer()
                instance = cls(user_in_progress_ctx)
            elif addr.invitation_type == InvitationType.DEVICE:
                device_initial_ctx = DeviceGreetInitialCtx(cmds=cmds, token=addr.token)
                device_in_progress_ctx = await device_initial_ctx.do_wait_peer()
                instance = cls(device_in_progress_ctx)
            elif addr.invitation_type == InvitationType.SHAMIR_RECOVERY:
                shamir_recovery_initial_ctx = ShamirRecoveryGreetInitialCtx(
                    cmds=cmds, token=addr.token
                )
                shamir_recovery_in_progress_ctx = await shamir_recovery_initial_ctx.do_wait_peer()
                instance = cls(shamir_recovery_in_progress_ctx)
            else:
                assert False
            yield instance


class GreetersManager(BaseInviteManager):
    _LONG_TERM_CTX_CLS = GreetLongTermCtx
