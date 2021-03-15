import trio
from typing import Callable, Dict, TypeVar, Optional, AsyncIterator
from contextlib import asynccontextmanager


class ReadCancelledByWriter(Exception):
    pass


class ReadWriteLock:
    """
    Reader/writer lock with priority on writers.
    """

    def __init__(self) -> None:
        self._lock = trio.Lock()
        self._no_writers = trio.Event()
        self._no_writers.set()
        self._no_readers = trio.Event()
        self._no_readers.set()
        self._readers_cancel_scopes: Dict[int, trio.CancelScope] = {}

    @asynccontextmanager
    async def read_acquire(self) -> AsyncIterator[None]:
        """
        Raises: ReadCancelledByWriter
        """
        while True:
            async with self._lock:
                if self._no_writers.is_set():
                    # Stores the cancel scopes allows us to count the number
                    # of readers and to cancel them all when a writer arrives
                    cancel_scope = trio.CancelScope()
                    self._readers_cancel_scopes[id(cancel_scope)] = cancel_scope
                    if len(self._readers_cancel_scopes) == 1:
                        self._no_readers = trio.Event()
                    break
            await self._no_writers.wait()
        try:
            with cancel_scope:
                yield
        finally:
            with trio.CancelScope(shield=True):
                async with self._lock:
                    del self._readers_cancel_scopes[id(cancel_scope)]
                    if not self._readers_cancel_scopes:
                        self._no_readers.set()
                    if cancel_scope.cancelled_caught:
                        raise ReadCancelledByWriter

    @asynccontextmanager
    async def write_acquire(self) -> AsyncIterator[None]:
        """
        Raises: Nothing
        """
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
        # To avoid deadlock if a reader is blocked forever, we cancel all readers
        # instead of letting them finish what they are doing
        for cancel_scope in self._readers_cancel_scopes.values():
            cancel_scope.cancel()
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
        """
        Raises: Nothing
        """
        with trio.CancelScope() as cancel_scope:
            component_stopped = trio.Event()

            async def _stop_component():
                cancel_scope.cancel()
                await component_stopped.wait()

            managed_component = None

            async with component_factory() as component:
                try:
                    managed_component = cls(component=component, stop_component=_stop_component)
                    task_status.started(managed_component)
                    await trio.sleep_forever()

                finally:
                    # Do this before entering the component's __aexit__ to ensure
                    # the component cannot be acquired while it is tearing down
                    if managed_component is not None:
                        managed_component._component = None
                    component_stopped.set()

    async def stop(self):
        """
        Raises: Nothing
        """
        async with self._rwlock.write_acquire():
            # _stop_component_callback is idempotent so no need to check
            # if the component is actually still running
            await self._stop_component_callback()

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[ComponentTypeVar]:
        """
        Raises: ComponentNotRegistered
        """
        try:
            async with self._rwlock.read_acquire():
                if self._component is None:
                    raise ComponentNotRegistered
                yield self._component

        except ReadCancelledByWriter as exc:
            raise ComponentNotRegistered from exc


class LTCM:
    """
    Long Time Component Management.
    Allow to run arbitrary long-lived code with a greater lifetime
    than the code that initiated it.
    This is useful when exposing a stateless API where LTCM will hold the state
    on the behalf of the API consumer.
    """

    def __init__(self, nursery):
        self._nursery = nursery
        self._lock = trio.Lock()
        self._components: Dict[int, ManagedComponent] = {}

    @classmethod
    @asynccontextmanager
    async def run(cls) -> AsyncIterator["LTCM"]:
        """
        Raises: Nothing
        """
        async with trio.open_nursery() as nursery:
            yield cls(nursery)
            nursery.cancel_scope.cancel()

    async def register_component(self, component_factory: Callable) -> int:
        """
        Raises: Nothing
        """
        async with self._lock:
            managed_component = await self._nursery.start(ManagedComponent.run, component_factory)
            handle = id(managed_component)
            self._components[handle] = managed_component
            return handle

    async def unregister_component(self, handle: int) -> None:
        """
        Raises: ComponentNotRegistered
        """
        async with self._lock:
            try:
                managed_component = self._components.pop(handle)
            except KeyError:
                raise ComponentNotRegistered
            await managed_component.stop()

    def is_registered_component(self, handle: int) -> bool:
        return handle in self._components

    @asynccontextmanager
    async def acquire_component(self, handle: int) -> AsyncIterator[ComponentTypeVar]:
        """
        Raises: ComponentNotRegistered
        """
        try:
            managed_component = self._components[handle]
        except KeyError:
            raise ComponentNotRegistered
        async with managed_component.acquire() as component:
            yield component
