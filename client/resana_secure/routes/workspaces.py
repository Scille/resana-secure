from __future__ import annotations

import re
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
    Parser,
    backend_errors_to_api_exceptions,
    get_workspace_type,
    get_user_id_from_email,
    email_validator,
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
    parser = Parser()
    parser.add_argument("name", converter=EntryName, required=True)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    with backend_errors_to_api_exceptions():
        workspace_id = await core.user_fs.workspace_create(args["name"])

    personal_workspace_name_pattern = core.config.personal_workspace_name_pattern
    personal_workspace_name_regex = (
        re.compile(personal_workspace_name_pattern) if personal_workspace_name_pattern else None
    )

    if personal_workspace_name_regex and personal_workspace_name_regex.fullmatch(str(args["name"])):
        workspace_fs = core.user_fs.get_workspace(workspace_id)
        await workspace_fs.enable_block_remanence()

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
    parser = Parser()
    parser.add_argument("old_name", converter=EntryName, required=True)
    parser.add_argument("new_name", converter=EntryName, required=True)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    for entry in core.user_fs.get_user_manifest().workspaces:
        if entry.id == workspace_id:
            if entry.name != args["old_name"]:
                raise APIException(409, {"error": "precondition_failed"})
            break
    else:
        raise APIException(404, {"error": "unknown_workspace"})

    with backend_errors_to_api_exceptions():
        await core.user_fs.workspace_rename(workspace_id, args["new_name"])

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
    parser = Parser()
    parser.add_argument("email", type=str, required=True, validator=email_validator)
    parser.add_argument("role", converter=RealmRole.from_str)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    with backend_errors_to_api_exceptions():
        user_id = await get_user_id_from_email(core, args["email"])
        if user_id is None:
            raise APIException(404, {"error": "unknown_email"})

        await core.user_fs.workspace_share(
            workspace_id=workspace_id, recipient=user_id, role=args["role"]
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
    parser = Parser()
    parser.add_argument("enable", type=bool, required=True)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    info = workspace_fs.get_remanence_manager_info()
    if args["enable"] and info.is_block_remanent:
        raise APIException(400, {"error": "offline_availability_already_enabled"})
    if not args["enable"] and not info.is_block_remanent:
        raise APIException(400, {"error": "offline_availability_already_disabled"})
    try:
        if args["enable"]:
            await workspace_fs.enable_block_remanence()
        else:
            await workspace_fs.disable_block_remanence()
        return {}, 200
    except Exception:
        if args["enable"]:
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
