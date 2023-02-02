from __future__ import annotations

from typing import Any

from quart import Blueprint

from parsec.core.logged_core import LoggedCore
from parsec.core.fs.workspacefs import WorkspaceFS
from parsec.core.fs.exceptions import FSWorkspaceNotFoundError
from parsec.api.data import EntryID, EntryName
from parsec.api.protocol import RealmRole

from ..utils import (
    APIException,
    authenticated,
    requires_rie,
    get_data,
    check_if_timestamp,
    parse_arg,
    BadField,
    backend_errors_to_api_exceptions,
    get_workspace_type,
)

workspaces_bp = Blueprint("workspaces_api", __name__)


@workspaces_bp.route("/workspaces", methods=["GET"])
@authenticated
async def list_workspaces(core: LoggedCore) -> tuple[dict[str, Any], int]:
    # get_user_manifest() never raise exception
    user_manifest = core.user_fs.get_user_manifest()
    return (
        {
            "workspaces": sorted(
                [
                    {"id": entry.id.hex, "name": entry.name.str, "role": entry.role.str}
                    for entry in user_manifest.workspaces
                    if entry.role is not None
                ],
                key=lambda elem: elem["name"],
            )
        },
        200,
    )


@workspaces_bp.route("/workspaces", methods=["POST"])
@authenticated
async def create_workspaces(core: LoggedCore) -> tuple[dict[str, Any], int]:
    data = await get_data()
    name = parse_arg(data, "name", type=EntryName, convert=EntryName)
    if isinstance(name, BadField):
        raise APIException.from_bad_fields([name])

    with backend_errors_to_api_exceptions():
        workspace_id = await core.user_fs.workspace_create(name)

    # TODO: should we do a `user_fs.sync()` ?

    return {"id": workspace_id.hex}, 201


@workspaces_bp.route("/workspaces/sync", methods=["POST"])
@authenticated
async def sync_workspaces(core: LoggedCore) -> tuple[dict[str, Any], int]:
    # Core already do the sync in background, this route is to ensure
    # synchronization has occured
    user_fs = core.user_fs
    with backend_errors_to_api_exceptions():
        await user_fs.sync()
        for entry in user_fs.get_user_manifest().workspaces:
            workspace = user_fs.get_workspace(entry.id)
            await workspace.sync()

    return {}, 200


# TODO: provide an EntryID url converter
@workspaces_bp.route("/workspaces/<WorkspaceID:workspace_id>", methods=["PATCH"])
@authenticated
async def rename_workspaces(core: LoggedCore, workspace_id: EntryID) -> tuple[dict[str, Any], int]:
    data = await get_data()
    old_name = parse_arg(data, "old_name", type=EntryName, convert=EntryName)
    new_name = parse_arg(data, "new_name", type=EntryName, convert=EntryName)
    if isinstance(old_name, BadField) or isinstance(new_name, BadField):
        raise APIException.from_bad_fields([old_name, new_name])

    for entry in core.user_fs.get_user_manifest().workspaces:
        if entry.id == workspace_id:
            if entry.name != old_name:
                raise APIException(409, {"error": "precondition_failed"})
            else:
                break
    else:
        raise APIException(404, {"error": "unknown_workspace"})

    with backend_errors_to_api_exceptions():
        await core.user_fs.workspace_rename(workspace_id, new_name)

    # TODO: should we do a `user_fs.sync()` ?

    return {}, 200


@workspaces_bp.route("/workspaces/<WorkspaceID:workspace_id>/share", methods=["GET"])
@authenticated
async def get_workspace_share_info(
    core: LoggedCore, workspace_id: EntryID
) -> tuple[dict[str, Any], int]:
    timestamp = await check_if_timestamp()

    with backend_errors_to_api_exceptions():
        workspace = get_workspace_type(core, workspace_id, timestamp)

        cooked_roles = {}
        roles = await workspace.get_user_roles()
        for user_id, role in roles.items():
            user_info = await core.get_user_info(user_id)
            assert user_info.human_handle is not None
            cooked_roles[user_info.human_handle.email] = role.str

    return {"roles": cooked_roles}, 200


@workspaces_bp.route("/workspaces/<WorkspaceID:workspace_id>/share", methods=["PATCH"])
@authenticated
async def share_workspace(core: LoggedCore, workspace_id: EntryID) -> tuple[dict[str, Any], int]:
    data = await get_data()
    email = parse_arg(data, "email", type=str)
    role = parse_arg(data, "role", type=RealmRole, convert=RealmRole.from_str, missing=None)
    if isinstance(email, BadField) or isinstance(role, BadField):
        raise APIException.from_bad_fields([email, role])

    with backend_errors_to_api_exceptions():
        results, _ = await core.find_humans(query=email, per_page=1)
        try:
            # TODO: find_humans doesn't guarantee exact match on email
            assert results[0].human_handle is not None and results[0].human_handle.email == email
            recipient = results[0].user_id
        except IndexError:
            raise APIException(404, {"error": "unknown_email"})

        await core.user_fs.workspace_share(
            workspace_id=workspace_id, recipient=recipient, role=role
        )

    return {}, 200


