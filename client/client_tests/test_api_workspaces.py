from collections import namedtuple
from typing import Awaitable, Callable
from unittest.mock import ANY, Mock

import pytest
import trio
from quart.typing import TestAppProtocol, TestClientProtocol

from parsec._parsec import DateTime
from parsec.api.data import EntryID

from .conftest import LocalDeviceTestbed, RemoteDeviceTestbed

WorkspaceInfo = namedtuple("WorkspaceInfo", "id,name")


async def wait_for(condition: Callable[[], Awaitable[None]], timeout=5.0):
    with trio.fail_after(timeout):
        while True:
            try:
                await condition()
            except AssertionError:
                pass
            else:
                return
            await trio.sleep(0)


@pytest.fixture
async def workspace_mounted(authenticated_client: TestClientProtocol, workspace: WorkspaceInfo):
    async def condition():
        response = await authenticated_client.get("/workspaces/mountpoints")
        body = await response.get_json()
        assert response.status_code == 200, body
        assert len(body["workspaces"]) == 1

    await wait_for(condition)


@pytest.fixture
async def remanence_monitor_prepared(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
    remanence_monitor_event: trio.Event,
):
    remanence_monitor_event.set()

    async def condition():
        response = await authenticated_client.get(
            f"/workspaces/{workspace.id}/get_offline_availability_status"
        )
        body = await response.get_json()
        assert response.status_code == 200, body
        assert body["is_running"]
        assert body["is_prepared"]

    await wait_for(condition)


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
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {"workspaces": []}

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
    assert response.status_code == 200, body
    assert await response.get_json() == {
        "workspaces": [
            {"id": bar_id, "name": "bar", "role": "OWNER", "archiving_configuration": "AVAILABLE"},
            {"id": foo_id, "name": "foo", "role": "OWNER", "archiving_configuration": "AVAILABLE"},
        ]
    }

    # Enforce the sync
    response = await authenticated_client.post("/workspaces/sync", json={})
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}


@pytest.mark.trio
async def test_create_with_block_remanence_workspaces(authenticated_client: TestClientProtocol):
    # No workspaces
    response = await authenticated_client.get("/workspaces")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {"workspaces": []}

    # Create workspace
    response = await authenticated_client.post("/workspaces", json={"name": "Block_Reman"})
    body = await response.get_json()
    assert response.status_code == 201, body
    assert body == {"id": ANY}
    foo_id = body["id"]

    # Get block_remanence status
    response = await authenticated_client.get(
        f"/workspaces/{foo_id}/get_offline_availability_status"
    )
    assert response.status_code == 200, body
    body = await response.get_json()
    assert body == {
        "is_available_offline": True,
        "is_prepared": ANY,
        "is_running": ANY,
        "total_size": 0,
        "remote_only_size": 0,
        "local_and_remote_size": 0,
    }

    # Get the updated workspaces list
    response = await authenticated_client.get("/workspaces")
    assert response.status_code == 200, body
    assert await response.get_json() == {
        "workspaces": [
            {
                "id": foo_id,
                "name": "Block_Reman",
                "role": "OWNER",
                "archiving_configuration": "AVAILABLE",
            },
        ]
    }

    # Enforce the sync
    response = await authenticated_client.post("/workspaces/sync", json={})
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}


@pytest.mark.trio
async def test_rename_workspace(authenticated_client: TestClientProtocol, workspace: WorkspaceInfo):
    for i in range(2):
        response = await authenticated_client.patch(
            f"/workspaces/{workspace.id}", json={"old_name": workspace.name, "new_name": "bar"}
        )
        if i == 0:
            body = await response.get_json()
            assert response.status_code == 200, body
            assert body == {}
        else:
            # Renaming while having an out of date old_name should do nothing
            body = await response.get_json()
            assert response.status_code == 409
            assert body == {"error": "precondition_failed"}

        response = await authenticated_client.get("/workspaces")
        body = await response.get_json()
        assert response.status_code == 200, body
        assert body == {
            "workspaces": [
                {
                    "id": workspace.id,
                    "name": "bar",
                    "role": "OWNER",
                    "archiving_configuration": "AVAILABLE",
                }
            ]
        }


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
    assert response.status_code == 200, body
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
    assert body == {"error": "unexpected_error", "detail": "FSError('Cannot share to oneself')"}


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
    assert response.status_code == 200, body
    assert body == {}

    # Share info should have been updated
    response = await authenticated_client.get(f"/workspaces/{workspace.id}/share")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {"roles": {"alice@example.com": "OWNER", "bob@example.com": "MANAGER"}}


