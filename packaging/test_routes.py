import argparse
from unittest.mock import ANY
import logging
import requests
import base64
import concurrent.futures
import time
import urllib


logger = logging.getLogger("test-resana")


DEFAULT_EMAIL = "gordon.freeman@blackmesa.nm"
INVITEE_EMAIL = "eli.vance@blackmesa.nm"
DEFAULT_PASSWORD = "P@ssw0rd"
DEFAULT_WORKSPACE = "Resonance Cascade Incident"


def make_request(method, url, auth_token=None, headers=None, data=None):
    logger.debug(f"[Making request {method} {url}")

    headers = headers or {}
    if auth_token:
        # Might as well see if it works with no auth while we're at it
        r = getattr(requests, method.lower())(url, headers=headers, json=data)
        # Should be 401 Auth required, else the route is not secure
        if r.status_code != 401:
            logger.error(f"{method} f{url} does not requires authentication.")

        # Now that we checked that auth token was required, we can perform the real request
        headers["Authorization"] = f"Bearer {auth_token}"
    try:
        r = getattr(requests, method.lower())(url, headers=headers, json=data)
        return r
    except Exception as exc:
        logger.error(f"Failed to make request: {type(exc)} {exc}")


def test_workspaces(auth_token, resana_addr):
    VARIABLES = {}

    # List workspaces
    r = make_request("GET", f"{resana_addr}/workspaces", auth_token=auth_token)
    try:
        assert r.status_code == 200
        assert r.json() == {"workspaces": []}
    except AssertionError:
        logger.exception("[KO] List workspaces")
        logger.debug(r.json())
    else:
        logger.info("[OK] List workspaces")

    # Add a new workspace
    r = make_request(
        "POST",
        f"{resana_addr}/workspaces",
        auth_token=auth_token,
        data={"name": "Resonance Cascade Incident"},
    )
    try:
        assert r.status_code == 201
        assert r.json() == {"id": ANY}
        VARIABLES["workspace_id"] = r.json()["id"]
    except AssertionError:
        logger.exception("[KO] Adding a new workspace")
        logger.debug(r.json())
    else:
        logger.info("[OK] Adding a new workspace")

    # Checking that we have a new workspace
    r = make_request("GET", f"{resana_addr}/workspaces", auth_token=auth_token)
    try:
        assert r.status_code == 200
        assert r.json() == {
            "workspaces": [{"id": ANY, "name": DEFAULT_WORKSPACE, "role": "OWNER"}]
        }
    except AssertionError:
        logger.exception("[KO] List workspace to check that we have one")
        logger.debug(r.json())
    else:
        logger.info("[OK] List workspace to check that we have one")

    # Renaming our new workspace
    r = make_request(
        "PATCH",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}",
        auth_token=auth_token,
        data={
            "old_name": DEFAULT_WORKSPACE,
            "new_name": f"{DEFAULT_WORKSPACE}_RENAMED",
        },
    )
    try:
        assert r.status_code == 200
    except AssertionError:
        logger.exception("[KO] Rename the workspace")
        logger.debug(r.json())
    else:
        logger.info("[OK] Rename the workspace")

    # Checking that it has been renamed
    r = make_request("GET", f"{resana_addr}/workspaces", auth_token=auth_token)
    try:
        assert r.status_code == 200
        assert r.json() == {
            "workspaces": [
                {"id": ANY, "name": f"{DEFAULT_WORKSPACE}_RENAMED", "role": "OWNER"}
            ]
        }
    except AssertionError:
        logger.exception("[KO] Check that the workspace was renamed")
        logger.debug(r.json())
    else:
        logger.info("[OK] Check that the workspace was renamed")

    # Checking the share info
    r = make_request(
        "GET",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 200
        assert r.json() == {"roles": {DEFAULT_EMAIL: "OWNER"}}
    except AssertionError:
        logger.exception("[KO] Get the sharing info")
        logger.debug(r.json())
    else:
        logger.info("[OK] Get the sharing info")

    # Sharing with second user
    r = make_request(
        "PATCH",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
        auth_token=auth_token,
        data={"email": INVITEE_EMAIL, "role": "MANAGER"},
    )
    try:
        assert r.status_code == 200
    except AssertionError:
        logger.exception("[KO] Share the workspace")
        logger.debug(r.json())
    else:
        logger.info("[OK] Share the workspace")

    # Checking the share info
    r = make_request(
        "GET",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 200
        assert r.json() == {"roles": {DEFAULT_EMAIL: "OWNER", INVITEE_EMAIL: "MANAGER"}}
    except AssertionError:
        logger.exception("[KO] Check that the workspace has been shared")
        logger.debug(r.json())
    else:
        logger.info("[OK] Check that the workspace has been shared")

    # Updating role
    r = make_request(
        "PATCH",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
        auth_token=auth_token,
        data={"email": INVITEE_EMAIL, "role": "READER"},
    )
    try:
        assert r.status_code == 200
    except AssertionError:
        logger.exception("[KO] Update role")
        logger.debug(r.json())
    else:
        logger.info("[OK] Update role")

    # Checking the share info
    r = make_request(
        "GET",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 200
        assert r.json() == {"roles": {DEFAULT_EMAIL: "OWNER", INVITEE_EMAIL: "READER"}}
    except AssertionError:
        logger.exception("[KO] Check that role has been updated")
        logger.debug(r.json())
    else:
        logger.info("[OK] Check that role has been updated")

    # Unsharing
    r = make_request(
        "PATCH",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
        auth_token=auth_token,
        data={"email": INVITEE_EMAIL, "role": None},
    )
    try:
        assert r.status_code == 200
    except AssertionError:
        logger.exception("[KO] Unshare the workspace")
        logger.debug(r.json())
    else:
        logger.info("[OK] Unshare the workspace")

    # Checking the share info
    r = make_request(
        "GET",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/share",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 200
        assert r.json() == {"roles": {DEFAULT_EMAIL: "OWNER"}}
    except AssertionError:
        logger.exception(
            "[KO] Make sure that the workspace is no longer shared with bob"
        )
        logger.debug(r.json())
    else:
        logger.info("[OK] Make sure that the workspace is no longer shared with bob")


def test_humans(auth_token, resana_addr):
    r = make_request("GET", f"{resana_addr}/humans", auth_token=auth_token)
    try:
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert len(data["users"]) == 2
        assert all(u["revoked_on"] is None for u in data["users"])
    except AssertionError:
        logger.exception("[KO] List users")
    else:
        logger.info("[OK] List users")

    # Revoking second user
    r = make_request(
        "POST", f"{resana_addr}/humans/{INVITEE_EMAIL}/revoke", auth_token=auth_token
    )
    try:
        assert r.status_code == 200
    except AssertionError:
        logger.exception("[KO] Revoke second user")
    else:
        logger.info("[OK] Revoke second user")

    r = make_request("GET", f"{resana_addr}/humans", auth_token=auth_token)
    try:
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert len(data["users"]) == 2
        assert any(
            u["revoked_on"] is not None and u["human_handle"]["email"] == INVITEE_EMAIL
            for u in data["users"]
        )
    except AssertionError:
        logger.exception("[KO] Make sure that user was revoked")
    else:
        logger.info("[OK] Make sure that user was revoked")


def test_files(auth_token, resana_addr):
    VARIABLES = {}

    # Get a workspace id
    r = make_request("GET", f"{resana_addr}/workspaces", auth_token=auth_token)
    try:
        assert r.status_code == 200
        VARIABLES["workspace_id"] = r.json()["workspaces"][0]["id"]
    except AssertionError:
        logger.exception("[KO] List workspaces")
        logger.debug(r.json())
    else:
        logger.info("[OK] List workspaces")

    # Get folders
    r = make_request(
        "GET",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/folders",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 200
        assert r.json() == {
            "children": {},
            "created": ANY,
            "id": ANY,
            "name": "/",
            "updated": ANY,
        }
        VARIABLES["root_folder_id"] = r.json()["id"]
    except AssertionError:
        logger.exception("[KO] List folders")
        logger.debug(r.json())
    else:
        logger.info("[OK] List folders")

    # Create a folder
    r = make_request(
        "POST",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/folders",
        auth_token=auth_token,
        data={
            "name": "Folder",
            "parent": VARIABLES["root_folder_id"],
        },
    )
    try:
        assert r.status_code == 201
        assert r.json() == {"id": ANY}
        VARIABLES["sub_folder_id"] = r.json()["id"]
    except AssertionError:
        logger.exception("[KO] Create a folder")
        logger.debug(r.json())
    else:
        logger.info("[OK] Create a folder")

    # List folders
    r = make_request(
        "GET",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/folders",
        auth_token=auth_token,
    )
    try:
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
    except AssertionError:
        logger.exception("[KO] Check new folder created")
        logger.debug(r.json())
    else:
        logger.info("[OK] Check new folder created")

    # Post a file
    r = make_request(
        "POST",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files",
        auth_token=auth_token,
        data={
            "name": "test.txt",
            "parent": VARIABLES["sub_folder_id"],
            "content": base64.b64encode(b"test").decode(),
        },
    )
    try:
        assert r.status_code == 201
        assert r.json() == {"id": ANY}
        VARIABLES["file1_id"] = r.json()["id"]
    except AssertionError:
        logger.exception("[KO] Upload a new file")
        logger.debug(r.json())
    else:
        logger.info("[OK] Upload a new file")

    # Check if the file was created
    r = make_request(
        "GET",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/{VARIABLES['sub_folder_id']}",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 200
        assert r.json() == {
            "files": [
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file1_id"],
                    "name": "test.txt",
                    "size": 4,
                    "updated": ANY,
                }
            ]
        }
    except AssertionError:
        logger.exception("[KO] Make sure the file appears")
        logger.debug(r.json())
    else:
        logger.info("[OK] Make sure the file appears")

    # Rename the file
    r = make_request(
        "POST",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/rename",
        auth_token=auth_token,
        data={"id": VARIABLES["file1_id"], "new_name": "test_renamed.txt"},
    )
    try:
        assert r.status_code == 200
    except AssertionError:
        logger.exception("[KO] Rename the file")
        logger.debug(r.json())
    else:
        logger.info("[OK] Rename the file")

    # Check the folder
    r = make_request(
        "GET",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/{VARIABLES['sub_folder_id']}",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 200
        assert r.json() == {
            "files": [
                {
                    "created": ANY,
                    "extension": "txt",
                    "id": VARIABLES["file1_id"],
                    "name": "test_renamed.txt",
                    "size": 4,
                    "updated": ANY,
                }
            ]
        }
    except AssertionError:
        logger.exception("[KO] Make sure the file was renamed")
        logger.debug(r.json())
    else:
        logger.info("[OK] Make sure the file was renamed")

    # Delete the file
    r = make_request(
        "DELETE",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/{VARIABLES['file1_id']}",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 204
    except AssertionError:
        logger.exception("[KO] Delete the file")
    else:
        logger.info("[OK] Delete the file")

    # Check the folder
    r = make_request(
        "GET",
        f"{resana_addr}/workspaces/{VARIABLES['workspace_id']}/files/{VARIABLES['sub_folder_id']}",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 200
        assert r.json() == {"files": []}
    except AssertionError:
        logger.exception("[KO] Make sure the file was deleted")
        logger.debug(r.json())
    else:
        logger.info("[OK] Make sure the file was deleted")


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
            data={"greeter_sas": VARIABLES["greeter_sas"]},
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
            data={"claimer_sas": VARIABLES["claimer_sas"]},
        )

    def _greeter_finalize():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/4-finalize",
            auth_token=auth_token,
            data={"claimer_email": INVITEE_EMAIL, "granted_profile": "STANDARD"},
        )

    def _claimer_finalize(password):
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/4-finalize",
            data={"key": password},
        )

    def _invite_user():
        # Inviting someone
        r = make_request(
            "POST",
            f"{resana_addr}/invitations",
            auth_token=auth_token,
            data={"type": "user", "claimer_email": INVITEE_EMAIL},
        )
        try:
            assert r.status_code == 200
            assert r.json() == {"token": ANY}
            token = r.json()["token"]
        except AssertionError:
            logger.exception("[KO] Inviting user")
            logger.debug(r.json())
        else:
            logger.info("[OK] Inviting user")

        # Check that the new invitation appears
        r = make_request("GET", f"{resana_addr}/invitations", auth_token=auth_token)
        try:
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
        except AssertionError:
            logger.exception("[KO] Checking if the new userinvitation appears")
            logger.debug(r.json())
        else:
            logger.info("[OK] Checking if the new user invitation appears")
        return token

    # List invitations
    r = make_request("GET", f"{resana_addr}/invitations", auth_token=auth_token)
    try:
        assert r.status_code == 200
        assert r.json() == {"device": None, "users": []}
    except AssertionError:
        logger.exception("[KO] Invite user listing invitations")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user listing invitations")

    token = _invite_user()

    # Delete user invitation
    r = make_request(
        "DELETE",
        f"{resana_addr}/invitations/{token}",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 204
    except AssertionError:
        logger.exception("[KO] Delete user invitation")
    else:
        logger.info("[OK] Delete user invitation")

    VARIABLES["token"] = _invite_user()

    # Claimer retrieve info (and not retrEIve)
    r = make_request(
        "POST",
        f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/0-retreive-info",
    )
    try:
        assert r.status_code == 200
        assert r.json() == {"greeter_email": DEFAULT_EMAIL, "type": "user"}
    except AssertionError:
        logger.exception("[KO] Invite user claimer retrieve info")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user claimer retrieve info")

    claimer_ret = None
    greeter_ret = None
    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_wait)
        greeter_future = executor.submit(_greeter_wait)
        claimer_ret = claimer_future.result()
        greeter_ret = greeter_future.result()

    try:
        assert greeter_ret.status_code == 200
        assert greeter_ret.json() == {"greeter_sas": ANY, "type": "user"}
    except AssertionError:
        logger.exception("[KO] Invite user greeter wait")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user greeter wait")

    try:
        assert claimer_ret.status_code == 200
        assert claimer_ret.json() == {"candidate_greeter_sas": [ANY, ANY, ANY, ANY]}
        assert (
            greeter_ret.json()["greeter_sas"]
            in claimer_ret.json()["candidate_greeter_sas"]
        )
        VARIABLES["greeter_sas"] = greeter_ret.json()["greeter_sas"]
    except AssertionError:
        logger.exception("[KO] Invite user claimer wait")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user claimer wait")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        greeter_future = executor.submit(_greeter_wait_peer_trust)
        time.sleep(1.0)
        claimer_future = executor.submit(_claimer_check_trust)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    try:
        assert greeter_ret.status_code == 200
        greeter_ret.json() == {"candidate_claimer_sas": [ANY, ANY, ANY, ANY]}
    except AssertionError:
        logger.exception("[KO] Invite user greeter wait peer trust")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user greeter wait peer trust")

    try:
        assert claimer_ret.status_code == 200
        claimer_ret.json() == {"claimer_sas": ANY}
        assert (
            claimer_ret.json()["claimer_sas"]
            in greeter_ret.json()["candidate_claimer_sas"]
        )
        VARIABLES["claimer_sas"] = claimer_ret.json()["claimer_sas"]
    except AssertionError:
        logger.exception("[KO] Invite user claimer check trust")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user claimer check trust")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_wait_peer_trust)
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_check_trust)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    try:
        assert greeter_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Invite user greeter check trust")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user greeter check trust")

    try:
        assert claimer_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Invite user claimer wait peer trust")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user claimer wait peer trust")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(
            _claimer_finalize, password="ClaimUserNewP@ssw0rd"
        )
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_finalize)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    try:
        assert claimer_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Invite user claimer finalize")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user claimer finalize")

    try:
        assert greeter_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Invite user greeter finalize")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite user greeter finalize")

    r = make_request("GET", f"{resana_addr}/humans", auth_token=auth_token)
    try:
        assert r.status_code == 200
        assert r.json()["total"] == 2
        assert any(
            u["human_handle"]["email"] == INVITEE_EMAIL for u in r.json()["users"]
        )
    except AssertionError:
        logger.exception("[KO] List users to see new user")
        logger.debug(r.json())
    else:
        logger.info("[OK] List users to see new user")

    # Try to log with the new user
    r = make_request(
        "POST",
        f"{resana_addr}/auth",
        data={
            "email": INVITEE_EMAIL,
            "key": "ClaimUserNewP@ssw0rd",
            "organization": org_id,
        },
    )
    try:
        assert r.status_code == 200
        assert r.json()["token"] == ANY
    except AssertionError:
        logger.exception("[KO] Log in with new user")
        logger.debug(r.json())
    else:
        logger.info("[OK] Log in with new user")


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
            data={"greeter_sas": VARIABLES["greeter_sas"]},
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
            data={"claimer_sas": VARIABLES["claimer_sas"]},
        )

    def _greeter_finalize():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/greeter/4-finalize",
            auth_token=auth_token,
            data={"claimer_email": INVITEE_EMAIL, "granted_profile": "STANDARD"},
        )

    def _claimer_finalize(password):
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/4-finalize",
            data={"key": password},
        )

    def _invite_device():
        token = None

        # Inviting a new device
        r = make_request(
            "POST",
            f"{resana_addr}/invitations",
            auth_token=auth_token,
            data={"type": "device"},
        )
        try:
            assert r.status_code == 200
            assert r.json() == {"token": ANY}
            token = r.json()["token"]
        except AssertionError:
            logger.exception("[KO] Inviting device")
            logger.debug(r.json())
        else:
            logger.info("[OK] Inviting device")

        # Check that the new invitation appears
        r = make_request("GET", f"{resana_addr}/invitations", auth_token=auth_token)
        try:
            assert r.status_code == 200
            assert r.json() == {
                "device": {
                    "token": token,
                    "created_on": ANY,
                    "status": "IDLE",
                },
                "users": [],
            }
        except AssertionError:
            logger.exception("[KO] Checking if the new device invitation appears")
            logger.debug(r.json())
        else:
            logger.info("[OK] Checking if the new device invitation appears")
        return token

    # List invitations
    r = make_request("GET", f"{resana_addr}/invitations", auth_token=auth_token)
    try:
        assert r.status_code == 200
        assert r.json() == {"device": None, "users": []}
    except AssertionError:
        logger.exception("[KO] Invite device listing invitations")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device listing invitations")

    token = _invite_device()

    # Delete device invitation
    r = make_request(
        "DELETE",
        f"{resana_addr}/invitations/{token}",
        auth_token=auth_token,
    )
    try:
        assert r.status_code == 204
    except AssertionError:
        logger.exception("[KO] Delete device invitation")
        logger.debug(r.status_code, r.json())
    else:
        logger.info("[OK] Delete device invitation")

    VARIABLES["token"] = _invite_device()

    # Claimer retrieve info (and not retrEIve)
    r = make_request(
        "POST",
        f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/0-retreive-info",
    )
    try:
        assert r.status_code == 200
        assert r.json() == {"greeter_email": DEFAULT_EMAIL, "type": "device"}
    except AssertionError:
        logger.exception("[KO] Invite device claimer retrieve info")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device claimer retrieve info")

    claimer_ret = None
    greeter_ret = None
    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_wait)
        greeter_future = executor.submit(_greeter_wait)
        claimer_ret = claimer_future.result()
        greeter_ret = greeter_future.result()

    try:
        assert greeter_ret.status_code == 200
        assert greeter_ret.json() == {"greeter_sas": ANY, "type": "device"}
    except AssertionError:
        logger.exception("[KO] Invite device greeter wait")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device greeter wait")

    try:
        assert claimer_ret.status_code == 200
        assert claimer_ret.json() == {"candidate_greeter_sas": [ANY, ANY, ANY, ANY]}
        assert (
            greeter_ret.json()["greeter_sas"]
            in claimer_ret.json()["candidate_greeter_sas"]
        )
        VARIABLES["greeter_sas"] = greeter_ret.json()["greeter_sas"]
    except AssertionError:
        logger.exception("[KO] Invite device claimer wait")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device claimer wait")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        greeter_future = executor.submit(_greeter_wait_peer_trust)
        time.sleep(1.0)
        claimer_future = executor.submit(_claimer_check_trust)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    try:
        assert greeter_ret.status_code == 200
        greeter_ret.json() == {"candidate_claimer_sas": [ANY, ANY, ANY, ANY]}
    except AssertionError:
        logger.exception("[KO] Invite device greeter wait peer trust")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device greeter wait peer trust")

    try:
        assert claimer_ret.status_code == 200
        claimer_ret.json() == {"claimer_sas": ANY}
        assert (
            claimer_ret.json()["claimer_sas"]
            in greeter_ret.json()["candidate_claimer_sas"]
        )
        VARIABLES["claimer_sas"] = claimer_ret.json()["claimer_sas"]
    except AssertionError:
        logger.exception("[KO] Invite device claimer check trust")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device claimer check trust")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_wait_peer_trust)
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_check_trust)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    try:
        assert greeter_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Invite device greeter check trust")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device greeter check trust")

    try:
        assert claimer_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Invite device claimer wait peer trust")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device claimer wait peer trust")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(
            _claimer_finalize, password="ClaimDeviceNewP@ssw0rd"
        )
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_finalize)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    try:
        assert claimer_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Invite device claimer finalize")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device claimer finalize")

    try:
        assert greeter_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Invite device greeter finalize")
        logger.debug(r.json())
    else:
        logger.info("[OK] Invite device greeter finalize")

    # Try to log with the new device
    r = make_request(
        "POST",
        f"{resana_addr}/auth",
        data={
            "email": DEFAULT_EMAIL,
            "key": "ClaimDeviceNewP@ssw0rd",
            "organization": org_id,
        },
    )
    try:
        assert r.status_code == 200
        assert r.json()["token"] == ANY
    except AssertionError:
        logger.exception("[KO] Log in with new device")
        logger.debug(r.json())
    else:
        logger.info("[OK] Log in with new device")


