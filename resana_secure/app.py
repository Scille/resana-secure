import trio
import secrets
from functools import wraps
from uuid import uuid4
from base64 import b64decode, b64encode
from typing import Dict
from quart_trio import QuartTrio
from quart import current_app, session, request, Blueprint
from werkzeug.routing import BaseConverter
from contextlib import asynccontextmanager, contextmanager

from parsec.api.data import EntryID
from parsec.api.protocol import RealmRole
from parsec.core import logged_core_factory
from parsec.core.config import load_config
from parsec.core.local_device import (
    list_available_devices,
    load_device_with_password,
    LocalDeviceError,
)
from parsec.core.backend_connection import BackendConnectionError, BackendNotAvailable, BackendConnectionRefused
from parsec.core.fs.exceptions import FSError, FSWorkspaceNotFoundError, FSBackendOfflineError, FSSharingNotAllowedError

from .utils import APIException, ReadWriteLock


class CoreNotLoggedError(Exception):
    pass


class CoreUnknownEmailError(Exception):
    pass


class CoreAlreadyLoggedError(Exception):
    pass


class EntryIDConverter(BaseConverter):
    def to_python(self, value):
        return super().to_python(value)

    def to_url(self, value) -> str:
        return super().to_url(value)

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
                    password = b64encode(key).decode("ascii")  # TODO: use key (made of bytes) directly instead
                    device = load_device_with_password(available_device.key_file_path, password)
                    break

                except LocalDeviceError as exc:
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
            managed_core = await ManagedCore.start(nursery=self.nursery, config=self.core_config, email=email, key=key)
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


def authenticated(fn):
    @wraps(fn)
    async def wrapper(*args, **kwargs):
        # global auth_token
        print('AUTH !!!! ', list(current_app.cores_manager._cores.keys()))
        is_auth = session.get("logged_in", "")
        try:
            async with current_app.cores_manager.get_core(is_auth) as core:
                return await fn(*args, core=core, **kwargs)
        except CoreNotLoggedError:
            raise APIException(401, {"error": "authentication_requested"})
    return wrapper


api_bp = Blueprint("api", __name__)


@api_bp.route('/auth', methods=["POST"])
async def do_auth():
    data = await request.get_json()
    with check_data() as bad_fields:
        email = data.get("email")
        if not isinstance(email, str):
            bad_fields.add("email")
        key = data.get("key")
        try:
            key = b64decode(key)
        except (TypeError, ValueError):
            bad_fields.add("key")

    try:
        auth_token = await current_app.cores_manager.loggin(email=email, key=key)
    except CoreUnknownEmailError:
        raise APIException(404, {"error": "bad_auth"})
    except CoreAlreadyLoggedError:
        raise APIException(404, {"error": "already_authenticated"})
    print('LOGGIN !!!! ', list(current_app.cores_manager._cores.keys()))
    session["logged_in"] = auth_token
    return {}, 200


@contextmanager
def check_data():
    bad_fields = set()
    yield bad_fields
    if bad_fields:
        raise APIException(400, {"error": "bad_data", "fields": list(bad_fields)})


@api_bp.route('/workspaces', methods=["GET"])
@authenticated
async def list_workspaces(core):
    user_manifest = core.user_fs.get_user_manifest()
    return {
        "workspaces": [
            {
                "id": entry.id.hex,
                "name": entry.name,
                "role": entry.role.value,
            }
            for entry in user_manifest.workspaces
        ]
    }, 200


@api_bp.route('/workspaces', methods=["POST"])
@authenticated
async def create_workspaces(core):
    data = await request.get_json()
    with check_data() as bad_fields:
        name = data.get("name")
        if not isinstance(name, str):
            bad_fields.add("name")

    workspace_id = await core.user_fs.workspace_create(name)

    # TODO: should we do a `user_fs.sync()` ?

    return {
        "id": workspace_id.hex
    }, 201


@api_bp.route('/workspaces/sync', methods=["POST"])
@authenticated
async def sync_workspaces(core):
    # Core already do the sync in background, this route is to ensure
    # synchronization has occured
    user_fs = core.user_fs
    try:
        await user_fs.sync()
        for entry in user_fs.get_user_manifest().workspaces:
            workspace = user_fs.get_workspace(entry.id)
            await workspace.sync()

    except FSBackendOfflineError:
        raise APIException(503, {"error": "offline"})
    except FSError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    return {}, 200


