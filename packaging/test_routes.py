from __future__ import annotations

import argparse
import random
from unittest.mock import ANY
import logging
import requests
import base64
import concurrent.futures
import time
import urllib.parse
import contextlib
import uuid
from dataclasses import dataclass
from parsec._parsec import DateTime


from resana_secure.cli import get_default_dirs


logger = logging.getLogger("test-resana")

DEFAULT_EMAIL = "gordon.freeman@blackmesa.nm"
INVITEE_EMAIL = "eli.vance@blackmesa.nm"
DEFAULT_PASSWORD = "P@ssw0rd"

# Using a UUID in case of multiple launches in row,
# so we can always have a unique name for the mountpoint
# on the file system, instead of Parsec appending a number.
DEFAULT_WORKSPACE = f"RCI_{uuid.uuid4()}"

TESTS_STATUS: dict[str, bool] = {}


@contextlib.contextmanager
def run_test(test_name: str):
    @dataclass
    class TestContext:
        request: requests.Response | None

    logger.debug(f"Running --{test_name}--")
    context = TestContext(None)
    try:
        yield context
    except Exception:
        logger.exception(f"[KO] {test_name}")
        if context.request is not None:
            logger.debug(context.request.content)
        TESTS_STATUS[test_name] = False
    else:
        logger.info(f"[OK] {test_name}")
        TESTS_STATUS[test_name] = True


def make_request(method, url, auth_token=None, headers=None, data=None, files=None, json=None):
    logger.debug(f"[Making request {method} {url}")

    headers = headers or {}
    if auth_token:
        # Might as well see if it works with no auth while we're at it
        r = requests.request(method, url, headers=headers, data=data, files=files, json=json)
        # Should be 401 Auth required, else the route is not secure
        if r.status_code != 401:
            logger.error(f"{method} f{url} does not requires authentication.")

        # Now that we checked that auth token was required, we can perform the real request
        headers["Authorization"] = f"Bearer {auth_token}"
    try:
        return requests.request(method, url, headers=headers, data=data, files=files, json=json)
    except Exception as exc:
        logger.error(f"Failed to make request: {type(exc)} {exc}")
        return


def test_workspaces(auth_token, resana_addr):
    VARIABLES = {}

    MOUNTPOINT_DIR, _, _ = get_default_dirs()

    # List workspaces
    with run_test("List workspaces") as context:
        r = make_request("GET", f"{resana_addr}/workspaces", auth_token=auth_token)
        context.context = r
        assert r.status_code == 200
        assert r.json() == {"workspaces": []}

    # Add a new workspace
    with run_test("Add workspace") as context:
        r = make_request(
            "POST",
            f"{resana_addr}/workspaces",
            auth_token=auth_token,
            json={"name": DEFAULT_WORKSPACE},
        )
        context.request = r
        assert r.status_code == 201
        assert r.json() == {"id": ANY}
        VARIABLES["workspace_id"] = r.json()["id"]

    # Checking that we have a new workspace
    with run_test("Check new workspace created") as context:
        r = make_request("GET", f"{resana_addr}/workspaces", auth_token=auth_token)
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"workspaces": [{"id": ANY, "name": DEFAULT_WORKSPACE, "role": "OWNER"}]}
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE).is_dir()

    # Renaming our new workspace
    with run_test("Rename workspace") as context:
        r = make_request(
            "PATCH",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}",
            auth_token=auth_token,
            json={
                "old_name": DEFAULT_WORKSPACE,
                "new_name": f"{DEFAULT_WORKSPACE}_RENAMED",
            },
        )
        context.request = r
        assert r.status_code == 200

    # Checking that it has been renamed
    with run_test("Check workspace renamed") as context:
        r = make_request("GET", f"{resana_addr}/workspaces", auth_token=auth_token)
        context.request = r
        assert r.status_code == 200
        assert r.json() == {
            "workspaces": [{"id": ANY, "name": f"{DEFAULT_WORKSPACE}_RENAMED", "role": "OWNER"}]
        }

    # Checking the share info
    with run_test("Check workspace sharing info") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"roles": {DEFAULT_EMAIL: "OWNER"}}

    # Sharing with second user
    with run_test("Share workspace") as context:
        r = make_request(
            "PATCH",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
            auth_token=auth_token,
            json={"email": INVITEE_EMAIL, "role": "MANAGER"},
        )
        context.request = r
        assert r.status_code == 200

    # Checking the share info
    with run_test("Check new sharing info") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"roles": {DEFAULT_EMAIL: "OWNER", INVITEE_EMAIL: "MANAGER"}}

    # Updating role
    with run_test("Update role") as context:
        r = make_request(
            "PATCH",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
            auth_token=auth_token,
            json={"email": INVITEE_EMAIL, "role": "READER"},
        )
        context.request = r
        assert r.status_code == 200

    # Checking the share info
    with run_test("Check role updated") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"roles": {DEFAULT_EMAIL: "OWNER", INVITEE_EMAIL: "READER"}}

    # Unsharing
    with run_test("Unshare workspace") as context:
        r = make_request(
            "PATCH",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
            auth_token=auth_token,
            json={"email": INVITEE_EMAIL, "role": None},
        )
        context.request = r
        assert r.status_code == 200

    # Checking the share info
    with run_test("Check workspace unshared") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"roles": {DEFAULT_EMAIL: "OWNER"}}


