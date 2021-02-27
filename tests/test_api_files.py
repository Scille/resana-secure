import pytest
from unittest.mock import ANY


@pytest.fixture
async def workspace_id(authenticated_client):
    response = await authenticated_client.post("/workspaces", json={"name": "foo"})
    assert response.status_code == 201
    return (await response.get_json())["id"]


@pytest.mark.trio
async def test_folder_operations(authenticated_client):
    # Create a new workspace
    response = await authenticated_client.post("/workspaces", json={"name": "foo"})
    assert response.status_code == 201
    wid = (await response.get_json())["id"]

    response = await authenticated_client.get(f"/workspaces/{wid}/folders")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "id": ANY,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "type": "folder",
        "children": {},
    }
    root_entry_id = body["id"]
    assert isinstance(root_entry_id, str)

    # Create a folder
    response = await authenticated_client.post(
        f"/workspaces/{wid}/folders", json={"name": "foo", "parent": root_entry_id}
    )
    body = await response.get_json()
    assert response.status_code == 201
    assert body == {}

    # Check root and subfolder content
    response = await authenticated_client.get(f"/workspaces/{wid}/folders")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "id": root_entry_id,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "type": "folder",
        "children": {
            "foo": {
                "id": ANY,
                "name": "foo",
                "created": ANY,
                "updated": ANY,
                "type": "folder",
                "children": {},
            }
        },
    }
    subfolder_entry_id = body["children"]["foo"]["id"]
    assert isinstance(subfolder_entry_id, str)

    # Rename the subfolder
    response = await authenticated_client.post(
        f"/workspaces/{wid}/folders/rename",
        json={"id": subfolder_entry_id, "new_name": "bar", "new_parent": None},
    )
    assert await response.get_json() == {}
    assert response.status_code == 200

    # Check root and subfolder content
    response = await authenticated_client.get(f"/workspaces/{wid}/folders")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "id": root_entry_id,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "type": "folder",
        "children": {
            "bar": {
                "id": subfolder_entry_id,
                "name": "bar",
                "created": ANY,
                "updated": ANY,
                "type": "folder",
                "children": {},
            }
        },
    }

    # Delete the subfolder
    response = await authenticated_client.delete(
        f"/workspaces/{wid}/folders/{subfolder_entry_id}"
    )
    assert await response.get_json() == {}
    assert response.status_code == 204

    # Check root and subfolder content
    response = await authenticated_client.get(f"/workspaces/{wid}/folders")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {
        "id": root_entry_id,
        "name": "/",
        "created": ANY,
        "updated": ANY,
        "type": "folder",
        "children": {},
    }
