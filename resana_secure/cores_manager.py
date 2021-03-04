import trio
from uuid import uuid4
from base64 import b64encode
from typing import Dict
from quart import current_app
from contextlib import asynccontextmanager

from parsec.core import logged_core_factory
from parsec.core.config import load_config
from parsec.core.local_device import (
    list_available_devices,
    load_device_with_password,
    LocalDeviceError,
)


class CoreNotLoggedError(Exception):
    pass


class CoreUnknownEmailError(Exception):
    pass


class CoreAlreadyLoggedError(Exception):
    pass


class ReadWriteLock:
    """
    Reader/writer lock with priority of writer
    """

    def __init__(self) -> None:
        self._lock = trio.Lock()
        self._no_writers = trio.Event()
        self._no_writers.set()
        self._no_readers = trio.Event()
        self._no_readers.set()
        self._readers = 0

    @asynccontextmanager
    async def read_acquire(self):
        while True:
            async with self._lock:
                if self._no_writers.is_set():
                    self._readers += 1
                    if self._readers == 1:
                        self._no_readers = trio.Event()
                    break
            await self._no_writers.wait()
        try:
            yield
        finally:
            with trio.CancelScope(shield=True):
                async with self._lock:
                    self._readers -= 1
                    if self._readers == 0:
                        self._no_readers.set()

    @asynccontextmanager
    async def write_acquire(self):
        # First declare ourself as the current writer
        while True:
            async with self._lock:
                if self._no_writers.is_set():
                    # From now on, no other reader/writers can join
                    self._no_writers = trio.Event()
                    break
            # Somebody is already writting, must wait for it to finish
            await self._no_writers.wait()
        # Now we must wait for the readers that arrived before us to finish reading
        await self._no_readers.wait()
        try:
            yield
        finally:
            with trio.CancelScope(shield=True):
                async with self._lock:
                    self._no_writers.set()


class ManagedCore:
    def __init__(self, core, stop_core) -> None:
        self._rwlock = ReadWriteLock()
        self._core = core
        self._stop_core_callback = stop_core

    @classmethod
    async def start(cls, nursery, config, email, key):
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

        async def _run_core(task_status=trio.TASK_STATUS_IGNORED):
            with trio.CancelScope() as cancel_scope:
                core_stopped = trio.Event()

                async def _stop_core():
                    cancel_scope.cancel()
                    await core_stopped.wait()

                try:
                    async with logged_core_factory(config, device) as core:
                        task_status.started((core, _stop_core))
                        await trio.sleep_forever()

                finally:
                    core_stopped.set()

        core, stop_core = await nursery.start(_run_core)
        return cls(core=core, stop_core=stop_core)

    async def stop(self):
        async with self._rwlock.write_acquire():
            await self._stop_core_callback()
            self._core = None

    @asynccontextmanager
    async def acquire_core(self):
        async with self._rwlock.read_acquire():
            if not self._core:
                raise CoreNotLoggedError
            yield self._core


class CoresManager:
    def __init__(self, nursery):
        self.nursery = nursery
        self._cores: Dict[str, ManagedCore] = {}
        self._lock = trio.Lock()

    @classmethod
    @asynccontextmanager
    async def run(cls):
        async with trio.open_nursery() as nursery:
            yield cls(nursery)
            nursery.cancel_scope.cancel()

    @property
    def core_config(self):
        config_dir = current_app.config["CORE_CONFIG_DIR"]
        return load_config(config_dir)

    async def logout(self, auth_token: str) -> None:
        async with self._lock:
            try:
                managed_core = self._cores.pop(auth_token)
            except KeyError:
                raise CoreNotLoggedError()
        await managed_core.stop()

    async def loggin(self, email: str, key: bytes) -> str:
        auth_token = uuid4().hex
        async with self._lock:
            if email in self._cores:
                raise CoreAlreadyLoggedError()
            managed_core = await ManagedCore.start(
                nursery=self.nursery, config=self.core_config, email=email, key=key
            )
            self._cores[auth_token] = managed_core
        return auth_token

    @asynccontextmanager
    async def get_core(self, auth_token: str):
        try:
            managed_core = self._cores[auth_token]
        except KeyError:
            raise CoreNotLoggedError()
        async with managed_core.acquire_core() as core:
            yield core
