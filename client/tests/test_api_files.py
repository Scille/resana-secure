import pytest
from unittest.mock import ANY
from quart.typing import TestClientProtocol


class FilesTestBed:
    def __init__(self, authenticated_client: TestClientProtocol, wid: str, root_entry_id: str):
        self.authenticated_client = authenticated_client
        self.wid = wid
        self.root_entry_id = root_entry_id

    async def create_file(self, name, parent, content="", wid=None, expected_status_code=201):
        wid = wid if wid is not None else self.wid
        response = await self.authenticated_client.post(
            f"/workspaces/{wid}/files", json={"name": name, "parent": parent, "content": content}
        )
        body = await response.get_json()
        assert response.status_code == expected_status_code
        if expected_status_code == 201:
            return body["id"]
        else:
            return body

    async def create_folder(self, name, parent, wid=None, expected_status_code=201):
        wid = wid if wid is not None else self.wid
        response = await self.authenticated_client.post(
            f"/workspaces/{wid}/folders", json={"name": name, "parent": parent}
        )
        body = await response.get_json()
        assert response.status_code == expected_status_code
        if expected_status_code == 201:
            return body["id"]
        else:
            return body

    async def rename_folder(self, id, new_name, new_parent, wid=None, expected_status_code=200):
        wid = wid if wid is not None else self.wid
        response = await self.authenticated_client.post(
            f"/workspaces/{wid}/folders/rename",
            json={"id": id, "new_name": new_name, "new_parent": new_parent},
        )
        body = await response.get_json()
        assert response.status_code == expected_status_code
        if expected_status_code == 200:
            assert body == {}
        return body

    async def rename_file(self, id, new_name, new_parent, wid=None, expected_status_code=200):
        wid = wid if wid is not None else self.wid
        response = await self.authenticated_client.post(
            f"/workspaces/{wid}/files/rename",
            json={"id": id, "new_name": new_name, "new_parent": new_parent},
        )
        body = await response.get_json()
        assert response.status_code == expected_status_code
        if expected_status_code == 200:
            assert body == {}
        return body

    async def delete_folder(self, id, wid=None, expected_status_code=204):
        wid = wid if wid is not None else self.wid
        response = await self.authenticated_client.delete(f"/workspaces/{wid}/folders/{id}")
        body = await response.get_json()
        assert response.status_code == expected_status_code
        if expected_status_code == 200:
            assert body == {}
        return body

    async def delete_file(self, id, wid=None, expected_status_code=204):
        wid = wid if wid is not None else self.wid
        response = await self.authenticated_client.delete(f"/workspaces/{wid}/files/{id}")
        body = await response.get_json()
        assert response.status_code == expected_status_code
        if expected_status_code == 200:
            assert body == {}
        return body

    async def get_folders_tree(self, wid=None, expected_status_code=200):
        wid = wid if wid is not None else self.wid
        response = await self.authenticated_client.get(f"/workspaces/{wid}/folders")
        body = await response.get_json()
        assert response.status_code == expected_status_code
        return body

    async def get_files(self, folder_id, wid=None, expected_status_code=200):
        wid = wid if wid is not None else self.wid
        response = await self.authenticated_client.get(f"/workspaces/{wid}/files/{folder_id}")
        body = await response.get_json()
        assert response.status_code == expected_status_code
        return body

    async def open(self, entry_id, wid=None, expected_status_code=200):
        wid = wid if wid is not None else self.wid
        response = await self.authenticated_client.post(f"/workspaces/{wid}/open/{entry_id}")
        body = await response.get_json()
        assert response.status_code == expected_status_code
        if expected_status_code == 200:
            assert body == {}
        return body


@pytest.fixture()
async def testbed(authenticated_client: TestClientProtocol):
    # Create workspace
    response = await authenticated_client.post("/workspaces", json={"name": "foo"})
    assert response.status_code == 201
    wid = (await response.get_json())["id"]

    # retrieve root folder entry id
    response = await authenticated_client.get(f"/workspaces/{wid}/folders")
    body = await response.get_json()
    assert response.status_code == 200
    root_entry_id = body["id"]

    return FilesTestBed(authenticated_client, wid, root_entry_id)


@pytest.mark.trio
async def test_get_folders_tree_ignore_files(testbed: FilesTestBed):
    # Populate with folder&files
    foo_entry_id = await testbed.create_folder("foo", parent=testbed.root_entry_id)
    bar_entry_id = await testbed.create_folder("bar", parent=foo_entry_id)
    await testbed.create_file("spam.txt", parent=foo_entry_id)

    # Only folders should be visible
    assert await testbed.get_folders_tree() == {
        "id": testbed.root_entry_id,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "children": {
            "foo": {
                "id": foo_entry_id,
                "name": "foo",
                "created": ANY,
                "updated": ANY,
                "children": {
                    "bar": {
                        "id": bar_entry_id,
                        "name": "bar",
                        "created": ANY,
                        "updated": ANY,
                        "children": {},
                    }
                },
            }
        },
    }