def test_humans(auth_token, resana_addr):
    with run_test("List users") as context:
        r = make_request("GET", f"{resana_addr}/humans", auth_token=auth_token)
        context.request = r
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert len(data["users"]) == 2
        assert all(u["revoked_on"] is None for u in data["users"])

    # Revoking second user
    with run_test("Revoke second user") as context:
        r = make_request(
            "POST", f"{resana_addr}/humans/{INVITEE_EMAIL}/revoke", auth_token=auth_token
        )
        context.request = r
        assert r.status_code == 200

    with run_test("Check user revoked") as context:
        r = make_request("GET", f"{resana_addr}/humans", auth_token=auth_token)
        context.request = r
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert len(data["users"]) == 2
        assert any(
            u["revoked_on"] is not None and u["human_handle"]["email"] == INVITEE_EMAIL
            for u in data["users"]
        )


def test_files(auth_token, resana_addr):
    VARIABLES = {}
    SMALL_FILE_SIZE = 1024
    LARGE_FILE_SIZE = 2**20 * 20  # 20mB

    MOUNTPOINT_DIR, _, _ = get_default_dirs()

    # Get a workspace id
    with run_test("Get workspace id") as context:
        r = make_request("GET", f"{resana_addr}/workspaces", auth_token=auth_token)
        context.request = r
        assert r.status_code == 200
        VARIABLES["workspace_id"] = r.json()["workspaces"][0]["id"]

    # Get folders
    with run_test("Get folders") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/folders",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {
            "children": {},
            "created": ANY,
            "id": ANY,
            "name": "/",
            "updated": ANY,
        }
        VARIABLES["root_folder_id"] = r.json()["id"]
        assert [p for p in (MOUNTPOINT_DIR / DEFAULT_WORKSPACE).iterdir()] == []

    # Create a folder
    with run_test("Create a folder") as context:
        r = make_request(
            "POST",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/folders",
            auth_token=auth_token,
            json={
                "name": "Folder",
                "parent": VARIABLES["root_folder_id"],
            },
        )
        context.request = r
        assert r.status_code == 201
        assert r.json() == {"id": ANY}
        VARIABLES["sub_folder_id"] = r.json()["id"]
        assert [p.name for p in (MOUNTPOINT_DIR / DEFAULT_WORKSPACE).iterdir()] == ["Folder"]
        assert [p.name for p in (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder").iterdir()] == []

    # List folders
    with run_test("List folder to check new folder") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/folders",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {
            "children": {
                "Folder": {
                    "children": {},
                    "created": ANY,
                    "id": VARIABLES["sub_folder_id"],
                    "name": "Folder",
                    "updated": ANY,
                }
            },
            "created": ANY,
            "id": ANY,
            "name": "/",
            "updated": ANY,
        }

    # Post a small file with JSON
    with run_test("Post small file with JSON") as context:
        file_content = random.randbytes(SMALL_FILE_SIZE)
        r = make_request(
            "POST",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files",
            auth_token=auth_token,
            json={
                "name": "test.txt",
                "parent": VARIABLES["sub_folder_id"],
                "content": base64.b64encode(file_content).decode(),
            },
        )
        context.request = r
        assert r.status_code == 201
        assert r.json() == {"id": ANY}
        VARIABLES["file1_id"] = r.json()["id"]
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test.txt").is_file()
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test.txt").stat().st_size == len(
            file_content
        )
        assert (
            MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test.txt"
        ).read_bytes() == file_content

    # Post a small file with multipart
    with run_test("Post small file with multipart") as context:
        file_content = random.randbytes(SMALL_FILE_SIZE)
        r = make_request(
            "POST",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files",
            auth_token=auth_token,
            data={"parent": VARIABLES["sub_folder_id"]},
            files={"file": ("test2.txt", file_content)},
        )
        context.request = r
        assert r.status_code == 201
        assert r.json() == {"id": ANY}
        VARIABLES["file2_id"] = r.json()["id"]
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test2.txt").is_file()
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test2.txt").stat().st_size == len(
            file_content
        )
        assert (
            MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test2.txt"
        ).read_bytes() == file_content

    time.sleep(
        2.0
    )  # Wait for file sync to get timestamp, 2 seconds is long enough to be consistent
    timestamp = DateTime.now().to_rfc3339()

    # Post a large file with JSON
    with run_test("Post large file with JSON") as context:
        file_content = random.randbytes(LARGE_FILE_SIZE)
        r = make_request(
            "POST",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files",
            auth_token=auth_token,
            json={
                "name": "test3.txt",
                "parent": VARIABLES["sub_folder_id"],
                "content": base64.b64encode(file_content).decode(),
            },
        )
        context.request = r
        assert r.status_code == 201
        assert r.json() == {"id": ANY}
        VARIABLES["file3_id"] = r.json()["id"]
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test3.txt").is_file()
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test3.txt").stat().st_size == len(
            file_content
        )

    # Post a large file with multipart
    with run_test("Post large file with multipart") as context:
        file_content = random.randbytes(LARGE_FILE_SIZE)
        r = make_request(
            "POST",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files",
            auth_token=auth_token,
            data={"parent": VARIABLES["sub_folder_id"]},
            files={"file": ("test4.txt", file_content)},
        )
        context.request = r
        assert r.status_code == 201
        assert r.json() == {"id": ANY}
        VARIABLES["file4_id"] = r.json()["id"]
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test4.txt").is_file()
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test4.txt").stat().st_size == len(
            file_content
        )

    # Check if the files were created
    with run_test("Check files created") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/{VARIABLES['sub_folder_id']}",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {
            "files": [
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file1_id"],
                    "name": "test.txt",
                    "size": SMALL_FILE_SIZE,
                    "updated": ANY,
                },
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file2_id"],
                    "name": "test2.txt",
                    "size": SMALL_FILE_SIZE,
                    "updated": ANY,
                },
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file3_id"],
                    "name": "test3.txt",
                    "size": LARGE_FILE_SIZE,
                    "updated": ANY,
                },
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file4_id"],
                    "name": "test4.txt",
                    "size": LARGE_FILE_SIZE,
                    "updated": ANY,
                },
            ]
        }
        assert [p.name for p in (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder").iterdir()] == [
            "test.txt",
            "test2.txt",
            "test3.txt",
            "test4.txt",
        ]

    # Rename the file
    with run_test("Rename a file") as context:
        r = make_request(
            "POST",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/rename",
            auth_token=auth_token,
            json={"id": VARIABLES["file1_id"], "new_name": "test_renamed.txt"},
        )
        context.request = r
        assert r.status_code == 200
        assert not (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test.txt").exists()
        assert (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder" / "test_renamed.txt").exists()

    # Check the folder
    with run_test("Check file renamed") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/{VARIABLES['sub_folder_id']}",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {
            "files": [
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file2_id"],
                    "name": "test2.txt",
                    "size": SMALL_FILE_SIZE,
                    "updated": ANY,
                },
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file3_id"],
                    "name": "test3.txt",
                    "size": LARGE_FILE_SIZE,
                    "updated": ANY,
                },
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file4_id"],
                    "name": "test4.txt",
                    "size": LARGE_FILE_SIZE,
                    "updated": ANY,
                },
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file1_id"],
                    "name": "test_renamed.txt",
                    "size": SMALL_FILE_SIZE,
                    "updated": ANY,
                },
            ]
        }
        assert [p.name for p in (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder").iterdir()] == [
            "test2.txt",
            "test3.txt",
            "test4.txt",
            "test_renamed.txt",
        ]

    # Delete the file
    with run_test("Delete a file") as context:
        r = make_request(
            "DELETE",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/{VARIABLES['file1_id']}",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 204

    # Check the folder
    with run_test("Check file deleted") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/{VARIABLES['sub_folder_id']}",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {
            "files": [
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file2_id"],
                    "name": "test2.txt",
                    "size": SMALL_FILE_SIZE,
                    "updated": ANY,
                },
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file3_id"],
                    "name": "test3.txt",
                    "size": LARGE_FILE_SIZE,
                    "updated": ANY,
                },
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file4_id"],
                    "name": "test4.txt",
                    "size": LARGE_FILE_SIZE,
                    "updated": ANY,
                },
            ]
        }
        assert [p.name for p in (MOUNTPOINT_DIR / DEFAULT_WORKSPACE / "Folder").iterdir()] == [
            "test2.txt",
            "test3.txt",
            "test4.txt",
        ]

    # Mount workspace at previous timestamp
    with run_test("Mount timestamped workspace") as context:
        r = make_request(
            "POST",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/mount",
            auth_token=auth_token,
            json={"timestamp": timestamp},
        )
        context.context = r
        assert r.status_code == 200
        assert r.json() == {"id": f"{VARIABLES['workspace_id']}", "timestamp": timestamp}

    # List workspaces with timestamped
    with run_test("List workspaces with timestamped") as context:
        r = make_request("GET", f"{resana_addr}/workspaces/mountpoints", auth_token=auth_token)
        context.context = r
        assert r.status_code == 200
        assert r.json() == {
            "snapshots": [
                {
                    "id": VARIABLES["workspace_id"],
                    "name": f"{DEFAULT_WORKSPACE}_RENAMED",
                    "role": "READER",
                    "timestamp": timestamp,
                }
            ],
            "workspaces": [
                {
                    "id": f"{VARIABLES['workspace_id']}",
                    "name": f"{DEFAULT_WORKSPACE}_RENAMED",
                    "role": "OWNER",
                }
            ],
        }

    # Check the timestamped content
    with run_test("Check timestamped content") as context:
        r = make_request(
            "GET",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/{VARIABLES['sub_folder_id']}",
            json={"timestamp": timestamp},
            auth_token=auth_token,
        )
        context.request = r

        assert r.status_code == 200
        assert r.json() == {
            "files": [
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file1_id"],
                    "name": "test.txt",
                    "size": SMALL_FILE_SIZE,
                    "updated": ANY,
                },
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file2_id"],
                    "name": "test2.txt",
                    "size": SMALL_FILE_SIZE,
                    "updated": ANY,
                },
            ]
        }

    # Unmount workspace
    with run_test("Unmount timestamped workspace"):
        r = make_request(
            "POST",
            f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/unmount",
            json={"timestamp": timestamp},
            auth_token=auth_token,
        )
        context.context = r
        assert r.status_code == 200
        assert r.json() == {}

    # Checking that the timestamped is gone
    with run_test("Check timestamped unmounted") as context:
        r = make_request("GET", f"{resana_addr}/workspaces/mountpoints", auth_token=auth_token)
        context.request = r
        assert r.status_code == 200
        assert r.json() == {
            "snapshots": [],
            "workspaces": [{"id": ANY, "name": f"{DEFAULT_WORKSPACE}_RENAMED", "role": "OWNER"}],
        }