@workspaces_bp.route("/workspaces/mountpoints", methods=["GET"])
@authenticated
async def list_mountpoints(core: LoggedCore) -> tuple[dict[str, Any], int]:
    user_manifest = core.user_fs.get_user_manifest()
    timestamped_mountpoints = await core.mountpoint_manager.get_timestamped_mounted()

    mountpoint_list = {
        "workspaces": sorted(
            [
                {"id": entry.id.hex, "name": entry.name.str, "role": entry.role.str}
                for entry in user_manifest.workspaces
                if entry.role is not None and core.mountpoint_manager.is_workspace_mounted(entry.id)
            ],
            key=lambda elem: elem["name"],
        ),
    }
    mountpoint_list["snapshots"] = sorted(
        [
            {
                "id": entry[0].hex,
                "name": timestamped_mountpoints[entry].get_workspace_entry().name.str,
                "role": "READER",
                "timestamp": entry[1].to_rfc3339(),
            }
            for entry in timestamped_mountpoints
            if entry[1] is not None
        ],
        key=lambda elem: elem["name"],
    )
    return mountpoint_list, 200


@workspaces_bp.route("/workspaces/<WorkspaceID:workspace_id>/mount", methods=["POST"])
@authenticated
@requires_rie
async def mount_workspace(core: LoggedCore, workspace_id: EntryID) -> tuple[dict[str, Any], int]:
    try:
        core.user_fs.get_workspace(workspace_id)
    except FSWorkspaceNotFoundError:
        raise APIException(404, {"error": "unknown_workspace"})

    timestamp = await check_if_timestamp()

    with backend_errors_to_api_exceptions():
        await core.mountpoint_manager.mount_workspace(workspace_id, timestamp)

    if timestamp:
        return {"id": workspace_id.hex, "timestamp": timestamp.to_rfc3339()}, 200
    return {"id": workspace_id.hex}, 200


@workspaces_bp.route("/workspaces/<WorkspaceID:workspace_id>/unmount", methods=["POST"])
@authenticated
@requires_rie
async def unmount_workspace(core: LoggedCore, workspace_id: EntryID) -> tuple[dict[str, Any], int]:
    timestamp = await check_if_timestamp()
    with backend_errors_to_api_exceptions():
        await core.mountpoint_manager.unmount_workspace(workspace_id, timestamp)

    return {}, 200


@workspaces_bp.route(
    "/workspaces/<WorkspaceID:workspace_id>/toggle_offline_availability", methods=["POST"]
)
@authenticated
@requires_rie
async def toggle_offline_availability(
    core: LoggedCore, workspace_id: EntryID
) -> tuple[dict[str, Any], int]:
    workspace_fs: WorkspaceFS | None = None
    try:
        workspace_fs = core.user_fs.get_workspace(workspace_id)
    except FSWorkspaceNotFoundError:
        raise APIException(404, {"error": "unknown_workspace"})

    data = await get_data()
    enable = parse_arg(data, "enable", type=bool)
    if isinstance(enable, BadField):
        raise APIException.from_bad_fields([enable])

    info = workspace_fs.get_remanence_manager_info()
    if enable and info.is_block_remanent:
        raise APIException(400, {"error": "offline_availability_already_enabled"})
    elif not enable and not info.is_block_remanent:
        raise APIException(400, {"error": "offline_availability_already_disabled"})
    try:
        if enable:
            await workspace_fs.enable_block_remanence()
        else:
            await workspace_fs.disable_block_remanence()
        return {}, 200
    except Exception:
        if enable:
            raise APIException(400, {"error": "failed_to_enable_offline_availability"})
        else:
            raise APIException(400, {"error": "failed_to_disable_offline_availability"})


@workspaces_bp.route(
    "/workspaces/<WorkspaceID:workspace_id>/get_offline_availability_status", methods=["GET"]
)
@authenticated
@requires_rie
async def get_offline_availability_status(
    core: LoggedCore, workspace_id: EntryID
) -> tuple[dict[str, Any], int]:
    workspace_fs: WorkspaceFS | None = None
    try:
        workspace_fs = core.user_fs.get_workspace(workspace_id)
    except FSWorkspaceNotFoundError:
        raise APIException(404, {"error": "unknown_workspace"})
    info = workspace_fs.get_remanence_manager_info()

    return {
        "is_running": info.is_running,
        "is_prepared": info.is_prepared,
        "is_available_offline": info.is_block_remanent,
        "total_size": info.total_size,
        "remote_only_size": info.remote_only_size,
        "local_and_remote_size": info.local_and_remote_size,
    }, 200
