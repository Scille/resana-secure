import argparse
from unittest.mock import ANY
import logging
import requests
import base64
import concurrent.futures
import time

from parsec.core.types import BackendOrganizationBootstrapAddr


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
    else:
        logger.info("[OK] Make sure the file was deleted")


def test_invitations(auth_token, resana_addr):
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

    def _claimer_finalize():
        return make_request(
            "POST",
            f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/4-finalize",
            data={"key": "P@ssw0rd"},
        )

    # List invitations
    r = make_request("GET", f"{resana_addr}/invitations", auth_token=auth_token)
    try:
        assert r.status_code == 200
        assert r.json() == {"device": None, "users": []}
    except AssertionError:
        logger.exception("[KO] Listing invitations")
    else:
        logger.info("[OK] Listing invitations")

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
        VARIABLES["token"] = r.json()["token"]
    except AssertionError:
        logger.exception("[KO] Inviting user")
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
                    "token": ANY,
                }
            ],
        }
    except AssertionError:
        logger.exception("[KO] Checking if the new invitation appears")
    else:
        logger.info("[OK] Checking if the new invitation appears")

    # Claimer retrieve info (and not retrEIve)
    r = make_request(
        "POST",
        f"{resana_addr}/invitations/{VARIABLES['token']}/claimer/0-retreive-info",
    )
    try:
        assert r.status_code == 200
        assert r.json() == {"greeter_email": DEFAULT_EMAIL, "type": "user"}
    except AssertionError:
        logger.exception("[KO] Claimer retrieve info")
    else:
        logger.info("[OK] Claimer retrieve info")

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
        logger.exception("[KO] Greeter wait")
    else:
        logger.info("[OK] Greeter wait")

    try:
        assert claimer_ret.status_code == 200
        assert claimer_ret.json() == {"candidate_greeter_sas": [ANY, ANY, ANY, ANY]}
        assert (
            greeter_ret.json()["greeter_sas"]
            in claimer_ret.json()["candidate_greeter_sas"]
        )
        VARIABLES["greeter_sas"] = greeter_ret.json()["greeter_sas"]
    except AssertionError:
        logger.exception("[KO] Claimer wait")
    else:
        logger.info("[OK] Claimer wait")

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
        logger.exception("[KO] Greeter wait peer trust")
    else:
        logger.info("[OK] Greeter wait peer trust")

    try:
        assert claimer_ret.status_code == 200
        claimer_ret.json() == {"claimer_sas": ANY}
        assert (
            claimer_ret.json()["claimer_sas"]
            in greeter_ret.json()["candidate_claimer_sas"]
        )
        VARIABLES["claimer_sas"] = claimer_ret.json()["claimer_sas"]
    except AssertionError:
        logger.exception("[KO] Claimer check trust")
    else:
        logger.info("[OK] Claimer check trust")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_wait_peer_trust)
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_check_trust)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    try:
        assert greeter_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Greeter check trust")
    else:
        logger.info("[OK] Greeter check trust")

    try:
        assert claimer_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Claimer wait peer trust")
    else:
        logger.info("[OK] Claimer wait peer trust")

    with concurrent.futures.ThreadPoolExecutor() as executor:
        claimer_future = executor.submit(_claimer_finalize)
        time.sleep(1.0)
        greeter_future = executor.submit(_greeter_finalize)
        greeter_ret = greeter_future.result()
        claimer_ret = claimer_future.result()

    try:
        assert claimer_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Claimer finalize")
    else:
        logger.info("[OK] Claimer finalize")

    try:
        assert greeter_ret.status_code == 200
    except AssertionError:
        logger.exception("[KO] Greeter finalize")
    else:
        logger.info("[OK] Greeter finalize")

    r = make_request("GET", f"{resana_addr}/humans", auth_token=auth_token)
    try:
        assert r.status_code == 200
        assert r.json()["total"] == 2
        assert any(
            u["human_handle"]["email"] == INVITEE_EMAIL for u in r.json()["users"]
        )
    except AssertionError:
        logger.exception("[KO] List users to see new user")
    else:
        logger.info("[OK] List users to see new user")


def main(
    resana_addr,
    bootstrap_addr,
    skip_bootstrap=False,
    skip_humans=False,
    skip_workspaces=False,
    skip_files=False,
    skip_invite=False,
):
    """Test all Resana routes.

    The script needs the URL to a running Resana instance and the bootstrap
    address from Parsec (obtain with `parsec core create_organization`).
    """

    if not skip_bootstrap:
        logger.info("Bootstraping")
        r = make_request(
            "POST",
            f"{resana_addr}/organization/bootstrap",
            data={
                "organization_url": bootstrap_addr.to_url(),
                "email": DEFAULT_EMAIL,
                "key": DEFAULT_PASSWORD,
            },
        )
        assert r.status_code == 200

    logger.info("Authenticating...")
    r = requests.post(
        f"{resana_addr}/auth",
        json={
            "email": DEFAULT_EMAIL,
            "key": DEFAULT_PASSWORD,
            "organization": bootstrap_addr.organization_id.str,
        },
    )
    assert r.status_code == 200
    auth_token = r.json()["token"]

    # Start with invitation, so we can have another user
    if not skip_invite:
        test_invitations(auth_token, resana_addr)
    # # Continue with workspaces, share/unshare
    if not skip_workspaces:
        test_workspaces(auth_token, resana_addr)
    # Upload, rename, delete files
    if not skip_files:
        test_files(auth_token, resana_addr)
    # End with humans to test the revoke
    if not skip_humans:
        test_humans(auth_token, resana_addr)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=main.__doc__)

    parser.add_argument(
        "-r",
        "--resana",
        type=str,
        default="http://127.0.0.1:5775",
        required=True,
        help="Resana addr",
    )
    parser.add_argument(
        "-b",
        "--bootstrap",
        type=lambda s: BackendOrganizationBootstrapAddr.from_url(s),
        required=True,
        help="Bootstrap addr",
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
        "--skip-invite",
        action="store_true",
        help="Skip invite API (this may have an impact on other APIs)",
    )

    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    logging.getLogger("urllib3").setLevel(logging.WARNING)

    main(
        args.resana,
        args.bootstrap,
        skip_bootstrap=args.skip_bootstrap,
        skip_humans=args.skip_humans,
        skip_workspaces=args.skip_workspaces,
        skip_files=args.skip_files,
        skip_invite=args.skip_invite,
    )
