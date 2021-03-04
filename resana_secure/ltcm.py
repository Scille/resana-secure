import trio
from typing import Callable, Dict, TypeVar, Optional
from contextlib import asynccontextmanager


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


class ComponentNotRegistered(Exception):
    pass


ComponentTypeVar = TypeVar("ComponentTypeVar")


class ManagedComponent:
    def __init__(self, component: ComponentTypeVar, stop_component: Callable) -> None:
        self._rwlock = ReadWriteLock()
        self._component: Optional[ComponentTypeVar] = component
        self._stop_component_callback = stop_component

    @classmethod
    async def run(cls, component_factory: Callable, task_status=trio.TASK_STATUS_IGNORED):
        with trio.CancelScope() as cancel_scope:
            component_stopped = trio.Event()

            async def _stop_component():
                cancel_scope.cancel()
                await component_stopped.wait()

            try:
                async with component_factory() as component:
                    managed_component = cls(component=component, stop_component=_stop_component)
                    task_status.started(managed_component)
                    await trio.sleep_forever()

            finally:
                component_stopped.set()

        async def stop(self):
            async with self._rwlock.write_acquire():
                # _stop_component_callback is idempotent so no need to check
                # if the component is actually still running
                await self._stop_component_callback()
                self._component = None

    @asynccontextmanager
    async def acquire(self) -> ComponentTypeVar:
        # TODO: kill the reader instead of just waiting for them to finish ?
        async with self._rwlock.read_acquire():
            if self._component is None:
                raise ComponentNotRegistered
            yield self._component


class LTCM:
    """
    Long Time Component Management.
    Also manages greeter/claimer invite context, but I didn't waint to spoil the cool name ;-)
    """

    def __init__(self, nursery):
        self._nursery = nursery
        self._lock = trio.Lock()
        self._components: Dict[int, ManagedComponent] = {}

    @classmethod
    @asynccontextmanager
    async def run(cls):
        async with trio.open_nursery() as nursery:
            yield cls(nursery)
            nursery.cancel_scope.cancel()

    async def register_component(self, component_factory: Callable) -> int:
        async with self._lock:
            managed_component = await self._nursery.start(ManagedComponent.run, component_factory)
            handle = id(managed_component)
            self._components[handle] = managed_component
            return handle

    async def unregister_component(self, handle: int) -> None:
        async with self._lock:
            try:
                managed_component = self._components.pop(handle)
            except KeyError:
                raise ComponentNotRegistered
            await managed_component.stop()

    def is_registered_component(self, handle: int) -> bool:
        return handle in self._components

    @asynccontextmanager
    async def acquire_component(self, handle: int) -> ComponentTypeVar:
        try:
            managed_component = self._components[handle]
        except KeyError:
            raise ComponentNotRegistered
        async with managed_component.acquire() as component:
            yield component
