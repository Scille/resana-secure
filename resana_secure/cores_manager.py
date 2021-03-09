import trio
from uuid import uuid4
from base64 import b64encode
from typing import Dict
from functools import partial
from quart import current_app
from contextlib import asynccontextmanager

from parsec.core.logged_core import logged_core_factory, LoggedCore
from parsec.core.config import load_config, CoreConfig
from parsec.core.local_device import (
    list_available_devices,
    load_device_with_password,
    LocalDeviceError,
)

from .ltcm import ComponentNotRegistered


class CoreNotLoggedError(Exception):
    pass


class CoreUnknownEmailError(Exception):
    pass


class CoreAlreadyLoggedError(Exception):
    pass


@asynccontextmanager
async def start_core(config: CoreConfig, email: str, key: bytes):
    for available_device in list_available_devices(config.config_dir):
        if available_device.human_handle and available_device.human_handle.email == email:
            try:
                password = b64encode(key).decode(
                    "ascii"
                )  # TODO: use key (made of bytes) directly instead
                device = load_device_with_password(available_device.key_file_path, password)
                break

            except LocalDeviceError:
                # Maybe another device file is available for this email...
                continue

    else:
        raise CoreUnknownEmailError("No avaible device for this email")

    async with logged_core_factory(config, device) as core:
        yield core


class CoresManager:
    def __init__(self):
        self._email_to_auth_token: Dict[str, str] = {}
        self._auth_token_to_component_handle: Dict[str, int] = {}
        self._login_lock = trio.Lock()

    async def login(self, email: str, key: bytes) -> str:
        # The lock is needed here to avoid concurrent logins with the same email
        async with self._login_lock:
            existing_auth_token = self._email_to_auth_token.get(email)
            if current_app.ltcm.is_registered_component(existing_auth_token):
                raise CoreAlreadyLoggedError

            auth_token = uuid4().hex
            config = load_config(current_app.config["CORE_CONFIG_DIR"])
            component_handle = await current_app.ltcm.register_component(
                partial(start_core, config=config, email=email, key=key)
            )
            self._auth_token_to_component_handle[auth_token] = component_handle
            self._email_to_auth_token[email] = auth_token

            return auth_token

    async def logout(self, auth_token: str) -> None:
        # Unlike login, logout is idempotent (because LTCM.unregister_component is)
        # so it's ok to have concurrent call with the same auth_token
        try:
            component_handle = self._auth_token_to_component_handle[auth_token]

        except KeyError:
            raise CoreNotLoggedError

        try:
            await current_app.ltcm.unregister_component(component_handle)
            # Clear token-to-handle mapping last to avoid unreaching component
            # if cancellation occurs during logout at the wrong time
            self._auth_token_to_component_handle.pop(auth_token, None)

        except ComponentNotRegistered as exc:
            self._auth_token_to_component_handle.pop(auth_token, None)
            raise CoreNotLoggedError from exc

    @asynccontextmanager
    async def get_core(self, auth_token: str) -> LoggedCore:
        try:
            component_handle = self._auth_token_to_component_handle[auth_token]

        except KeyError:
            raise CoreNotLoggedError

        try:
            async with current_app.ltcm.acquire_component(component_handle) as component:
                yield component

        except ComponentNotRegistered as exc:
            raise CoreNotLoggedError from exc
