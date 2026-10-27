def test_create_project(client, auth_headers):
    payload = {
        "name": "Backend Engineering Project",
        "description": "Production-ready TaskFlow API",
    }
    response = client.post("/api/v1/projects", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Backend Engineering Project"
    assert data["description"] == "Production-ready TaskFlow API"
    assert "id" in data
    assert "owner_id" in data


def test_list_projects_isolation(client, auth_headers, auth_headers_user_2):
    # User 1 creates a project
    client.post("/api/v1/projects", json={"name": "User1 Project"}, headers=auth_headers)

    # User 2 creates a project
    client.post("/api/v1/projects", json={"name": "User2 Project"}, headers=auth_headers_user_2)

    # User 1 lists projects: should only see User 1's project
    res_1 = client.get("/api/v1/projects", headers=auth_headers)
    assert res_1.status_code == 200
    items_1 = res_1.json()["items"]
    assert len(items_1) == 1
    assert items_1[0]["name"] == "User1 Project"

    # User 2 lists projects: should only see User 2's project
    res_2 = client.get("/api/v1/projects", headers=auth_headers_user_2)
    assert res_2.status_code == 200
    items_2 = res_2.json()["items"]
    assert len(items_2) == 1
    assert items_2[0]["name"] == "User2 Project"


def test_project_authorization_boundary_view(client, auth_headers, auth_headers_user_2):
    # User 1 creates project
    res = client.post("/api/v1/projects", json={"name": "Secret Project"}, headers=auth_headers)
    project_id = res.json()["id"]

    # User 2 attempts to view User 1's project -> 403 Forbidden
    res_forbidden = client.get(f"/api/v1/projects/{project_id}", headers=auth_headers_user_2)
    assert res_forbidden.status_code == 403
    assert (
        "permission" in res_forbidden.json()["detail"].lower()
        or "forbidden" in res_forbidden.json()["detail"].lower()
    )


def test_project_authorization_boundary_update(client, auth_headers, auth_headers_user_2):
    # User 1 creates project
    res = client.post("/api/v1/projects", json={"name": "Original Name"}, headers=auth_headers)
    project_id = res.json()["id"]

    # User 2 attempts to update User 1's project -> 403 Forbidden
    res_forbidden = client.patch(
        f"/api/v1/projects/{project_id}", json={"name": "Hacked Name"}, headers=auth_headers_user_2
    )
    assert res_forbidden.status_code == 403


def test_project_authorization_boundary_delete(client, auth_headers, auth_headers_user_2):
    # User 1 creates project
    res = client.post("/api/v1/projects", json={"name": "Important Project"}, headers=auth_headers)
    project_id = res.json()["id"]

    # User 2 attempts to delete User 1's project -> 403 Forbidden
    res_forbidden = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers_user_2)
    assert res_forbidden.status_code == 403

    # User 1 successfully deletes their project -> 204 No Content
    res_delete = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert res_delete.status_code == 204
