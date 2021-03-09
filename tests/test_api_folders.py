import pytest
from unittest.mock import ANY


class TestBed:
    def __init__(self, authenticated_client, wid, root_entry_id):
        self.authenticated_client = authenticated_client
        self.wid = wid
        self.root_entry_id = root_entry_id

    async def create_file(self, name, parent, content=""):
        response = await self.authenticated_client.post(
            f"/workspaces/{self.wid}/files",
            json={"name": name, "parent": parent, "content": content},
        )
        body = await response.get_json()
        assert response.status_code == 201
        return body["id"]

    async def create_folder(self, name, parent):
        response = await self.authenticated_client.post(
            f"/workspaces/{self.wid}/folders", json={"name": name, "parent": parent}
        )
        body = await response.get_json()
        assert response.status_code == 201
        return body["id"]

    async def rename(self, id, new_name, new_parent):
        response = await self.authenticated_client.post(
            f"/workspaces/{self.wid}/folders/rename",
            json={"id": id, "new_name": new_name, "new_parent": new_parent},
        )
        assert await response.get_json() == {}
        assert response.status_code == 200

    async def delete(self, id):
        response = await self.authenticated_client.delete(f"/workspaces/{self.wid}/folders/{id}")
        assert await response.get_json() == {}
        assert response.status_code == 204

    async def get_folder_tree(self):
        response = await self.authenticated_client.get(f"/workspaces/{self.wid}/folders")
        body = await response.get_json()
        assert response.status_code == 200
        return body


@pytest.fixture()
async def testbed(authenticated_client):
    # Create workspace
    response = await authenticated_client.post("/workspaces", json={"name": "foo"})
    assert response.status_code == 201
    wid = (await response.get_json())["id"]

    # retrieve root folder entry id
    response = await authenticated_client.get(f"/workspaces/{wid}/folders")
    body = await response.get_json()
    assert response.status_code == 200
    root_entry_id = body["id"]

    return TestBed(authenticated_client, wid, root_entry_id)


@pytest.mark.trio
async def test_get_folders_tree_ignore_files(testbed, authenticated_client):
    # Populate with folder&files
    foo_entry_id = await testbed.create_folder("foo", parent=testbed.root_entry_id)
    bar_entry_id = await testbed.create_folder("bar", parent=foo_entry_id)
    await testbed.create_file("spam.txt", parent=foo_entry_id)

    # Only folders should be visible
    assert await testbed.get_folder_tree() == {
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
async def test_folder_operations(authenticated_client, testbed):
    # Folder should be empty at first
    assert await testbed.get_folder_tree() == {
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
    assert await testbed.get_folder_tree() == {
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
    await testbed.rename(subfolder_entry_id, new_name="bar", new_parent=None)

    # Check root and subfolder content
    assert await testbed.get_folder_tree() == {
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
    await testbed.delete(subfolder_entry_id)

    # Check root and subfolder content
    assert await testbed.get_folder_tree() == {
        "id": testbed.root_entry_id,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "children": {},
    }
