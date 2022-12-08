from __future__ import annotations

import sys
import os
import trio
import subprocess
from pathlib import PurePath
from quart import Blueprint, request
from base64 import b64decode

from PyQt5.QtWidgets import QApplication
from typing import Optional, Sequence, cast, TypedDict, Any, List

from parsec._parsec import DateTime
from parsec.core.logged_core import LoggedCore
from parsec.api.data import EntryID, EntryName
from parsec.core.mountpoint import MountpointNotMounted
from parsec.core.fs import FsPath, WorkspaceFS
from parsec.core.fs.exceptions import (
    FSNotADirectoryError,
    FSFileNotFoundError,
    FSPermissionError,
    FSIsADirectoryError,
)

from ..utils import APIException, authenticated, check_data, backend_errors_to_api_exceptions

from resana_secure.gui import ResanaGuiApp

files_bp = Blueprint("files_api", __name__)


class EntryInfo(TypedDict):
    id: EntryID
    type: str
    children: Sequence[EntryName]
    created: DateTime
    updated: DateTime
    size: int


def get_file_extension(filename: EntryName) -> str:
    extension = filename.str.rsplit(".", 1)[-1]
    return (extension if extension != filename.str else "").lower()


# TODO: Parsec api should provide a way to do this
async def entry_id_to_path(
    workspace: WorkspaceFS, needle_entry_id: EntryID
) -> tuple[FsPath, EntryInfo] | None:
    async def _recursive_search(path: FsPath) -> tuple[FsPath, EntryInfo] | None:
        entry_info = cast(EntryInfo, await workspace.path_info(path=path))
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
async def get_workspace_folders_tree(
    core: LoggedCore, workspace_id: str
) -> tuple[dict[str, Any], int]:
    try:
        workspace_id_parsed = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id_parsed)

        async def _recursive_build_tree(
            path: str, name: Optional[EntryName]
        ) -> dict[str, Any] | None:
            entry_info = cast(EntryInfo, await workspace.path_info(path=path))
            if entry_info["type"] != "folder":
                return None
            stat: dict[str, Any] = {
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

    assert cooked_tree is not None
    return cooked_tree, 200


@files_bp.route("/workspaces/<string:workspace_id>/folders", methods=["POST"])
@authenticated
async def create_workspace_folder(
    core: LoggedCore, workspace_id: str
) -> tuple[dict[str, Any], int]:
    try:
        workspace_id_parsed = EntryID.from_hex(workspace_id)
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

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id_parsed)

        result = await entry_id_to_path(workspace, parent_entry_id)
        if not result:
            raise APIException(404, {"error": "unknown_parent"})
        parent_path, _ = result
        path = parent_path / name

        entry_id = await workspace.transactions.folder_create(path)

    return {"id": entry_id.hex}, 201


@files_bp.route("/workspaces/<string:workspace_id>/folders/rename", methods=["POST"])
@authenticated
async def rename_workspace_folder(
    core: LoggedCore, workspace_id: str
) -> tuple[dict[str, Any], int]:
    return await _rename_workspace_entry(core, workspace_id, expected_entry_type="folder")


async def _rename_workspace_entry(
    core: LoggedCore, workspace_id: str, expected_entry_type: str
) -> tuple[dict[str, Any], int]:
    try:
        workspace_id_parsed = EntryID.from_hex(workspace_id)
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
        workspace = core.user_fs.get_workspace(workspace_id_parsed)

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
async def delete_workspace_folder(
    core: LoggedCore, workspace_id: str, folder_id: str
) -> tuple[dict[str, Any], int]:
    return await _delete_workspace_entry(
        core, workspace_id, folder_id, expected_entry_type="folder"
    )