@pytest.mark.trio
async def test_folder_operations(testbed: FilesTestBed):
    # Folder should be empty at first
    assert await testbed.get_folders_tree() == {
        "id": testbed.root_entry_id,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "children": {},
    }
    assert isinstance(testbed.root_entry_id, str)

    # Create a folder
    subfolder_entry_id = await testbed.create_folder("foo", parent=testbed.root_entry_id)
    assert isinstance(subfolder_entry_id, str)

    # Check root and subfolder content
    assert await testbed.get_folders_tree() == {
        "id": testbed.root_entry_id,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "children": {
            "foo": {
                "id": subfolder_entry_id,
                "name": "foo",
                "created": ANY,
                "updated": ANY,
                "children": {},
            }
        },
    }

    # Rename the subfolder
    await testbed.rename_folder(subfolder_entry_id, new_name="bar", new_parent=None)

    # Check root and subfolder content
    assert await testbed.get_folders_tree() == {
        "id": testbed.root_entry_id,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "children": {
            "bar": {
                "id": subfolder_entry_id,
                "name": "bar",
                "created": ANY,
                "updated": ANY,
                "children": {},
            }
        },
    }

    # Delete the subfolder
    await testbed.delete_folder(subfolder_entry_id)

    # Check root and subfolder content
    assert await testbed.get_folders_tree() == {
        "id": testbed.root_entry_id,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "children": {},
    }


@pytest.mark.trio
async def test_file_operations(testbed: FilesTestBed):
    # Create a files
    foo_id = await testbed.create_file("foo.tar.gz", parent=testbed.root_entry_id)
    assert isinstance(foo_id, str)
    bar_id = await testbed.create_file("bar.txt", parent=testbed.root_entry_id)

    subfolder_id = await testbed.create_folder("spam", parent=testbed.root_entry_id)
    await testbed.create_file("foo", parent=subfolder_id)

    # Check files in a given folder
    assert await testbed.get_files(folder_id=testbed.root_entry_id) == {
        "files": [
            {
                "created": ANY,
                "extension": "txt",
                "id": bar_id,
                "name": "bar.txt",
                "size": 0,
                "updated": ANY,
            },
            {
                "created": ANY,
                "extension": "gz",
                "id": foo_id,
                "name": "foo.tar.gz",
                "size": 0,
                "updated": ANY,
            },
        ]
    }

    # Rename a file
    await testbed.rename_file(bar_id, new_name="bar.md", new_parent=None)
    assert await testbed.get_files(folder_id=testbed.root_entry_id) == {
        "files": [
            {
                "created": ANY,
                "extension": "md",
                "id": bar_id,
                "name": "bar.md",
                "size": 0,
                "updated": ANY,
            },
            {
                "created": ANY,
                "extension": "gz",
                "id": foo_id,
                "name": "foo.tar.gz",
                "size": 0,
                "updated": ANY,
            },
        ]
    }

    # Delete a file
    await testbed.delete_file(bar_id)
    assert await testbed.get_files(folder_id=testbed.root_entry_id) == {
        "files": [
            {
                "created": ANY,
                "extension": "gz",
                "id": foo_id,
                "name": "foo.tar.gz",
                "size": 0,
                "updated": ANY,
            }
        ]
    }


@pytest.mark.trio
@pytest.mark.parametrize("bad_wid", ["c0f0b18ee7634d01bd7ae9533d1222ef", "<not_an_uuid>"])
async def test_bad_workspace(testbed: FilesTestBed, bad_wid: str):
    other_id = "c3acdcb2ede6437f89fb94da11d733f2"
    expected_body = {"error": "unknown_workspace"}

    assert await testbed.get_folders_tree(wid=bad_wid, expected_status_code=404) == expected_body
    assert await testbed.get_files(other_id, wid=bad_wid, expected_status_code=404) == expected_body
    assert (
        await testbed.create_folder("foo", parent=other_id, wid=bad_wid, expected_status_code=404)
        == expected_body
    )
    assert (
        await testbed.create_file("foo", parent=other_id, wid=bad_wid, expected_status_code=404)
        == expected_body
    )
    assert (
        await testbed.rename_folder(
            other_id, new_name="bar", new_parent=None, wid=bad_wid, expected_status_code=404
        )
        == expected_body
    )
    assert (
        await testbed.rename_file(
            other_id, new_name="bar", new_parent=None, wid=bad_wid, expected_status_code=404
        )
        == expected_body
    )
    assert (
        await testbed.delete_folder(other_id, wid=bad_wid, expected_status_code=404)
        == expected_body
    )
    assert (
        await testbed.delete_file(other_id, wid=bad_wid, expected_status_code=404) == expected_body
    )
    assert await testbed.open(other_id, wid=bad_wid, expected_status_code=404) == expected_body


@pytest.mark.trio
async def test_create_folder_already_exists(testbed: FilesTestBed):
    await testbed.create_folder("foo", parent=testbed.root_entry_id)

    expected_body = {"error": "unexpected_error", "detail": "File exists: /foo"}
    assert (
        await testbed.create_folder("foo", parent=testbed.root_entry_id, expected_status_code=400)
        == expected_body
    )
