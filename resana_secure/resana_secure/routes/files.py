import sys
import os
import trio
import subprocess
from quart import Blueprint
from base64 import b64decode
from typing import Optional

from parsec.api.data import EntryID, EntryName
from parsec.core.mountpoint import MountpointNotMounted
from parsec.core.fs import FsPath
from parsec.core.fs.exceptions import (
    FSNotADirectoryError,
    FSFileNotFoundError,
    FSPermissionError,
    FSIsADirectoryError,
)

from ..utils import APIException, authenticated, check_data, backend_errors_to_api_exceptions


files_bp = Blueprint("files_api", __name__)


# TODO: Parsec api should provide a way to do this
async def entry_id_to_path(workspace, needle_entry_id):
    async def _recursive_search(path):
        entry_info = await workspace.path_info(path=path)
        if entry_info["id"] == needle_entry_id:
            return path, entry_info
        if entry_info["type"] == "folder":
            for child_name in entry_info["children"]:
                result = await _recursive_search(path=path / child_name)
                if result:
                    return result
        return None

    return await _recursive_search(path=FsPath("/"))


### Folders ###


@files_bp.route("/workspaces/<string:workspace_id>/folders", methods=["GET"])
@authenticated
async def get_workspace_folders_tree(core, workspace_id):
    try:
        workspace_id = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id)

        async def _recursive_build_tree(path: str, name: Optional[EntryName]):
            entry_info = await workspace.path_info(path=path)
            if entry_info["type"] != "folder":
                return
            stat = {
                "id": entry_info["id"].hex,
                "name": name.str if name is not None else "/",
                "created": entry_info["created"].to_rfc3339(),
                "updated": entry_info["updated"].to_rfc3339(),
            }
            cooked_children = {}
            for child_name in entry_info["children"]:
                child_cooked_tree = await _recursive_build_tree(
                    path=f"{path}/{child_name}", name=child_name
                )
                if child_cooked_tree:
                    cooked_children[child_name.str] = child_cooked_tree
            stat["children"] = cooked_children
            return stat

        cooked_tree = await _recursive_build_tree(path="/", name=None)

    return cooked_tree, 200


@files_bp.route("/workspaces/<string:workspace_id>/folders", methods=["POST"])
@authenticated
async def create_workspace_folder(core, workspace_id):
    return await _create_workspace_entry(core, workspace_id, type="folder")


async def _create_workspace_entry(core, workspace_id, type):
    try:
        workspace_id = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    async with check_data() as (data, bad_fields):
        name = data.get("name")
        try:
            name = EntryName(name)
        except (TypeError, ValueError):
            bad_fields.add("name")
        parent_entry_id = data.get("parent")
        try:
            parent_entry_id = EntryID.from_hex(parent_entry_id)
        except (TypeError, ValueError):
            bad_fields.add("parent")
        if type == "file":
            content = data.get("content")
            try:
                content = b64decode(content)
            except (TypeError, ValueError):
                bad_fields.add("content")

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id)

        result = await entry_id_to_path(workspace, parent_entry_id)
        if not result:
            raise APIException(404, {"error": "unknown_parent"})
        parent_path, _ = result
        path = parent_path / name

        if type == "folder":
            entry_id = await workspace.transactions.folder_create(path)
        else:
            entry_id, fd = await workspace.transactions.file_create(path, open=True)
            try:
                await workspace.transactions.fd_write(fd, content=content, offset=0)

            finally:
                await workspace.transactions.fd_close(fd)

    return {"id": entry_id.hex}, 201


@files_bp.route("/workspaces/<string:workspace_id>/folders/rename", methods=["POST"])
@authenticated
async def rename_workspace_folder(core, workspace_id):
    return await _rename_workspace_entry(core, workspace_id, expected_entry_type="folder")


async def _rename_workspace_entry(core, workspace_id, expected_entry_type):
    try:
        workspace_id = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    async with check_data() as (data, bad_fields):
        entry_id = data.get("id")
        try:
            entry_id = EntryID.from_hex(entry_id)
        except (TypeError, ValueError):
            bad_fields.add("id")
        new_name = data.get("new_name")
        try:
            new_name = EntryName(new_name)
        except (TypeError, ValueError):
            bad_fields.add("new_name")
        new_parent_entry_id = data.get("new_parent")
        if new_parent_entry_id is not None:
            try:
                new_parent_entry_id = EntryID.from_hex(new_parent_entry_id)
            except (TypeError, ValueError):
                bad_fields.add("new_parent")

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id)

        result = await entry_id_to_path(workspace, entry_id)
        if not result:
            raise APIException(404, {"error": "unknown_source"})
        source_path, source_stat = result
        if source_stat["type"] != expected_entry_type:
            raise APIException(404, {"error": "unknown_source"})

        if new_parent_entry_id:
            result = await entry_id_to_path(workspace, new_parent_entry_id)
            if not result:
                raise APIException(404, {"error": "unknown_destination_parent"})
            destination_parent_path, _ = result
            destination_path = destination_parent_path / new_name
        else:
            destination_path = source_path.parent / new_name

        try:
            await workspace.move(source=source_path, destination=destination_path)

        except FSNotADirectoryError as exc:
            if exc.filename == destination_path:
                raise APIException(404, {"error": "destination_parent_not_a_folder"})
            else:
                raise APIException(404, {"error": "source_not_a_folder"})
        except FSFileNotFoundError as exc:
            if exc.filename == destination_path:
                raise APIException(404, {"error": "unknown_destination_parent"})
            else:
                raise APIException(404, {"error": "unknown_source"})
        except FSPermissionError:
            raise APIException(404, {"error": "cannot_move_root_folder"})

    return {}, 200


