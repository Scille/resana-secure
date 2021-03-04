from quart import Blueprint

from parsec.api.data import EntryID
from parsec.api.protocol import RealmRole
from parsec.core.backend_connection import (
    BackendConnectionError,
    BackendNotAvailable,
    BackendConnectionRefused,
)
from parsec.core.fs.exceptions import (
    FSError,
    FSWorkspaceNotFoundError,
    FSBackendOfflineError,
    FSSharingNotAllowedError,
)

from ..utils import APIException, authenticated, check_data


workspaces_bp = Blueprint("workspaces_api", __name__)


@workspaces_bp.route("/workspaces", methods=["GET"])
@authenticated
async def list_workspaces(core):
    user_manifest = core.user_fs.get_user_manifest()
    return (
        {
            "workspaces": [
                {"id": entry.id.hex, "name": entry.name, "role": entry.role.value}
                for entry in user_manifest.workspaces
            ]
        },
        200,
    )


@workspaces_bp.route("/workspaces", methods=["POST"])
@authenticated
async def create_workspaces(core):
    async with check_data() as (data, bad_fields):
        name = data.get("name")
        if not isinstance(name, str):
            bad_fields.add("name")

    workspace_id = await core.user_fs.workspace_create(name)

    # TODO: should we do a `user_fs.sync()` ?

    return {"id": workspace_id.hex}, 201


@workspaces_bp.route("/workspaces/sync", methods=["POST"])
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
@workspaces_bp.route("/workspaces/<string:workspace_id>", methods=["PATCH"])
@authenticated
async def rename_workspaces(core, workspace_id):
    try:
        workspace_id = EntryID(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    async with check_data() as (data, bad_fields):
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


@workspaces_bp.route("/workspaces/<string:workspace_id>/share", methods=["GET"])
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


@workspaces_bp.route("/workspaces/<string:workspace_id>/share", methods=["PATCH"])
@authenticated
async def share_workspace(core, workspace_id):
    try:
        workspace_id = EntryID(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    async with check_data() as (data, bad_fields):
        email = data.get("email")
        if not isinstance(email, str):
            bad_fields.add("email")
        role = data.get("role")
        if role is not None:
            for choice in RealmRole:
                if choice.value == role:
                    role = choice
                    break
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
        raise APIException(502, {"error": "connection_refused_by_server"})
    except BackendConnectionError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    try:
        await core.user_fs.workspace_share(
            workspace_id=workspace_id, recipient=recipient, role=role
        )
    except FSWorkspaceNotFoundError:
        raise APIException(404, {"error": "unknown_workspace"})
    except FSSharingNotAllowedError:
        raise APIException(403, {"error": "sharing_not_allowed"})
    except FSBackendOfflineError:
        raise APIException(503, {"error": "offline"})
    except FSError as exc:
        raise APIException(400, {"error": "unexpected_error", "detail": str(exc)})

    return {}, 200
