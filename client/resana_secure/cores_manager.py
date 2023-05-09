import trio
from uuid import uuid4
from typing import TYPE_CHECKING, AsyncIterator, Callable, Dict, Optional, Tuple, List, cast
from functools import partial
from pathlib import Path
from contextlib import asynccontextmanager
import structlog
from PyQt5.QtWidgets import QApplication

from parsec._parsec import CoreEvent, list_available_devices
from parsec.core.types import LocalDevice, BackendOrganizationAddr
from parsec.core.logged_core import logged_core_factory, LoggedCore
from parsec.core.local_device import (
    LocalDeviceError,
    AvailableDevice,
)
from parsec.event_bus import EventCallback
from parsec.api.protocol import OrganizationID

from .config import ResanaConfig
from .crypto import decrypt_parsec_key, CryptoError
from .ltcm import ComponentNotRegistered, LTCM

if TYPE_CHECKING:
    from .gui import ResanaGuiApp


logger = structlog.get_logger()


class CoreManagerError(Exception):
    pass


class CoreNotLoggedError(CoreManagerError):
    pass


class CoreDeviceNotFoundError(CoreManagerError):
    pass


class CoreDeviceInvalidPasswordError(CoreManagerError):
    pass


class CoreDeviceEncryptedKeyNotFoundError(CoreManagerError):
    pass


def find_matching_devices(
    config_dir: Path, email: str, organization_id: Optional[OrganizationID] = None
) -> List[AvailableDevice]:
    return [
        d
        for d in list_available_devices(config_dir)
        if (
            (not organization_id or organization_id and d.organization_id == organization_id)
            and d.human_handle
            and d.human_handle.email == email
        )
    ]


def load_device_or_error(available_device: AvailableDevice, password: str) -> Optional[LocalDevice]:
    try:
        return LocalDevice.load_device_with_password(
            key_file=available_device.key_file_path, password=password
        )
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
        # Not using the exception in the log to make sure the encrypted key isn't leaked
        logger.warning("Failed to write the encrypted key to the disk.")


def device_has_encrypted_key(device: AvailableDevice) -> bool:
    return load_device_encrypted_key(device) is not None


def is_org_hosted_on_rie(
    org_addr: BackendOrganizationAddr, rie_server_addrs: List[Tuple[str, Optional[int]]]
) -> bool:
    # `rie_server_addrs` contains a list of tuple of either (domain, port) or (domain, None)
    # We check if our org addr matches either of those.
    # If `rie_server_addrs` we return True for the sake of compatibility
    return (org_addr.hostname, None) in rie_server_addrs or (
        org_addr.hostname,
        org_addr.port,
    ) in rie_server_addrs


@asynccontextmanager
async def start_core(
    config: ResanaConfig, device: LocalDevice, on_stopped: Callable[[], None]
) -> AsyncIterator[LoggedCore]:

    core_config = config.core_config.evolve(
        mountpoint_enabled=is_org_hosted_on_rie(device.organization_addr, config.rie_server_addrs)
    )

    async with logged_core_factory(core_config, device) as core:
        try:
            core.event_bus.connect(
                CoreEvent.FS_ENTRY_SYNC_REJECTED_BY_SEQUESTER_SERVICE,
                cast(EventCallback, _on_fs_sync_refused_by_sequester_service),
            )
            yield core
        finally:
            core.event_bus.disconnect(
                CoreEvent.FS_ENTRY_SYNC_REJECTED_BY_SEQUESTER_SERVICE,
                cast(EventCallback, _on_fs_sync_refused_by_sequester_service),
            )
            on_stopped()


def _on_fs_sync_refused_by_sequester_service(
    event: CoreEvent,
    **kwargs: object,
) -> None:
    if event == CoreEvent.FS_ENTRY_SYNC_REJECTED_BY_SEQUESTER_SERVICE:
        file_path = kwargs["file_path"]
        instance = cast("ResanaGuiApp", QApplication.instance())
        instance.file_rejected.emit(file_path)