def test_user_invitations(auth_token, resana_addr, org_id):
    VARIABLES = {}

    def _claimer_wait():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/1-wait-peer-ready",
        )

    def _greeter_wait():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/1-wait-peer-ready",
            auth_token=auth_token,
        )

    def _greeter_wait_peer_trust():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/2-wait-peer-trust",
            auth_token=auth_token,
        )

    def _claimer_check_trust():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/2-check-trust",
            json={"greeter_sas": VARIABLES["greeter_sas"]},
        )

    def _claimer_wait_peer_trust():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/3-wait-peer-trust",
        )

    def _greeter_check_trust():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/3-check-trust",
            auth_token=auth_token,
            json={"claimer_sas": VARIABLES["claimer_sas"]},
        )

    def _greeter_finalize():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/4-finalize",
            auth_token=auth_token,
            json={"claimer_email": INVITEE_EMAIL, "granted_profile": "STANDARD"},
        )

    def _claimer_finalize(password):
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/4-finalize",
            json={"key": password},
        )

    def _invite_user():
        # Inviting someone
        with run_test("Invite someone") as context:
            r = make_request(
                "POST",
                f"{resana_addr}/invitations",
                auth_token=auth_token,
                json={"type": "user", "claimer_email": INVITEE_EMAIL},
            )
            context.request = r
            assert r.status_code == 200
            assert r.json() == {"token": ANY}
            token = r.json()["token"]

        # Check that the new invitation appears
        with run_test("Check invitation appears") as context:
            r = make_request("GET", f"{resana_addr}/invitations", auth_token=auth_token)
            context.request = r
            assert r.status_code == 200
            assert r.json() == {
                "device": None,
                "users": [
                    {
                        "claimer_email": INVITEE_EMAIL,
                        "created_on": ANY,
                        "status": "IDLE",
                        "token": token,
                    }
                ],
            }
        return token

    # List invitations
    with run_test("List invitations") as context:
        r = make_request("GET", f"{resana_addr}/invitations", auth_token=auth_token)
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"device": None, "users": []}

    token = _invite_user()

    # Delete user invitation
    with run_test("Delete user invitation") as context:
        r = make_request(
            "DELETE",
            f"{resana_addr}/invitations/{token}",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 204

    VARIABLES["token"] = _invite_user()

    # Claimer retrieve info (and not retrEIve)
    with run_test("Claimer retrieve info") as context:
        r = make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/0-retreive-info",
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"greeter_email": DEFAULT_EMAIL, "type": "user"}

    claimer_ret = None
    greeter_ret = None
    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_wait)
        greeter_future = executor.submit(_greeter_wait)
        claimer_ret = claimer_future.result()
        greeter_ret = greeter_future.result()

    with run_test("Invite user greeter wait") as context:
        context.request = greeter_ret
        context.request = r
        assert greeter_ret.status_code == 200
        assert greeter_ret.json() == {"greeter_sas": ANY, "type": "user"}

    with run_test("Invite user claimer wait") as context:
        context.request = claimer_ret
        assert claimer_ret.status_code == 200
        assert claimer_ret.json() == {"candidate_greeter_sas": [ANY, ANY, ANY, ANY]}
        assert greeter_ret.json()["greeter_sas"] in claimer_ret.json()["candidate_greeter_sas"]
        VARIABLES["greeter_sas"] = greeter_ret.json()["greeter_sas"]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        greeter_future = executor.submit(_greeter_wait_peer_trust)
        time.sleep(1.0)
        claimer_future = executor.submit(_claimer_check_trust)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    with run_test("Invite user greeter wait peer trust") as context:
        context.request = greeter_ret
        assert greeter_ret.status_code == 200
        greeter_ret.json() == {"candidate_claimer_sas": [ANY, ANY, ANY, ANY]}

    with run_test("Invite user claimer check trust") as context:
        context.request = claimer_ret
        assert claimer_ret.status_code == 200
        claimer_ret.json() == {"claimer_sas": ANY}
        assert claimer_ret.json()["claimer_sas"] in greeter_ret.json()["candidate_claimer_sas"]
        VARIABLES["claimer_sas"] = claimer_ret.json()["claimer_sas"]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_wait_peer_trust)
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_check_trust)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    with run_test("Invite user greeter check trust") as context:
        context.request = greeter_ret
        assert greeter_ret.status_code == 200

    with run_test("Invite user claimer wait peer trust") as context:
        context.request = claimer_ret
        assert claimer_ret.status_code == 200

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_finalize, password="ClaimUserNewP@ssw0rd")
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_finalize)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    with run_test("Invite user claimer finalize") as context:
        context.request = claimer_ret
        assert claimer_ret.status_code == 200

    with run_test("Invite user greeter finalize") as context:
        context.request = greeter_ret
        assert greeter_ret.status_code == 200

    with run_test("List user check new user") as context:
        r = make_request("GET", f"{resana_addr}/humans", auth_token=auth_token)
        context.request = r
        assert r.status_code == 200
        assert r.json()["total"] == 2
        assert any(u["human_handle"]["email"] == INVITEE_EMAIL for u in r.json()["users"])

    # Try to log with the new user
    with run_test("Log in with new user") as context:
        r = make_request(
            "POST",
            f"{resana_addr}/auth",
            json={
                "email": INVITEE_EMAIL,
                "key": "ClaimUserNewP@ssw0rd",
                "organization": org_id,
            },
        )
        context.request = r
        assert r.status_code == 200
        assert r.json()["token"] == ANY


