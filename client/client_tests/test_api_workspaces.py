import pytest
import trio
from unittest.mock import ANY, Mock
from collections import namedtuple
from quart.typing import TestClientProtocol, TestAppProtocol

from .conftest import RemoteDeviceTestbed
from parsec._parsec import DateTime
from parsec.api.data import EntryID


WorkspaceInfo = namedtuple("WorkspaceInfo", "id,name")


@pytest.fixture
async def workspace(authenticated_client: TestClientProtocol):
    name = "wksp1"
    response = await authenticated_client.post("/workspaces", json={"name": name})
    assert response.status_code == 201
    body = await response.get_json()
    return WorkspaceInfo(body["id"], name)


@pytest.mark.trio
async def test_create_and_list_workspaces(authenticated_client: TestClientProtocol):
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
            {"id": bar_id, "name": "bar", "role": "OWNER"},
            {"id": foo_id, "name": "foo", "role": "OWNER"},
        ]
    }

    # Enforce the sync
    response = await authenticated_client.post("/workspaces/sync", json={})
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}


@pytest.mark.trio
async def test_rename_workspace(authenticated_client: TestClientProtocol, workspace: WorkspaceInfo):
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
async def test_rename_unknown_workspace(authenticated_client: TestClientProtocol):
    response = await authenticated_client.patch(
        "/workspaces/c3acdcb2ede6437f89fb94da11d733f2", json={"old_name": "foo", "new_name": "bar"}
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}


@pytest.mark.trio
async def test_get_share_info(authenticated_client: TestClientProtocol, workspace: WorkspaceInfo):
    response = await authenticated_client.get(f"/workspaces/{workspace.id}/share")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"roles": {"alice@example.com": "OWNER"}}


@pytest.mark.trio
async def test_get_share_info_unknown_workspace(authenticated_client: TestClientProtocol):
    response = await authenticated_client.get("/workspaces/c3acdcb2ede6437f89fb94da11d733f2/share")
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}


@pytest.mark.trio
async def test_share_unknown_email(
    authenticated_client: TestClientProtocol, workspace: WorkspaceInfo
):
    response = await authenticated_client.patch(
        f"/workspaces/{workspace.id}/share", json={"email": "dummy@example.com", "role": "OWNER"}
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_email"}


@pytest.mark.trio
async def test_share_invalid_role(
    authenticated_client: TestClientProtocol,
    other_device: RemoteDeviceTestbed,
    workspace: WorkspaceInfo,
):
    response = await authenticated_client.patch(
        f"/workspaces/{workspace.id}/share", json={"email": other_device.email, "role": "DUMMY"}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_data", "fields": ["role"]}


@pytest.mark.trio
async def test_share_unknown_workspace(
    authenticated_client: TestClientProtocol, other_user: RemoteDeviceTestbed
):
    response = await authenticated_client.patch(
        "/workspaces/c3acdcb2ede6437f89fb94da11d733f2/share",
        json={"email": other_user.email, "role": "OWNER"},
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}


@pytest.mark.trio
async def test_self_share_not_allowed(
    authenticated_client: TestClientProtocol, other_device: RemoteDeviceTestbed
):
    response = await authenticated_client.patch(
        "/workspaces/c3acdcb2ede6437f89fb94da11d733f2/share?foo=bar&touille=spam&foo=bar2",
        json={"email": other_device.email, "role": "OWNER"},
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "unexpected_error", "detail": "Cannot share to oneself"}


@pytest.mark.trio
async def test_share_ok(
    authenticated_client: TestClientProtocol,
    other_user: RemoteDeviceTestbed,
    workspace: WorkspaceInfo,
):
    response = await authenticated_client.patch(
        f"/workspaces/{workspace.id}/share", json={"email": other_user.email, "role": "MANAGER"}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Share info should have been updated
    response = await authenticated_client.get(f"/workspaces/{workspace.id}/share")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"roles": {"alice@example.com": "OWNER", "bob@example.com": "MANAGER"}}


@pytest.mark.trio
async def test_mount_unmount_workspace(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
):
    await trio.sleep(2)  # 2 seconds to ensure the default mountpoint is present

    # Unmount workspace mounted by default
    response = await authenticated_client.post(f"/workspaces/{workspace.id}/unmount")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Unmount not mounted workspace
    response = await authenticated_client.post(f"/workspaces/{workspace.id}/unmount")
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "mountpoint_not_mounted"}

    # Mount workspace
    response = await authenticated_client.post(f"/workspaces/{workspace.id}/mount")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"id": workspace.id}

    # Mount already mounted workspace
    response = await authenticated_client.post(f"/workspaces/{workspace.id}/mount")
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "mountpoint_already_mounted"}

    # Mount invalid workspace
    response = await authenticated_client.post("/workspaces/c3acdcb2ede6437f89fb94da11d733f2/mount")
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}

    # Unmount workspace
    response = await authenticated_client.post(f"/workspaces/{workspace.id}/unmount")
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}


