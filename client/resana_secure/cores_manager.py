import trio
from uuid import uuid4
from typing import AsyncIterator, Callable, Dict, Optional, Tuple, Generator
from functools import partial
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
    AvailableDevice,
)
from parsec.api.protocol import OrganizationID


from .crypto import decrypt_parsec_key, CryptoError
from .ltcm import ComponentNotRegistered, LTCM


logger = structlog.get_logger()


class CoreManagerError(Exception):
    pass


class CoreNotLoggedError(CoreManagerError):
    pass


class CoreDeviceNotFoundError(CoreManagerError):
    pass


class CoreDeviceInvalidPasswordError(CoreManagerError):
    pass


def iter_matching_devices(
    config_dir: Path, email: str, organization_id: Optional[OrganizationID] = None
) -> Generator[AvailableDevice]:
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
            yield available_device


def load_device_or_error(available_device: AvailableDevice, password: str) -> Optional[LocalDevice]:
    try:
        return load_device_with_password(key_file=available_device.key_file_path, password=password)
    except LocalDeviceError:
        raise CoreDeviceInvalidPasswordError


def load_device_encrypted_key(device: AvailableDevice) -> Optional[str]:
    try:
        return (device.key_file_path.parent / f"{device.slughash}.enc_key").read_text()
    except OSError:
        return None


def save_device_encrypted_key(device: AvailableDevice, encrypted_key: str) -> None:
    try:
        (device.key_file_path.parent / f"{device.slughash}.enc_key").write_text(encrypted_key)
    except OSError:
        pass


def device_has_encrypted_key(device: AvailableDevice) -> bool:
    return load_device_encrypted_key(device) is not None


@asynccontextmanager
async def start_core(
    core_config: CoreConfig, device: LocalDevice, on_stopped: Callable
) -> AsyncIterator[LoggedCore]:
    async with logged_core_factory(core_config, device) as core:
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
    _instance = None

    def __init__(self, core_config: CoreConfig, ltcm: LTCM):
        self._email_to_auth_token: Dict[Tuple[OrganizationID, str], str] = {}
        self._auth_token_to_component_handle: Dict[str, int] = {}
        self._login_lock = trio.Lock()
        self.core_config = core_config
        self.ltcm = ltcm

    async def login(
        self,
        email: str,
        key: Optional[str] = None,
        user_password: Optional[str] = None,
        encrypted_key: Optional[str] = None,
        organization_id: Optional[OrganizationID] = None,
    ) -> str:
        """
        Raises:
            CoreDeviceNotFoundError
            CoreDeviceInvalidPasswordError
        """

        device = None
        found_device = False

        # We iterate over the devices that match this email and organization_id (usually we only get one but we may have more in some cases)
        for available_device in iter_matching_devices(
            self.core_config.config_dir, email=email, organization_id=organization_id
        ):
            # Indicate that we did find a device, useful for the final error
            found_device = True

            # We have a user password
            if user_password:
                # But not encrypted key, meaning we're trying to log offline
                if not encrypted_key:
                    # Load the key from the file
                    encrypted_key = load_device_encrypted_key(available_device)
                # No key, probably because we never logged while online, let's try the next device
                if not encrypted_key:
                    continue
                try:
                    # Decrypt the parsec password using the user password
                    key = decrypt_parsec_key(user_password, encrypted_key)
                except CryptoError:
                    # Let's try the next device
                    continue
            try:
                # This operation can be done concurrently and ensures the email/password couple is valid
                device = load_device_or_error(
                    available_device=available_device,
                    password=key or "",
                )
            except (CoreDeviceNotFoundError, CoreDeviceInvalidPasswordError):
                # Cannot authenticate the device, let's try the next device
                continue
            else:
                # Everything seems alright, if we have a user_password and an encrypted_key, let's save the encrypted_key so it stays up to date
                if user_password and encrypted_key:
                    save_device_encrypted_key(available_device, encrypted_key=encrypted_key)
                break

        # We did not find a matching device
        if not found_device:
            raise CoreDeviceNotFoundError
        # We did find a matching device but did not manage to authenticate
        if found_device and not device:
            raise CoreDeviceInvalidPasswordError

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
            component_handle = await self.ltcm.register_component(
                partial(
                    start_core, core_config=self.core_config, device=device, on_stopped=_on_stopped
                )
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
            await self.ltcm.unregister_component(component_handle)

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
            async with self.ltcm.acquire_component(  # type: ignore[var-annotated]
                component_handle
            ) as component:
                yield component

        except ComponentNotRegistered as exc:
            raise CoreNotLoggedError from exc

    async def list_available_devices(
        self, only_offline_available: bool = False
    ) -> dict[Tuple[OrganizationID, str], Tuple[AvailableDevice, Optional[str]]]:
        devices = {}
        for available_device in list_available_devices(self.core_config.config_dir):
            if only_offline_available and not device_has_encrypted_key(available_device):
                continue
            # The lock is needed here to avoid concurrent logins with the same email
            async with self._login_lock:
                # Check if the device is logged in
                existing_auth_token = self._email_to_auth_token.get(
                    (available_device.organization_id, available_device.human_handle.email)
                )
                # Ensuring that two devices from the same user only appear once
                # It doesn't really matter if there are many devices with the same email and org_id,
                # when login we try them all anyway.
                key = (available_device.organization_id, available_device.human_handle.email)
                if key not in devices:
                    devices[key] = (available_device, existing_auth_token)
        return devices
