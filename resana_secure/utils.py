import trio
from quart import jsonify, Response
from quart.exceptions import HTTPException
from contextlib import asynccontextmanager


class APIException(HTTPException):
    def __init__(self, status_code, data) -> None:
        super().__init__(status_code, "", "")
        self.data = data

    def get_response(self) -> Response:
        response = jsonify(self.data)
        response.status_code = self.status_code
        return response


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
