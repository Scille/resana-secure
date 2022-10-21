import trio
from uuid import uuid4
from typing import AsyncIterator, Callable, Dict, Optional, Tuple
from functools import partial
from quart import current_app
from pathlib import Path
from contextlib import asynccontextmanager
import structlog
from PyQt5.QtWidgets import QApplication

from parsec.core.core_events import CoreEvent
from parsec.core.types import LocalDevice
from parsec.core.logged_core import logged_core_factory, LoggedCore
from parsec.core.config import CoreConfig
from parsec.core.local_device import (
    list_available_devices,
    load_device_with_password,
    LocalDeviceError,
)
from parsec.api.protocol import OrganizationID


from .ltcm import ComponentNotRegistered


logger = structlog.get_logger()


class CoreManagerError(Exception):
    pass


class CoreNotLoggedError(CoreManagerError):
    pass


class CoreDeviceNotFoundError(CoreManagerError):
    pass


class CoreDeviceInvalidPasswordError(CoreManagerError):
    pass


def load_device_or_error(
    config_dir: Path, email: str, password: str, organization_id: Optional[OrganizationID] = None
) -> Optional[LocalDevice]:
    found_email = False
    for available_device in list_available_devices(config_dir):
        if (
            (
                not organization_id
                or organization_id
                and available_device.organization_id == organization_id
            )
            and available_device.human_handle
            and available_device.human_handle.email == email
        ):
            found_email = True
            try:
                return load_device_with_password(
                    key_file=available_device.key_file_path, password=password
                )

            except LocalDeviceError:
                # Maybe another device file is available for this email...
                continue
    else:
        if found_email:
            raise CoreDeviceInvalidPasswordError
        else:
            raise CoreDeviceNotFoundError


@asynccontextmanager
async def start_core(
    config: CoreConfig, device: LocalDevice, on_stopped: Callable
) -> AsyncIterator[LoggedCore]:
    async with logged_core_factory(config, device) as core:
        try:
            core.event_bus.connect(
                CoreEvent.FS_ENTRY_SYNC_REJECTED_BY_SEQUESTER_SERVICE,
                _on_fs_sync_refused_by_sequester_service,
            )
            yield core
        finally:
            core.event_bus.disconnect(
                CoreEvent.FS_ENTRY_SYNC_REJECTED_BY_SEQUESTER_SERVICE,
                _on_fs_sync_refused_by_sequester_service,
            )
            on_stopped()


async def _on_fs_sync_refused_by_sequester_service(
    event,
    file_path,
    **kwargs,
):
    if event == CoreEvent.FS_ENTRY_SYNC_REJECTED_BY_SEQUESTER_SERVICE:
        trio.to_thread.run_sync(
            QApplication.message_requested.emit,
            "Fichier malicieux détecté",
            f"Le fichier `{file_path}` a été détecté comme malicieux. Il ne sera pas synchronisé.",
        )


class CoresManager:
    def __init__(self):
        self._email_to_auth_token: Dict[Tuple(OrganizationID, str), str] = {}
        self._auth_token_to_component_handle: Dict[str, int] = {}
        self._login_lock = trio.Lock()

    async def login(
        self, email: str, password: str, organization_id: Optional[OrganizationID] = None
    ) -> str:
        """
        Raises:
            CoreDeviceNotFoundError
            CoreDeviceInvalidPasswordError
        """
        config = current_app.config["CORE_CONFIG"]
        # First load the device from disk
        # This operation can be done concurrently and ensures the email/password couple is valid
        device = load_device_or_error(
            config_dir=config.config_dir,
            email=email,
            password=password,
            organization_id=organization_id,
        )

        # The lock is needed here to avoid concurrent logins with the same email
        async with self._login_lock:
            # Return existing auth_token if the login has already be done for this device
            existing_auth_token = self._email_to_auth_token.get((organization_id, email))
            if existing_auth_token:
                # No need to check if the related component is still available
                # given `_on_stopped` callback (see below) makes sure to
                # remove the mapping as soon as the core is starting it teardown
                return existing_auth_token

            # Actual login is required

            def _on_stopped():
                self._auth_token_to_component_handle.pop(auth_token, None)
                self._email_to_auth_token.pop((organization_id, email), None)

            auth_token = uuid4().hex
            component_handle = await current_app.ltcm.register_component(
                partial(start_core, config=config, device=device, on_stopped=_on_stopped)
            )
            self._auth_token_to_component_handle[auth_token] = component_handle
            self._email_to_auth_token[(organization_id, email)] = auth_token

            return auth_token

    async def logout(self, auth_token: str) -> None:
        """
        Raises:
            CoreNotLoggedError
        """
        # Unlike login, logout is idempotent (because LTCM.unregister_component is)
        # so it's ok to have concurrent call with the same auth_token
        try:
            component_handle = self._auth_token_to_component_handle[auth_token]

        except KeyError:
            raise CoreNotLoggedError

        try:
            await current_app.ltcm.unregister_component(component_handle)

        except ComponentNotRegistered as exc:
            raise CoreNotLoggedError from exc

    @asynccontextmanager
    async def get_core(self, auth_token: str) -> LoggedCore:
        """
        Raises:
            CoreNotLoggedError
        """
        try:
            component_handle = self._auth_token_to_component_handle[auth_token]

        except KeyError:
            raise CoreNotLoggedError

        try:
            async with current_app.ltcm.acquire_component(component_handle) as component:
                yield component

        except ComponentNotRegistered as exc:
            raise CoreNotLoggedError from exc