@files_bp.route("/workspaces/<string:workspace_id>/folders/<string:folder_id>", methods=["DELETE"])
@authenticated
async def delete_workspace_folder(core, workspace_id, folder_id):
    return await _delete_workspace_entry(
        core, workspace_id, folder_id, expected_entry_type="folder"
    )


async def _delete_workspace_entry(core, workspace_id, entry_id, expected_entry_type):
    try:
        workspace_id = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    try:
        entry_id = EntryID.from_hex(entry_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_entry"})

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id)

        result = await entry_id_to_path(workspace, entry_id)
        if not result:
            raise APIException(404, {"error": "unknown_entry"})
        path, _ = result

        try:
            if expected_entry_type == "folder":
                await workspace.rmdir(path=path)
            else:
                await workspace.unlink(path=path)

        except FSIsADirectoryError:
            raise APIException(404, {"error": "not_a_file"})
        except FSNotADirectoryError:
            raise APIException(404, {"error": "not_a_folder"})
        except FSFileNotFoundError:
            raise APIException(404, {"error": "unknown_entry"})
        except FSPermissionError:
            raise APIException(400, {"error": "cannot_delete_root_folder"})

    return {}, 204


### Files ###


@files_bp.route("/workspaces/<string:workspace_id>/files/<string:folder_id>", methods=["GET"])
@authenticated
async def get_workspace_folder_content(core, workspace_id, folder_id):
    try:
        workspace_id = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    try:
        folder_id = EntryID.from_hex(folder_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_folder"})

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id)

        async def _build_cooked_files():
            folder_path, folder_stat = await entry_id_to_path(workspace, folder_id)
            if folder_stat["type"] != "folder":
                raise APIException(404, {"error": "unknown_folder"})
            cooked_files = []
            for child_name in folder_stat["children"]:
                child_stat = await workspace.path_info(path=folder_path / child_name.str)
                if child_stat["type"] == "folder":
                    continue
                extension = child_name.str.rsplit(".", 1)[-1]
                extension = extension if extension != child_name.str else ""
                cooked_files.append(
                    {
                        "id": child_stat["id"].hex,
                        "name": child_name.str,
                        "created": child_stat["created"].to_rfc3339(),
                        "updated": child_stat["updated"].to_rfc3339(),
                        "size": child_stat["size"],
                        "extension": extension,
                    }
                )
            cooked_files.sort(key=lambda x: x["name"])
            return cooked_files

        cooked_files = await _build_cooked_files()

    return {"files": cooked_files}, 200


@files_bp.route("/workspaces/<string:workspace_id>/files", methods=["POST"])
@authenticated
async def create_workspace_file(core, workspace_id):
    return await _create_workspace_entry(core, workspace_id, type="file")


@files_bp.route("/workspaces/<string:workspace_id>/files/rename", methods=["POST"])
@authenticated
async def rename_workspace_file(core, workspace_id):
    return await _rename_workspace_entry(core, workspace_id, expected_entry_type="file")


@files_bp.route("/workspaces/<string:workspace_id>/files/<string:file_id>", methods=["DELETE"])
@authenticated
async def delete_workspace_file(core, workspace_id, file_id):
    return await _delete_workspace_entry(core, workspace_id, file_id, expected_entry_type="file")


@files_bp.route("/workspaces/<string:workspace_id>/open/<string:entry_id>", methods=["POST"])
@authenticated
async def open_workspace_item(core, workspace_id, entry_id):
    try:
        workspace_id = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    try:
        entry_id = EntryID.from_hex(entry_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_file"})

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id)

        result = await entry_id_to_path(workspace, entry_id)
        if not result:
            raise APIException(404, {"error": "unknown_file"})
        path, _ = result

        try:
            fspath = core.mountpoint_manager.get_path_in_mountpoint(workspace_id, path)
        except MountpointNotMounted:
            raise APIException(400, {"error": "workspace_not_mounted"})

    # Must run the open in a thread, otherwise we will block the current thread
    # that is suppossed to handle the actual open operation asked by the kernel !
    def _open_item():
        if sys.platform == "linux":
            subprocess.call(["xdg-open", fspath])
        elif sys.platform == "win32":
            os.startfile(fspath)

    await trio.to_thread.run_sync(_open_item)

    return {}, 200