@pytest.mark.trio
async def test_mount_unmount_workspace(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
    workspace_mounted: None,
):
    # Unmount workspace mounted by default
    response = await authenticated_client.post(f"/workspaces/{workspace.id}/unmount")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}

    # Unmount not mounted workspace
    response = await authenticated_client.post(f"/workspaces/{workspace.id}/unmount")
    body = await response.get_json()
    assert response.status_code == 404
    assert body == {"error": "mountpoint_not_mounted"}

    # Mount workspace
    response = await authenticated_client.post(f"/workspaces/{workspace.id}/mount")
    body = await response.get_json()
    assert response.status_code == 200, body
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
    assert response.status_code == 200, body
    assert body == {}


@pytest.mark.trio
async def test_mount_unmount_workspace_timestamped(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
    workspace_mounted: None,
):
    now = DateTime.now().to_rfc3339()

    # List mountpoints
    response = await authenticated_client.get("/workspaces/mountpoints")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "snapshots": [],
        "workspaces": [
            {"id": workspace.id, "name": workspace.name, "role": "OWNER"},
        ],
    }

    # Force sync before accessing timestamped workspace
    # Otherwise we might get an `FSRemoteManifestNotFound`
    response = await authenticated_client.post("/workspaces/sync", json={})
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}

    # Mount timestamped
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/mount", json={"timestamp": now}
    )
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {"id": workspace.id, "timestamp": now}

    # List mountpoints with timestamped
    response = await authenticated_client.get("/workspaces/mountpoints")
    assert response.status_code == 200, body
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
    assert response.status_code == 200, body
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
    remanence_monitor_prepared,
):
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
    assert response.status_code == 200, body
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
    remanence_monitor_prepared,
):

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
    assert response.status_code == 200, body
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
    assert response.status_code == 200, body
    assert body == {}


@pytest.mark.trio
async def test_get_offline_availability_status(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
    remanence_monitor_prepared,
):
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
    assert response.status_code == 200, body
    assert body == {
        "is_running": True,
        "is_prepared": True,
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
    assert response.status_code == 200, body
    assert body == {}

    response = await authenticated_client.get(
        f"/workspaces/{workspace.id}/get_offline_availability_status"
    )
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "is_running": True,
        "is_prepared": True,
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
    assert response.status_code == 200, body
    assert body == {}

    response = await authenticated_client.get(
        f"/workspaces/{workspace.id}/get_offline_availability_status"
    )
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "is_running": True,
        "is_prepared": True,
        "is_available_offline": False,
        "total_size": 0,
        "remote_only_size": 0,
        "local_and_remote_size": 0,
    }


@pytest.mark.trio
async def test_workspace_archiving(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
):
    # Default archiving configuration
    response = await authenticated_client.get(f"/workspaces/{workspace.id}/archiving")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "configuration": "AVAILABLE",
        "configured_by": None,
        "configured_on": None,
        "deletion_date": None,
        "minimum_archiving_period": 2592000,
    }

    # Archive the workpace
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving", json={"configuration": "ARCHIVED"}
    )
    body = await response.get_json()
    assert response.status_code == 200, body

    # Check the archiving status
    response = await authenticated_client.get(f"/workspaces/{workspace.id}/archiving")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "configuration": "ARCHIVED",
        "configured_by": "alice@example.com",
        "configured_on": ANY,
        "deletion_date": None,
        "minimum_archiving_period": 2592000,
    }
    DateTime.from_rfc3339(body["configured_on"])

    # Check the workspace list
    response = await authenticated_client.get("/workspaces")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "workspaces": [
            {"id": ANY, "name": "wksp1", "role": "OWNER", "archiving_configuration": "ARCHIVED"}
        ]
    }

    # Unarchive the workspace
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving",
        json={"configuration": "AVAILABLE", "deletion_date": None},
    )
    body = await response.get_json()
    assert response.status_code == 200, body

    # Check the archiving status
    response = await authenticated_client.get(f"/workspaces/{workspace.id}/archiving")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "configuration": "AVAILABLE",
        "configured_by": "alice@example.com",
        "configured_on": ANY,
        "deletion_date": None,
        "minimum_archiving_period": 2592000,
    }
    DateTime.from_rfc3339(body["configured_on"])

    # Check the workspace list
    response = await authenticated_client.get("/workspaces")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "workspaces": [
            {"id": ANY, "name": "wksp1", "role": "OWNER", "archiving_configuration": "AVAILABLE"}
        ]
    }

    # Plan a deletion for the workspace
    deletion_date = DateTime.now().add(days=31).to_rfc3339()
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving",
        json={"configuration": "DELETION_PLANNED", "deletion_date": deletion_date},
    )
    body = await response.get_json()
    assert response.status_code == 200, body

    # Check the archiving status
    response = await authenticated_client.get(f"/workspaces/{workspace.id}/archiving")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "configuration": "DELETION_PLANNED",
        "configured_by": "alice@example.com",
        "configured_on": ANY,
        "deletion_date": deletion_date,
        "minimum_archiving_period": 2592000,
    }
    DateTime.from_rfc3339(body["configured_on"])

    # Check the workspace list
    response = await authenticated_client.get("/workspaces")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "workspaces": [
            {
                "id": ANY,
                "name": "wksp1",
                "role": "OWNER",
                "archiving_configuration": "DELETION_PLANNED",
            }
        ]
    }