def test_device_invitations(auth_token, resana_addr, org_id):
    VARIABLES = {}

    def _claimer_wait():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/1-wait-peer-ready",
        )

    def _greeter_wait():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/1-wait-peer-ready",
            auth_token=auth_token,
        )

    def _greeter_wait_peer_trust():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/2-wait-peer-trust",
            auth_token=auth_token,
        )

    def _claimer_check_trust():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/2-check-trust",
            json={"greeter_sas": VARIABLES["greeter_sas"]},
        )

    def _claimer_wait_peer_trust():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/3-wait-peer-trust",
        )

    def _greeter_check_trust():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/3-check-trust",
            auth_token=auth_token,
            json={"claimer_sas": VARIABLES["claimer_sas"]},
        )

    def _greeter_finalize():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/4-finalize",
            auth_token=auth_token,
            json={"claimer_email": INVITEE_EMAIL, "granted_profile": "STANDARD"},
        )

    def _claimer_finalize(password):
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/4-finalize",
            json={"key": password},
        )

    def _invite_device():
        token = None

        # Inviting a new device
        with run_test("Invite new device") as context:
            r = make_request(
                "POST",
                f"{resana_addr}/invitations",
                auth_token=auth_token,
                json={"type": "device"},
            )
            context.request = r
            assert r.status_code == 200
            assert r.json() == {"token": ANY}
            token = r.json()["token"]

        # Check that the new invitation appears
        with run_test("Check new device invitation") as context:
            r = make_request("GET", f"{resana_addr}/invitations", auth_token=auth_token)
            context.request = r
            assert r.status_code == 200
            assert r.json() == {
                "device": {
                    "token": token,
                    "created_on": ANY,
                    "status": "IDLE",
                },
                "users": [],
            }
        return token

    # List invitations
    with run_test("List device invitations") as context:
        r = make_request("GET", f"{resana_addr}/invitations", auth_token=auth_token)
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"device": None, "users": []}

    token = _invite_device()

    # Delete device invitation
    with run_test("Delete device invitation") as context:
        r = make_request(
            "DELETE",
            f"{resana_addr}/invitations/{token}",
            auth_token=auth_token,
        )
        context.request = r
        assert r.status_code == 204

    VARIABLES["token"] = _invite_device()

    # Claimer retrieve info (and not retrEIve)
    with run_test("Claim device retrieve info") as context:
        r = make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/0-retreive-info",
        )
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"greeter_email": DEFAULT_EMAIL, "type": "device"}

    claimer_ret = None
    greeter_ret = None
    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_wait)
        greeter_future = executor.submit(_greeter_wait)
        claimer_ret = claimer_future.result()
        greeter_ret = greeter_future.result()

    with run_test("Invite device greeter wait") as context:
        context.request = greeter_ret
        assert greeter_ret.status_code == 200
        assert greeter_ret.json() == {"greeter_sas": ANY, "type": "device"}

    with run_test("Invite device claimer wait") as context:
        context.request = claimer_ret
        assert claimer_ret.status_code == 200
        assert claimer_ret.json() == {"candidate_greeter_sas": [ANY, ANY, ANY, ANY]}
        assert greeter_ret.json()["greeter_sas"] in claimer_ret.json()["candidate_greeter_sas"]
        VARIABLES["greeter_sas"] = greeter_ret.json()["greeter_sas"]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        greeter_future = executor.submit(_greeter_wait_peer_trust)
        time.sleep(1.0)
        claimer_future = executor.submit(_claimer_check_trust)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    with run_test("Invite device greeter wait peer trust") as context:
        context.request = greeter_ret
        assert greeter_ret.status_code == 200
        greeter_ret.json() == {"candidate_claimer_sas": [ANY, ANY, ANY, ANY]}

    with run_test("Invite device claimer check trust") as context:
        context.request = claimer_ret
        assert claimer_ret.status_code == 200
        claimer_ret.json() == {"claimer_sas": ANY}
        assert claimer_ret.json()["claimer_sas"] in greeter_ret.json()["candidate_claimer_sas"]
        VARIABLES["claimer_sas"] = claimer_ret.json()["claimer_sas"]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_wait_peer_trust)
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_check_trust)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    with run_test("Invite device greeter check trust") as context:
        context.request = greeter_ret
        assert greeter_ret.status_code == 200

    with run_test("Invite device claimer wait peer trust") as context:
        context.request = claimer_ret
        assert claimer_ret.status_code == 200

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_finalize, password="ClaimDeviceNewP@ssw0rd")
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_finalize)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    with run_test("Invite device claimer finalize") as context:
        context.request = claimer_ret
        assert claimer_ret.status_code == 200

    with run_test("Invite device greeter finalize") as context:
        context.request = greeter_ret
        assert greeter_ret.status_code == 200

    # Try to log with the new device
    with run_test("Log in with new device") as context:
        r = make_request(
            "POST",
            f"{resana_addr}/auth",
            json={
                "email": DEFAULT_EMAIL,
                "key": "ClaimDeviceNewP@ssw0rd",
                "organization": org_id,
            },
        )
        context.request = r
        assert r.status_code == 200
        assert r.json()["token"] == ANY