class CoresManager:
    def __init__(self, config: ResanaConfig, ltcm: LTCM):
        self._email_to_auth_token: Dict[Tuple[OrganizationID, str], str] = {}
        self._auth_token_to_component_handle: Dict[str, int] = {}
        self._login_lock = trio.Lock()
        self.config = config
        self.ltcm = ltcm

    async def _authenticate(
        self,
        device: AvailableDevice,
        key: Optional[str] = None,
        user_password: Optional[str] = None,
        encrypted_key: Optional[str] = None,
    ) -> str:
        # We have a user password, we're trying to get the device key from it
        if user_password:
            # No encrypted key, meaning we're trying to log in while offline
            if not encrypted_key:
                # Load the key from the file
                encrypted_key = load_device_encrypted_key(device)
                # No key, probably because we never logged while online
                if not encrypted_key:
                    raise CoreDeviceEncryptedKeyNotFoundError
            try:
                # Decrypt the parsec password using the user password
                key = decrypt_parsec_key(user_password, encrypted_key)
            except CryptoError as exc:
                raise CoreDeviceInvalidPasswordError from exc

        # This operation can be done concurrently and ensures the email/password couple is valid
        loaded_device = load_device_or_error(
            available_device=device,
            password=key or "",
        )
        # Everything seems alright, if we have a user_password and an encrypted_key, let's save the encrypted_key so it stays up to date
        if user_password and encrypted_key:
            save_device_encrypted_key(device, encrypted_key=encrypted_key)

        # The lock is needed here to avoid concurrent logins with the same email
        async with self._login_lock:
            assert device.human_handle is not None
            device_tuple = (device.organization_id, device.human_handle.email)
            # Return existing auth_token if the login has already be done for this device
            existing_auth_token = self._email_to_auth_token.get(device_tuple)
            if existing_auth_token:
                # No need to check if the related component is still available
                # given `_on_stopped` callback (see below) makes sure to
                # remove the mapping as soon as the core is starting it teardown
                return existing_auth_token

            # Actual login is required

            def _on_stopped() -> None:
                self._auth_token_to_component_handle.pop(auth_token, None)
                self._email_to_auth_token.pop(device_tuple, None)

            auth_token = uuid4().hex
            component_handle = await self.ltcm.register_component(
                partial(
                    start_core,
                    config=self.config,
                    device=loaded_device,
                    on_stopped=_on_stopped,
                )
            )
            self._auth_token_to_component_handle[auth_token] = component_handle
            self._email_to_auth_token[device_tuple] = auth_token

            return auth_token

    async def login(
        self,
        email: str,
        key: Optional[str] = None,
        user_password: Optional[str] = None,
        encrypted_key: Optional[str] = None,
        organization_id: Optional[OrganizationID] = None,
    ) -> str:
        matching_devices = find_matching_devices(
            self.config.core_config.config_dir, email=email, organization_id=organization_id
        )
        if not matching_devices:
            raise CoreDeviceNotFoundError
        last_exc: Optional[Exception] = None
        for device in matching_devices:
            try:
                return await self._authenticate(
                    device, key=key, user_password=user_password, encrypted_key=encrypted_key
                )
            except CoreManagerError as exc:
                # Expected, just reraise it at the end if we didn't find the device
                last_exc = exc
            except Exception as exc:
                # This is unexpected, log it and reraire it at the end
                logger.exception("Unhandled exception when logging in")
                last_exc = exc
        assert last_exc is not None
        raise last_exc

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

    async def logout_all(self) -> None:
        """
        Raises:
            CoreNotLoggedError
        """
        while self._auth_token_to_component_handle.keys():
            auth_token = next(iter(self._auth_token_to_component_handle))
            component_handle = self._auth_token_to_component_handle[auth_token]

            try:
                await self.ltcm.unregister_component(component_handle)

            except ComponentNotRegistered as exc:
                raise CoreNotLoggedError from exc

    @asynccontextmanager
    async def get_core(self, auth_token: str) -> AsyncIterator[LoggedCore]:
        """
        Raises:
            CoreNotLoggedError
        """
        try:
            component_handle = self._auth_token_to_component_handle[auth_token]

        except KeyError:
            raise CoreNotLoggedError

        try:
            async with self.ltcm.acquire_component(component_handle) as component:
                assert isinstance(component, LoggedCore)
                yield component

        except ComponentNotRegistered as exc:
            raise CoreNotLoggedError from exc

    async def list_available_devices(
        self, only_offline_available: bool = False
    ) -> dict[Tuple[OrganizationID, str], Tuple[AvailableDevice, Optional[str]]]:
        devices = {}
        for available_device in list_available_devices(self.config.core_config.config_dir):
            if only_offline_available and not device_has_encrypted_key(available_device):
                continue
            async with self._login_lock:
                # Check if the device is logged in
                assert available_device.human_handle is not None
                existing_auth_token = self._email_to_auth_token.get(
                    (available_device.organization_id, available_device.human_handle.email)
                )
                key = (available_device.organization_id, available_device.human_handle.email)
                if key not in devices:
                    devices[key] = (available_device, existing_auth_token)
        return devices