@pytest.mark.trio
async def test_mount_unmount_workspace_timestamped(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
):
    await trio.sleep(2)  # 2 seconds to ensure the default mountpoint is present
    now = DateTime.now().to_rfc3339()

    # List mountpoints
    response = await authenticated_client.get("/workspaces/mountpoints")
    assert response.status_code == 200
    assert await response.get_json() == {
        "snapshots": [],
        "workspaces": [
            {"id": workspace.id, "name": workspace.name, "role": "OWNER"},
        ],
    }

    # Mount timestamped
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/mount", json={"timestamp": now}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {"id": workspace.id, "timestamp": now}

    # List mountpoints with timestamped
    response = await authenticated_client.get("/workspaces/mountpoints")
    assert response.status_code == 200
    assert await response.get_json() == {
        "snapshots": [
            {"id": workspace.id, "name": workspace.name, "role": "READER", "timestamp": now},
        ],
        "workspaces": [
            {"id": workspace.id, "name": workspace.name, "role": "OWNER"},
        ],
    }

    # Unmount timestamped
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/unmount", json={"timestamp": now}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Mount with invalid timestamp
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/mount", json={"timestamp": "2020-06-02T082810"}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_data", "fields": ["timestamp"]}


@pytest.mark.trio
async def test_offline_availability_not_authenticated(
    test_app: TestAppProtocol,
    workspace: WorkspaceInfo,
):
    claimer_client = test_app.test_client()
    response = await claimer_client.post(f"/workspaces/{workspace.id}/toggle_offline_availability")
    assert response.status_code == 401
    body = await response.get_json()
    assert body == {"error": "authentication_requested"}

    response = await claimer_client.get(
        f"/workspaces/{workspace.id}/get_offline_availability_status"
    )
    assert response.status_code == 401
    body = await response.get_json()
    assert body == {"error": "authentication_requested"}


@pytest.mark.trio
async def test_toggle_offline_availability(
    authenticated_client: TestClientProtocol, workspace: WorkspaceInfo
):
    # Missing argument
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/toggle_offline_availability"
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "json_body_expected"}

    # Invalid argument value
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": "test"}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "bad_data", "fields": ["enable"]}


@pytest.mark.trio
async def test_enable_offline_availability(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
    monkeypatch,
    remanence_monitor_event,
):
    remanence_monitor_event.set()

    # Non existing workspace
    fake_id = EntryID.new()
    response = await authenticated_client.post(
        f"/workspaces/{fake_id.hex}/toggle_offline_availability", json={"enable": True}
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}

    # Fake an error when enabling
    mock = Mock(side_effect=AttributeError)
    with monkeypatch.context() as m:
        m.setattr("parsec.core.fs.workspacefs.WorkspaceFS.enable_block_remanence", mock)
        response = await authenticated_client.post(
            f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": True}
        )
        body = await response.get_json()
        assert response.status_code == 400
        assert body == {"error": "failed_to_enable_offline_availability"}

    # Enable block remanence
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": True}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Try to enable it a second time
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": True}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "offline_availability_already_enabled"}


@pytest.mark.trio
async def test_disable_offline_availability(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
    monkeypatch,
    remanence_monitor_event,
):
    remanence_monitor_event.set()

    # Non existing workspace
    fake_id = EntryID.new()
    response = await authenticated_client.post(
        f"/workspaces/{fake_id.hex}/toggle_offline_availability", json={"enable": False}
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}

    # Try to disable when remanence is not enabled
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": False}
    )
    body = await response.get_json()
    assert response.status_code == 400
    assert body == {"error": "offline_availability_already_disabled"}

    # Enable block remanence and then disable it
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": True}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    # Fake an error when disabling
    mock = Mock(side_effect=AttributeError)
    with monkeypatch.context() as m:
        m.setattr("parsec.core.fs.workspacefs.WorkspaceFS.disable_block_remanence", mock)
        response = await authenticated_client.post(
            f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": False}
        )
        body = await response.get_json()
        assert response.status_code == 400
        assert body == {"error": "failed_to_disable_offline_availability"}

    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": False}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}


@pytest.mark.trio
async def test_get_offline_availability_status(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
    monkeypatch,
    remanence_monitor_event,
):
    remanence_monitor_event.set()

    # Non existing workspace
    fake_id = EntryID.new()
    response = await authenticated_client.get(
        f"/workspaces/{fake_id.hex}/get_offline_availability_status"
    )
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "unknown_workspace"}

    # Get info
    response = await authenticated_client.get(
        f"/workspaces/{workspace.id}/get_offline_availability_status"
    )
    body = await response.get_json()
    assert response.status_code == 200
    body == {
        "is_running": False,
        "is_prepared": False,
        "is_available_offline": False,
        "total_size": 0,
        "remote_only_size": 0,
        "local_and_remote_size": 0,
    }

    # Enable block remanence
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": True}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    response = await authenticated_client.get(
        f"/workspaces/{workspace.id}/get_offline_availability_status"
    )
    body = await response.get_json()
    assert response.status_code == 200
    body == {
        "is_running": False,
        "is_prepared": False,
        "is_available_offline": True,
        "total_size": 0,
        "remote_only_size": 0,
        "local_and_remote_size": 0,
    }

    # Disable it again
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/toggle_offline_availability", json={"enable": False}
    )
    body = await response.get_json()
    assert response.status_code == 200
    assert body == {}

    response = await authenticated_client.get(
        f"/workspaces/{workspace.id}/get_offline_availability_status"
    )
    body = await response.get_json()
    assert response.status_code == 200
    body == {
        "is_running": False,
        "is_prepared": False,
        "is_available_offline": False,
        "total_size": 0,
        "remote_only_size": 0,
        "local_and_remote_size": 0,
    }