def test_recovery(auth_token, resana_addr, org_id):
    VARIABLES = {}

    # Create a recovery device
    with run_test("Create recovery device") as context:
        r = make_request("POST", f"{resana_addr}/recovery/export", auth_token=auth_token, json={})
        context.request = r
        assert r.status_code == 200
        assert r.json() == {"file_content": ANY, "file_name": ANY, "passphrase": ANY}
        VARIABLES["recovery_device"] = base64.b64decode(r.json()["file_content"].encode())
        VARIABLES["passphrase"] = r.json()["passphrase"]

    # Import the recovery device
    with run_test("Import recovery device") as r:
        r = make_request(
            "POST",
            f"{resana_addr}/recovery/import",
            json={
                "recovery_device_file_content": base64.b64encode(
                    VARIABLES["recovery_device"]
                ).decode(),
                "recovery_device_passphrase": VARIABLES["passphrase"],
                "new_device_key": "RecoveryNewP@ssw0rd",
            },
        )
        context.request = r
        assert r.status_code == 200

    # Try to log with the new device
    with run_test("Log in with recovered device") as context:
        r = make_request(
            "POST",
            f"{resana_addr}/auth",
            json={
                "email": DEFAULT_EMAIL,
                "key": "RecoveryNewP@ssw0rd",
                "organization": org_id,
            },
        )
        context.request = r
        assert r.status_code == 200
        assert r.json()["token"] == ANY


