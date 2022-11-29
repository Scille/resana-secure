from __future__ import annotations

from typing import Any

from quart import Blueprint

from parsec.core.logged_core import LoggedCore
from parsec.core.fs.exceptions import FSWorkspaceNotFoundError
from parsec.api.data import EntryID, EntryName
from parsec.api.protocol import RealmRole

from ..utils import (
    APIException,
    authenticated,
    requires_rie,
    check_data,
    check_if_timestamp,
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
    async with check_data() as (data, bad_fields):
        name_raw = data.get("name")
        if not isinstance(name_raw, str):
            bad_fields.add("name")
        try:
            name = EntryName(name_raw)
        except ValueError:
            bad_fields.add("name")

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
    async with check_data() as (data, bad_fields):
        old_name_raw = data.get("old_name")
        if not isinstance(old_name_raw, str):
            bad_fields.add("old_name")
        try:
            old_name = EntryName(old_name_raw)
        except ValueError:
            bad_fields.add("old_name")
        new_name_raw = data.get("new_name")
        if not isinstance(new_name_raw, str):
            bad_fields.add("new_name")
        try:
            new_name = EntryName(new_name_raw)
        except ValueError:
            bad_fields.add("new_name")

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
    async with check_data() as (data, bad_fields):
        email = data.get("email")
        if not isinstance(email, str):
            bad_fields.add("email")
        role = data.get("role")
        if role is not None:
            for choice in RealmRole.values():
                if choice.str == role:
                    role = choice
                    break
            else:
                bad_fields.add("role")

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
