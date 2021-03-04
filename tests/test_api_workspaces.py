import pytest
from unittest.mock import ANY
from collections import namedtuple


WorkspaceInfo = namedtuple("WorkspaceInfo", "id,name")


@pytest.fixture
async def workspace(authenticated_client):
    name = "wksp1"
    response = await authenticated_client.post("/workspaces", json={"name": name})
    assert response.status_code == 201
    body = await response.get_json()
    return WorkspaceInfo(body["id"], name)


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
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}


@pytest.mark.trio
async def test_rename_workspace(authenticated_client, workspace):
    for i in range(2):
        response = await authenticated_client.patch(
            f"/workspaces/{workspace.id}", json={"old_name": workspace.name, "new_name": "bar"}
        )
        if i == 0:
            body = await response.get_json()
            assert response.status_code == 200
            assert body == {}
        else:
            # Renaming while having an out of date old_name should do nothing
            body = await response.get_json()
            assert response.status_code == 409
            assert body == {"error": "precondition_failed"}

        response = await authenticated_client.get("/workspaces")
        body = await response.get_json()
        assert response.status_code == 200
        assert body == {"workspaces": [{"id": workspace.id, "name": "bar", "role": "OWNER"}]}


@pytest.mark.trio
async def test_rename_unknown_workspace(authenticated_client):
    response = await authenticated_client.patch(
        "/workspaces/c3acdcb2ede6437f89fb94da11d733f2", json={"old_name": "foo", "new_name": "bar"}
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}


@pytest.mark.trio
async def test_get_share_info(authenticated_client, workspace):
    response = await authenticated_client.get(f"/workspaces/{workspace.id}/share")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"roles": {"alice@example.com": "OWNER"}}


@pytest.mark.trio
async def test_get_share_info_unknown_workspace(authenticated_client):
    response = await authenticated_client.get("/workspaces/c3acdcb2ede6437f89fb94da11d733f2/share")
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}


@pytest.mark.trio
async def test_share_unknown_email(authenticated_client, workspace):
    response = await authenticated_client.patch(
        f"/workspaces/{workspace.id}/share", json={"email": "dummy@example.com", "role": "OWNER"}
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_email"}


@pytest.mark.trio
async def test_share_invalid_role(authenticated_client, local_device, workspace):
    response = await authenticated_client.patch(
        f"/workspaces/{workspace.id}/share", json={"email": local_device.email, "role": "DUMMY"}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_data", "fields": ["role"]}


@pytest.mark.trio
@pytest.mark.xfail(reason="TODO: other_device not available")
async def test_share_unknown_workspace(authenticated_client, other_device):
    response = await authenticated_client.patch(
        "/workspaces/c3acdcb2ede6437f89fb94da11d733f2/share",
        json={"email": other_device.email, "role": "OWNER"},
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}
    assert response.status_code == 400
    assert body == {"detail": "Cannot share to oneself", "error": "unexpected_error"}


@pytest.mark.trio
async def test_self_share_not_allowed(authenticated_client, local_device):
    response = await authenticated_client.patch(
        "/workspaces/c3acdcb2ede6437f89fb94da11d733f2/share?foo=bar&touille=spam&foo=bar2",
        json={"email": local_device.email, "role": "OWNER"},
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "unexpected_error", "detail": "Cannot share to oneself"}
