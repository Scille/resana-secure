import trio
from uuid import uuid4
from base64 import b64encode
from typing import Callable, Dict, Optional
from functools import partial
from quart import current_app
from contextlib import asynccontextmanager

from parsec.core.types import LocalDevice
from parsec.core.logged_core import logged_core_factory, LoggedCore
from parsec.core.config import load_config, CoreConfig
from parsec.core.local_device import (
    list_available_devices,
    load_device_with_password,
    LocalDeviceError,
)

from .ltcm import ComponentNotRegistered


class CoreManagerError(Exception):
    pass


class CoreNotLoggedError(CoreManagerError):
    pass


class CoreDeviceNotFoundError(CoreManagerError):
    pass


class CoreDeviceInvalidKeyError(CoreManagerError):
    pass


def load_device_or_error(config: CoreConfig, email: str, key: bytes) -> Optional[LocalDevice]:
    found_email = False
    for available_device in list_available_devices(config.config_dir):
        if available_device.human_handle and available_device.human_handle.email == email:
            found_email = True
            try:
                password = b64encode(key).decode(
                    "ascii"
                )  # TODO: use key (made of bytes) directly instead
                return load_device_with_password(available_device.key_file_path, password)

            except LocalDeviceError:
                # Maybe another device file is available for this email...
                continue
    else:
        if found_email:
            raise CoreDeviceInvalidKeyError
        else:
            raise CoreDeviceNotFoundError


@asynccontextmanager
async def start_core(config: CoreConfig, device: LocalDevice, on_stopped: Callable):
    async with logged_core_factory(config, device) as core:
        try:
            yield core
        finally:
            on_stopped()


class CoresManager:
    def __init__(self):
        self._email_to_auth_token: Dict[str, str] = {}
        self._auth_token_to_component_handle: Dict[str, int] = {}
        self._login_lock = trio.Lock()

    async def login(self, email: str, key: bytes) -> str:
        """
        Raises:
            CoreDeviceNotFoundError
            CoreDeviceInvalidKeyError
        """
        # First load the device from disk
        # This operation can be done concurrently and ensures the email/key couple is valid
        config = load_config(current_app.config["CORE_CONFIG_DIR"])
        device = load_device_or_error(config=config, email=email, key=key)

        # The lock is needed here to avoid concurrent logins with the same email
        async with self._login_lock:
            # Return existing auth_token if the login has already be done for this device
            existing_auth_token = self._email_to_auth_token.get(email)
            if existing_auth_token:
                # No need to check if the related component is still available
                # given `_on_stopped` callback (see below) makes sure to
                # remove the mapping as soon as the core is starting it teardown
                return existing_auth_token

            # Actual login is required

            def _on_stopped():
                self._auth_token_to_component_handle.pop(auth_token, None)
                self._email_to_auth_token.pop(email, None)

            auth_token = uuid4().hex
            component_handle = await current_app.ltcm.register_component(
                partial(start_core, config=config, device=device, on_stopped=_on_stopped)
            )
            self._auth_token_to_component_handle[auth_token] = component_handle
            self._email_to_auth_token[email] = auth_token

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