# TODO: provide an EntryID url converter
@api_bp.route('/workspaces/<string:workspace_id>', methods=["PATCH"])
@authenticated
async def rename_workspaces(core, workspace_id):
    try:
        workspace_id = EntryID(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    data = await request.get_json()
    with check_data() as bad_fields:
        old_name = data.get("old_name")
        if not isinstance(old_name, str):
            bad_fields.add("old_name")
        new_name = data.get("new_name")
        if not isinstance(new_name, str):
            bad_fields.add("new_name")

    for entry in core.user_fs.get_user_manifest().workspaces:
        if entry.id == workspace_id:
            if entry.name != old_name:
                raise APIException(409, {"error": "precondition_failed"})
            else:
                break
    else:
        raise APIException(404, {"error": "unknown_workspace"})
    try:
        workspace_id = await core.user_fs.workspace_rename(workspace_id, new_name)
    except FSWorkspaceNotFoundError:
        raise APIException(404, {"error": "unknown_workspace"})

    # TODO: should we do a `user_fs.sync()` ?

    return {}, 200


@api_bp.route('/workspaces/<string:workspace_id>/share', methods=["GET"])
@authenticated
async def get_workspace_share_info(core, workspace_id):
    try:
        workspace_id = EntryID(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    try:
        workspace = core.user_fs.get_workspace(workspace_id)
    except FSWorkspaceNotFoundError:
        raise APIException(404, {"error": "unknown_workspace"})

    cooked_roles = {}
    try:
        roles = await workspace.get_user_roles()
        for user_id, role in roles.items():
            user_info = await core.get_user_info(user_id)
            assert user_info.human_handle is not None
            cooked_roles[user_info.human_handle.email] = role.value

    except (BackendNotAvailable, FSBackendOfflineError):
        raise APIException(404, {"error": "unknown_workspace"})
    except (FSError, BackendConnectionError) as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    return {"roles": cooked_roles}, 200


@api_bp.route('/workspaces/<string:workspace_id>/share', methods=["PATCH"])
@authenticated
async def share_workspace(core, workspace_id):
    try:
        workspace_id = EntryID(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    data = await request.get_json()
    with check_data() as bad_fields:
        email = data.get("email")
        if not isinstance(email, str):
            bad_fields.add("email")
        role = data.get("role")
        if role is not None:
            for choice in RealmRole:
                if choice.value == role:
                    role = choice
            else:
                bad_fields.add("role")

    try:
        results, _ = await core.find_humans(query=email, per_page=1)
        try:
            # TODO: find_humans doesn't guarantee exact match on email
            assert results[0].human_handle is not None and results[0].human_handle.email == email
            recipient = results[0].user_id
        except IndexError:
            raise APIException(404, {"error": "unknown_email"})

    except BackendNotAvailable:
        raise APIException(503, {"error": "offline"})
    except BackendConnectionRefused:
        raise APIException(401, {"error": "connection_refused_by_server"})
    except BackendConnectionError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    try:
        await core.user_fs.workspace_share(workspace_id=workspace_id, recipient=recipient, role=role)
    except FSWorkspaceNotFoundError:
        raise APIException(404, {"error": "unknown_workspace"})
    except FSSharingNotAllowedError:
        raise APIException(403, {"error": "sharing_not_allowed"})
    except FSBackendOfflineError:
        raise APIException(503, {"error": "offline"})
    except FSError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    return {}, 200


@asynccontextmanager
async def app_factory():
    app = QuartTrio(__name__)
    app.register_blueprint(api_bp)

    app.config.from_mapping(
        # Secret key changes each time the application is started, this is
        # fine as long as we only use it for session cookies.
        # The reason for doing this is we serve the api on localhost, so
        # storing the secret on the hard drive in a no go.
        SECRET_KEY=secrets.token_hex(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="strict",

        CORE_CONFIG_DIR=None,  # TODO: Needed
    )
    async with CoresManager.run() as app.cores_manager:
        yield app


async def main(port="8080", debug=True):
    async with app_factory() as app:
        await app.run_task(host="127.0.0.1", port=port, debug=debug)


if __name__ == "__main__":
    trio.run(main)
