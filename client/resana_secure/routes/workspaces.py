from __future__ import annotations

import re
from typing import Any

from quart import Blueprint

from parsec._parsec import DateTime, RealmArchivingConfiguration
from parsec.api.data import EntryID, EntryName
from parsec.api.protocol import RealmRole
from parsec.core.logged_core import LoggedCore

from ..utils import (
    APIException,
    Parser,
    authenticated,
    backend_errors_to_api_exceptions,
    check_if_timestamp,
    check_workspace_available,
    email_validator,
    get_data,
    get_user_id_from_email,
    requires_rie,
)

workspaces_bp = Blueprint("workspaces_api", __name__)


@workspaces_bp.route("/workspaces", methods=["GET"])
@authenticated
async def list_workspaces(core: LoggedCore) -> tuple[dict[str, Any], int]:
    workspace_items = []
    for entry in core.user_fs.get_available_workspace_entries():
        assert entry.role is not None
        workspace = core.user_fs.get_workspace(entry.id)
        archiving_configuration, _, _ = workspace.get_archiving_configuration()
        workspace_item = {
            "id": entry.id.hex,
            "name": entry.name.str,
            "role": entry.role.str,
            "archiving_configuration": archiving_configuration.str,
        }
        workspace_items.append(workspace_item)
    workspace_items.sort(key=lambda elem: elem["name"])
    return (
        {"workspaces": workspace_items},
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

    workspace = check_workspace_available(core, workspace_id)
    if workspace.get_workspace_name() != args["old_name"]:
        raise APIException(409, {"error": "precondition_failed"})

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
        workspace = check_workspace_available(core, workspace_id, timestamp)

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
        user_id = await get_user_id_from_email(core, args["email"], omit_revoked=True)
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
    timestamp = await check_if_timestamp()

    check_workspace_available(core, workspace_id, timestamp)

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
    data = await get_data()
    parser = Parser()
    parser.add_argument("enable", type=bool, required=True)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    workspace = check_workspace_available(core, workspace_id)
    info = workspace.get_remanence_manager_info()
    if args["enable"] and info.is_block_remanent:
        raise APIException(400, {"error": "offline_availability_already_enabled"})
    if not args["enable"] and not info.is_block_remanent:
        raise APIException(400, {"error": "offline_availability_already_disabled"})
    try:
        if args["enable"]:
            await workspace.enable_block_remanence()
        else:
            await workspace.disable_block_remanence()
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
    workspace = check_workspace_available(core, workspace_id)
    info = workspace.get_remanence_manager_info()

    return {
        "is_running": info.is_running,
        "is_prepared": info.is_prepared,
        "is_available_offline": info.is_block_remanent,
        "total_size": info.total_size,
        "remote_only_size": info.remote_only_size,
        "local_and_remote_size": info.local_and_remote_size,
    }, 200


@workspaces_bp.route("/workspaces/<WorkspaceID:workspace_id>/archiving", methods=["GET"])
@authenticated
async def get_archiving_configuration(
    core: LoggedCore, workspace_id: EntryID
) -> tuple[dict[str, Any], int]:
    workspace = check_workspace_available(core, workspace_id)
    configuration, configured_on, configured_by = workspace.get_archiving_configuration()
    configured_on_str = None if configured_on is None else configured_on.to_rfc3339()
    deletion_date_str = (
        configuration.deletion_date.to_rfc3339() if configuration.is_deletion_planned() else None
    )
    organization_config = core.get_organization_config()

    configured_by_email = None
    if configured_by is not None:
        user_info = await core.get_user_info(configured_by.user_id)
        if user_info.human_handle is not None:
            configured_by_email = user_info.human_handle.email

    return {
        "configuration": configuration.str,
        "configured_on": configured_on_str,
        "configured_by": configured_by_email,
        "deletion_date": deletion_date_str,
        "minimum_archiving_period": organization_config.minimum_archiving_period,
    }, 200


@workspaces_bp.route("/workspaces/<WorkspaceID:workspace_id>/archiving", methods=["POST"])
@authenticated
async def set_archiving_configuration(
    core: LoggedCore, workspace_id: EntryID
) -> tuple[dict[str, Any], int]:
    def archiving_configuration_validator(value: str) -> None:
        try:
            RealmArchivingConfiguration.from_str(value, None)
        except ValueError:
            RealmArchivingConfiguration.from_str(value, DateTime.now())

    data = await get_data()
    parser = Parser()
    parser.add_argument(
        "configuration", type=str, validator=archiving_configuration_validator, required=True
    )
    parser.add_argument("deletion_date", converter=DateTime.from_rfc3339, required=False)
    args, bad_fields = parser.parse_args(data)
    if bad_fields:
        raise APIException.from_bad_fields(bad_fields)

    # The `configuration` and `deletion_date` fields have been validated independently
    # They also have to be validated together
    configuration: str = args["configuration"]
    deletion_date: DateTime | None = args["deletion_date"]
    try:
        archiving_configuration = RealmArchivingConfiguration.from_str(
            configuration,
            deletion_date,
        )
    except ValueError:
        raise APIException.from_bad_fields(["configuration", "deletion_date"])

    # Adapt the deletion date if necessary.
    # This is useful when a user tries to remove a workspace instantely (if allowed).
    # In that case, there's a good chance the planned date for deletion falls slightly
    # before `now`. In this case, it's ok to shift it and make it equal to `now`.
    # However we don't want this shift if the deletion date is way off, since it
    # means a user mistake is likely involved. A 5 minutes window seems like a
    # suitable trade-off.
    # Another solution would be to adapt the API for instant deletion but it's
    # probably not going to be used since a minimum archiving period is typically
    # configured. At the moment, this is mainly useful when testing.
    now = core.device.time_provider.now()
    if (
        archiving_configuration.is_deletion_planned()
        and deletion_date is not None
        and now.subtract(minutes=5) < deletion_date < now
    ):
        archiving_configuration = RealmArchivingConfiguration.deletion_planned(now)

    workspace = check_workspace_available(core, workspace_id)
    with backend_errors_to_api_exceptions():
        await workspace.configure_archiving(archiving_configuration, now=now)

    return {}, 200