def main(
    resana_addr,
    bootstrap_addr,
    org_id,
    skip_bootstrap=False,
    skip_humans=False,
    skip_workspaces=False,
    skip_files=False,
    skip_user_invite=False,
    skip_device_invite=False,
    skip_recovery=False,
):
    """Test all Resana routes.

    The script needs the URL to a running Resana instance, a Parsec backend address (with
    the backend configured with `spontaneous bootstrap`) and an organization id.
    """

    if not skip_bootstrap:
        logger.info(f"Bootstraping using `{bootstrap_addr}`")
        r = make_request(
            "POST",
            f"{resana_addr}/organization/bootstrap",
            json={
                "organization_url": bootstrap_addr,
                "email": DEFAULT_EMAIL,
                "key": DEFAULT_PASSWORD,
            },
        )
        assert r.status_code == 200

    logger.info("Authenticating...")
    r = make_request(
        "POST",
        f"{resana_addr}/auth",
        json={
            "email": DEFAULT_EMAIL,
            "key": DEFAULT_PASSWORD,
            "organization": org_id,
        },
    )
    assert r.status_code == 200
    auth_token = r.json()["token"]

    # Start with invitation, so we can have another user
    if not skip_user_invite:
        test_user_invitations(auth_token, resana_addr, org_id)
    if not skip_device_invite:
        test_device_invitations(auth_token, resana_addr, org_id)
    # Continue with workspaces, share/unshare
    if not skip_workspaces:
        test_workspaces(auth_token, resana_addr)
    # Upload, rename, delete files
    if not skip_files:
        test_files(auth_token, resana_addr)
    # Humans to test the revoke
    if not skip_humans:
        test_humans(auth_token, resana_addr)
    # Device recovery
    if not skip_recovery:
        test_recovery(auth_token, resana_addr, org_id)

    logger.info("Logging out...")
    r = make_request(
        "DELETE",
        f"{resana_addr}/auth",
    )
    assert r.status_code == 200


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=main.__doc__)

    parser.add_argument(
        "-r",
        "--resana",
        type=str,
        default="http://127.0.0.1:5775",
        help="Resana addr",
    )
    parser.add_argument(
        "-p",
        "--parsec",
        type=str,
        default="parsec://localhost:6888?no_ssl=true",
        help="Parsec backend address",
    )
    parser.add_argument(
        "-o",
        "--org",
        type=str,
        required=True,
        help="Organization ID",
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Adds extra debugging info")
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="Skip organization bootstrap (this may have an impact on other APIs)",
    )
    parser.add_argument(
        "--skip-humans",
        action="store_true",
        help="Skip human API (this may have an impact on other APIs)",
    )
    parser.add_argument(
        "--skip-workspaces",
        action="store_true",
        help="Skip workspace API (this may have an impact on other APIs)",
    )
    parser.add_argument(
        "--skip-files",
        action="store_true",
        help="Skip files API (this may have an impact on other APIs)",
    )
    parser.add_argument(
        "--skip-user-invite",
        action="store_true",
        help="Skip user invite API (this may have an impact on other APIs)",
    )
    parser.add_argument(
        "--skip-device-invite",
        action="store_true",
        help="Skip device invite API (this may have an impact on other APIs)",
    )
    parser.add_argument("--skip-recovery", action="store_true", help="Skip the recovery API")

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logging.getLogger("urllib3").setLevel(logging.WARNING)

    parsed = urllib.parse.urlparse(args.parsec)
    bootstrap_addr = (
        f"{parsed.scheme}://{parsed.netloc}/{args.org}?{parsed.query}&action=bootstrap_organization"
    )

    main(
        args.resana,
        bootstrap_addr,
        args.org,
        skip_bootstrap=args.skip_bootstrap,
        skip_humans=args.skip_humans,
        skip_workspaces=args.skip_workspaces,
        skip_files=args.skip_files,
        skip_user_invite=args.skip_user_invite,
        skip_device_invite=args.skip_device_invite,
        skip_recovery=args.skip_recovery,
    )

    ret_code = 0
    if TESTS_STATUS:
        print("-----")
        for test_name, status in TESTS_STATUS.items():
            if not status:
                ret_code = 1
                print(f"FAILED -> {test_name}")
        print("-----")
    raise SystemExit(ret_code)