def test_recovery(auth_token, resana_addr, org_id):
    VARIABLES = {}

    # Create a recovery device
    r = make_request(
        "POST", f"{resana_addr}/recovery/export", auth_token=auth_token, data={}
    )
    try:
        assert r.status_code == 200
        assert r.json() == {"file_content": ANY, "file_name": ANY, "passphrase": ANY}
        VARIABLES["recovery_device"] = base64.b64decode(
            r.json()["file_content"].encode()
        )
        VARIABLES["passphrase"] = r.json()["passphrase"]
    except AssertionError:
        print(r.raw)
        logger.exception("[KO] Create recovery device")
        logger.debug(r.json())
    else:
        logger.info("[OK] Create recovery device")

    # Import the recovery device
    r = make_request(
        "POST",
        f"{resana_addr}/recovery/import",
        data={
            "recovery_device_file_content": base64.b64encode(
                VARIABLES["recovery_device"]
            ).decode(),
            "recovery_device_passphrase": VARIABLES["passphrase"],
            "new_device_key": "RecoveryNewP@ssw0rd",
        },
    )
    try:
        assert r.status_code == 200
    except AssertionError:
        logger.exception("[KO] Import recovery device")
        logger.debug(r.json())
    else:
        logger.info("[OK] Import recovery device")

    # Try to log with the new device
    r = make_request(
        "POST",
        f"{resana_addr}/auth",
        data={
            "email": DEFAULT_EMAIL,
            "key": "RecoveryNewP@ssw0rd",
            "organization": org_id,
        },
    )
    try:
        assert r.status_code == 200
        assert r.json()["token"] == ANY
    except AssertionError:
        logger.exception("[KO] Log in with new device")
        logger.debug(r.json())
    else:
        logger.info("[OK] Log in with new device")


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
            data={
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
        data={
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
        required=True,
        help="Parsec backend address",
    )
    parser.add_argument(
        "-o",
        "--org",
        type=str,
        required=True,
        help="Organization ID",
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Adds extra debugging info"
    )
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
    parser.add_argument(
        "--skip-recovery", action="store_true", help="Skip the recovery API"
    )

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logging.getLogger("urllib3").setLevel(logging.WARNING)

    parsed = urllib.parse.urlparse(args.parsec)
    bootstrap_addr = f"{parsed.scheme}://{parsed.netloc}/{args.org}?{parsed.query}&action=bootstrap_organization"

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
