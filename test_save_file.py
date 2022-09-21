import requests
import trio


def f():
    r = requests.post(
        f"http://localhost:5775/auth",
        json={
            "email": "alice@example.com",
            "key": "test",
            "organization": "Org",
        },
    )
    assert r.status_code == 200
    auth_token = r.json()["token"]

    headers = {"Authorization": f"Bearer {auth_token}"}

    r = requests.get("http://localhost:5775/workspaces", headers=headers)
    assert r.status_code == 200
    print(r.json())
    workspace_id = r.json()["workspaces"][0]["id"]

    r = requests.get(f"http://localhost:5775/workspaces/{workspace_id}/folders", headers=headers)
    assert r.status_code == 200
    folder_id = r.json()["id"]

    r = requests.get(f"http://localhost:5775/workspaces/{workspace_id}/files/{folder_id}", headers=headers)
    assert r.status_code == 200
    file_id = r.json()["files"][0]["id"]

    r = requests.get(f"http://localhost:5775/workspaces/{workspace_id}/download/{file_id}", headers=headers)
    assert r.status_code == 200
    print(r.json())


f()