async def _delete_workspace_entry(
    core: LoggedCore, workspace_id: str, entry_id: str, expected_entry_type: str
) -> tuple[dict[str, Any], int]:
    try:
        workspace_id_parsed = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    try:
        entry_id_parsed = EntryID.from_hex(entry_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_entry"})

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id_parsed)

        result = await entry_id_to_path(workspace, entry_id_parsed)
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
async def get_workspace_folder_content(
    core: LoggedCore, workspace_id: str, folder_id: str
) -> tuple[dict[str, Any], int]:
    try:
        workspace_id_parsed = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    try:
        folder_id_parsed = EntryID.from_hex(folder_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_folder"})

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id_parsed)

        async def _build_cooked_files() -> list[dict[str, int | str]]:
            result = await entry_id_to_path(workspace, folder_id_parsed)
            assert result is not None
            folder_path, folder_stat = result
            if folder_stat["type"] != "folder":
                raise APIException(404, {"error": "unknown_folder"})
            cooked_files: list[dict[str, int | str]] = []
            for child_name in folder_stat["children"]:
                child_stat = cast(
                    EntryInfo, await workspace.path_info(path=folder_path / child_name.str)
                )
                if child_stat["type"] == "folder":
                    continue
                cooked_files.append(
                    {
                        "id": child_stat["id"].hex,
                        "name": child_name.str,
                        "created": child_stat["created"].to_rfc3339(),
                        "updated": child_stat["updated"].to_rfc3339(),
                        "size": child_stat["size"],
                        "extension": get_file_extension(child_name),
                    }
                )
            cooked_files.sort(key=lambda x: x["name"])
            return cooked_files

        cooked_files = await _build_cooked_files()

    return {"files": cooked_files}, 200


@files_bp.route("/workspaces/<string:workspace_id>/files", methods=["POST"])
@authenticated
async def create_workspace_file(core: LoggedCore, workspace_id: str) -> tuple[dict[str, Any], int]:
    try:
        workspace_id_parsed = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    # First we consider the file has been sent as multipart
    if request.content_type.startswith("multipart/form-data"):
        form = await request.form
        files = await request.files
        file = files.get("file")
        if not file:
            raise APIException(400, {"error": "bad_data", "fields": ["file"]})

        bad_fields = []

        name = file.filename
        try:
            name = EntryName(name)
        except (TypeError, ValueError):
            bad_fields.append("name")

        form = await request.form
        parent_entry_id_raw = cast(str, form.get("parent", ""))
        try:
            parent_entry_id = EntryID.from_hex(parent_entry_id_raw)
        except (TypeError, ValueError):
            bad_fields.append("parent")

        content = file.stream

        if bad_fields:
            raise APIException(400, {"error": "bad_data", "fields": bad_fields})

    else:
        # Otherwise consider is has been sent as json
        async with check_data() as (data, bad_fields_set):
            name = data.get("name")
            try:
                name = EntryName(name)
            except (TypeError, ValueError):
                bad_fields_set.add("name")
            parent_entry_id_raw = data.get("parent")
            try:
                parent_entry_id = EntryID.from_hex(parent_entry_id_raw)
            except (TypeError, ValueError):
                bad_fields_set.add("parent")

            content = data.get("content")
            try:
                content = b64decode(content)
            except (TypeError, ValueError):
                bad_fields_set.add("content")

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id_parsed)

        result = await entry_id_to_path(workspace, parent_entry_id)
        if not result:
            raise APIException(404, {"error": "unknown_parent"})
        parent_path, _ = result
        path = parent_path / name

        entry_id, fd = await workspace.transactions.file_create(path, open=True)
        assert fd is not None
        try:
            if isinstance(content, bytes):
                await workspace.transactions.fd_write(fd, content=content, offset=0)

            else:
                buffsize = 512 * 1024
                offset = 0
                while True:
                    buff = content.read(buffsize)
                    if not buff:
                        break
                    await workspace.transactions.fd_write(fd, content=buff, offset=offset)
                    offset += len(buff)

        finally:
            await workspace.transactions.fd_close(fd)

    return {"id": entry_id.hex}, 201