@pytest.mark.trio
async def test_delete_workspace(
    running_backend,
    local_device: LocalDeviceTestbed,
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
):
    await running_backend.organization.update(
        id=local_device.device.organization_id, minimum_archiving_period=0
    )

    deletion_date = DateTime.now().to_rfc3339()
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving",
        json={"configuration": "DELETION_PLANNED", "deletion_date": deletion_date},
    )
    body = await response.get_json()
    assert response.status_code == 200, body

    # Check the archiving status
    response = await authenticated_client.get(f"/workspaces/{workspace.id}/archiving")
    body = await response.get_json()
    assert response.status_code == 410
    assert body == {"error": "deleted_workspace"}

    # Check the workspace list
    response = await authenticated_client.get("/workspaces")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {"workspaces": []}


@pytest.mark.trio
async def test_workspace_archiving_bad_fields(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
):
    now_str = DateTime.now().to_rfc3339()

    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving", json={"configuration": "NOT_A_CONFIG"}
    )
    body = await response.get_json()
    assert response.status_code == 400, body
    assert body == {"error": "bad_data", "fields": ["configuration"]}

    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving",
        json={"configuration": "NOT_A_CONFIG", "deletion_date": now_str},
    )
    body = await response.get_json()
    assert response.status_code == 400, body
    assert body == {"error": "bad_data", "fields": ["configuration"]}

    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving",
        json={"configuration": "ARCHIVED", "deletion_date": now_str},
    )
    body = await response.get_json()
    assert response.status_code == 400, body
    assert body == {"error": "bad_data", "fields": ["configuration", "deletion_date"]}

    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving", json={"configuration": "DELETION_PLANNED"}
    )
    body = await response.get_json()
    assert response.status_code == 400, body
    assert body == {"error": "bad_data", "fields": ["configuration", "deletion_date"]}

    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving",
        json={"configuration": "DELETION_PLANNED", "deletion_date": None},
    )
    body = await response.get_json()
    assert response.status_code == 400, body
    assert body == {"error": "bad_data", "fields": ["configuration", "deletion_date"]}

    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving",
        json={"configuration": "DELETION_PLANNED", "deletion_date": "214"},
    )
    body = await response.get_json()
    assert response.status_code == 400, body
    assert body == {"error": "bad_data", "fields": ["deletion_date"]}


@pytest.mark.trio
async def test_workspace_archiving_period_too_short(
    authenticated_client: TestClientProtocol,
    workspace: WorkspaceInfo,
):
    deletion_date = DateTime.now().to_rfc3339()
    response = await authenticated_client.post(
        f"/workspaces/{workspace.id}/archiving",
        json={"configuration": "DELETION_PLANNED", "deletion_date": deletion_date},
    )
    body = await response.get_json()
    assert response.status_code == 400, body
    assert body == {"error": "archiving_period_is_too_short"}


@pytest.mark.trio
async def test_workspace_archiving_not_allowed(
    test_app,
    authenticated_client: TestClientProtocol,
    bob_user: LocalDeviceTestbed,
    workspace: WorkspaceInfo,
):
    bob_client = await bob_user.authenticated_client(test_app)

    response = await authenticated_client.patch(
        f"/workspaces/{workspace.id}/share", json={"email": bob_user.email, "role": "MANAGER"}
    )
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {}

    async def condition():
        response = await bob_client.get("/workspaces")
        body = await response.get_json()
        assert response.status_code == 200, body
        assert len(body["workspaces"]) == 1

    await wait_for(condition)

    # Check bob's workspace list
    response = await bob_client.get("/workspaces")
    body = await response.get_json()
    assert response.status_code == 200, body
    assert body == {
        "workspaces": [
            {"archiving_configuration": "AVAILABLE", "id": ANY, "name": "wksp1", "role": "MANAGER"}
        ]
    }

    response = await bob_client.post(
        f"/workspaces/{workspace.id}/archiving", json={"configuration": "ARCHIVED"}
    )
    body = await response.get_json()
    assert response.status_code == 403, body
    assert body == {"error": "archiving_not_allowed"}
