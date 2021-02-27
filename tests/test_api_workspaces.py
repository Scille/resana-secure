import pytest
from unittest.mock import ANY


@pytest.mark.trio
async def test_create_and_list_workspaces(authenticated_client):
    # No workspaces
    response = await authenticated_client.get("/workspaces")
    assert response.status_code == 200
    assert await response.get_json() == {"workspaces": []}

    # Create some workspaces
    response = await authenticated_client.post("/workspaces", json={"name": "foo"})
    assert response.status_code == 201
    body = await response.get_json()
    assert body == {"id": ANY}
    foo_id = body["id"]
    response = await authenticated_client.post("/workspaces", json={"name": "bar"})
    assert response.status_code == 201
    body = await response.get_json()
    assert body == {"id": ANY}
    bar_id = body["id"]

    # Get the updated workspaces list
    response = await authenticated_client.get("/workspaces")
    assert response.status_code == 200
    assert await response.get_json() == {
        "workspaces": [
            {"id": foo_id, "name": "foo", "role": "OWNER"},
            {"id": bar_id, "name": "bar", "role": "OWNER"},
        ]
    }

    # Enforce the sync
    response = await authenticated_client.post("/workspaces/sync", json={})
    assert response.status_code == 200
    assert await response.get_json() == {}


@pytest.mark.trio
async def test_rename_workspace(authenticated_client):
    response = await authenticated_client.post("/workspaces", json={"name": "foo"})
    assert response.status_code == 201
    foo_id = (await response.get_json())["id"]

    # Actually do the rename
    for i in range(2):
        response = await authenticated_client.patch(
            f"/workspaces/{foo_id}", json={"old_name": "foo", "new_name": "bar"}
        )
        if i == 0:
            assert response.status_code == 200
            assert await response.get_json() == {}
        else:
            # Renaming while having an out of date old_name should do nothing
            assert response.status_code == 409
            assert await response.get_json() == {"error": "precondition_failed"}

        response = await authenticated_client.get("/workspaces")
        assert response.status_code == 200
        assert await response.get_json() == {
            "workspaces": [
                {"id": foo_id, "name": "bar", "role": "OWNER"},
            ]
        }


@pytest.mark.trio
async def test_share_workspace(authenticated_client):
    response = await authenticated_client.post("/workspaces", json={"name": "foo"})
    assert response.status_code == 201
    foo_id = (await response.get_json())["id"]

    # Get sharing info
    response = await authenticated_client.get(f"/workspaces/{foo_id}/share")
    assert response.status_code == 200
    assert await response.get_json() == {"roles": {"alice@example.com": "OWNER"}}