@files_bp.route("/workspaces/<string:workspace_id>/files/rename", methods=["POST"])
@authenticated
async def rename_workspace_file(core: LoggedCore, workspace_id: str) -> tuple[dict[str, Any], int]:
    return await _rename_workspace_entry(core, workspace_id, expected_entry_type="file")


@files_bp.route("/workspaces/<string:workspace_id>/files/<string:file_id>", methods=["DELETE"])
@authenticated
async def delete_workspace_file(
    core: LoggedCore, workspace_id: str, file_id: str
) -> tuple[dict[str, Any], int]:
    return await _delete_workspace_entry(core, workspace_id, file_id, expected_entry_type="file")


@files_bp.route("/workspaces/<string:workspace_id>/open/<string:entry_id>", methods=["POST"])
@authenticated
async def open_workspace_item(
    core: LoggedCore, workspace_id: str, entry_id: str
) -> tuple[dict[str, Any], int]:
    try:
        workspace_id_parsed = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})

    try:
        entry_id_parsed = EntryID.from_hex(entry_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_file"})

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id_parsed)

        result = await entry_id_to_path(workspace, entry_id_parsed)
        if not result:
            raise APIException(404, {"error": "unknown_file"})
        path, _ = result

        try:
            fspath = core.mountpoint_manager.get_path_in_mountpoint(workspace_id_parsed, path)
            await trio.to_thread.run_sync(_open_item, fspath)
        except MountpointNotMounted:
            # Not mounted, use the GUI to download the file
            qt_app = cast(ResanaGuiApp, QApplication.instance())
            if qt_app:
                # Signals must be emitted using a thread to not block dialogs' exec_ method.
                await trio.to_thread.run_sync(qt_app.save_file_requested.emit, workspace, path)

    return {}, 200


def _open_item(fspath: PurePath) -> None:
    if sys.platform == "linux":
        subprocess.call(["xdg-open", fspath])
    elif sys.platform == "win32":
        os.startfile(fspath)


@files_bp.route("/workspaces/<string:workspace_id>/search", methods=["POST"])
@authenticated
async def search_workspace_item(
    core: LoggedCore,
    workspace_id: str,
) -> tuple[dict[str, Any], int]:

    try:
        workspace_id_parsed = EntryID.from_hex(workspace_id)
    except ValueError:
        raise APIException(404, {"error": "unknown_workspace"})
    async with check_data() as (data, bad_fields_set):
        case_sensitive = data.get("case_sensitive", False)
        if not isinstance(case_sensitive, bool):
            bad_fields_set.add("case_sensitive")
        exclude_folders = data.get("exclude_folders", False)
        if not isinstance(exclude_folders, bool):
            bad_fields_set.add("exclude_folders")
        search_string = data.get("string")
        if not isinstance(search_string, str):
            bad_fields_set.add("string")

    with backend_errors_to_api_exceptions():
        workspace = core.user_fs.get_workspace(workspace_id_parsed)

        def _matches(file_name: EntryName) -> bool:
            return (case_sensitive and search_string in file_name.str) or (
                not case_sensitive and search_string.lower() in file_name.str.lower()
            )

        async def _recursive_search(path: FsPath) -> List[dict[str, Any]]:
            entry_info = cast(EntryInfo, await workspace.path_info(path=path))
            files = []

            if (
                path != FsPath("/")
                and (not exclude_folders or exclude_folders and entry_info["type"] != "folder")
                and _matches(path.name)
            ):

                files.append(
                    {
                        "id": entry_info["id"].hex,
                        "name": path.name.str,
                        "path": str(path.parent),
                        "type": entry_info["type"],
                        "created": entry_info["created"].to_rfc3339(),
                        "updated": entry_info["updated"].to_rfc3339(),
                        "size": entry_info["size"] if entry_info["type"] != "folder" else 0,
                        "extension": get_file_extension(path.name),
                    }
                )

            if entry_info["type"] == "folder":
                for child in entry_info["children"]:
                    files.extend(await _recursive_search(path / child))
            return files

    files = await _recursive_search(FsPath("/"))

    return {"files": files}, 200
