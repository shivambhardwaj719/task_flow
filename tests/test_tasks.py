from datetime import datetime, timedelta, timezone


def test_create_task_success(client, auth_headers):
    # Create project first
    proj_res = client.post("/api/v1/projects", json={"name": "Taskflow App"}, headers=auth_headers)
    project_id = proj_res.json()["id"]

    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    task_payload = {
        "title": "Implement Redis Cache Invalidation",
        "description": "Ensure zero stale reads with versioned keys",
        "status": "todo",
        "due_date": due,
    }
    response = client.post(
        f"/api/v1/projects/{project_id}/tasks", json=task_payload, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Implement Redis Cache Invalidation"
    assert data["status"] == "todo"
    assert data["project_id"] == project_id
    assert "id" in data


def test_task_authorization_boundary_create(client, auth_headers, auth_headers_user_2):
    # User 1 creates project
    proj_res = client.post(
        "/api/v1/projects", json={"name": "User 1 Secret Project"}, headers=auth_headers
    )
    project_id = proj_res.json()["id"]

    # User 2 attempts to create a task in User 1's project -> 403 Forbidden
    task_payload = {"title": "Unauthorized Task", "status": "todo"}
    response = client.post(
        f"/api/v1/projects/{project_id}/tasks", json=task_payload, headers=auth_headers_user_2
    )
    assert response.status_code == 403
    assert (
        "cannot create tasks" in response.json()["detail"].lower()
        or "forbidden" in response.json()["detail"].lower()
    )


def test_task_authorization_boundary_view_and_update(client, auth_headers, auth_headers_user_2):
    # User 1 creates project & task
    proj_res = client.post(
        "/api/v1/projects", json={"name": "Private Project"}, headers=auth_headers
    )
    project_id = proj_res.json()["id"]

    task_res = client.post(
        f"/api/v1/projects/{project_id}/tasks", json={"title": "Private Task"}, headers=auth_headers
    )
    task_id = task_res.json()["id"]

    # User 2 attempts to view -> 403 Forbidden
    res_get = client.get(f"/api/v1/tasks/{task_id}", headers=auth_headers_user_2)
    assert res_get.status_code == 403

    # User 2 attempts to update status -> 403 Forbidden
    res_patch = client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "done"}, headers=auth_headers_user_2
    )
    assert res_patch.status_code == 403

    # User 1 updates status -> 200 OK
    res_owner_patch = client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "in_progress"}, headers=auth_headers
    )
    assert res_owner_patch.status_code == 200
    assert res_owner_patch.json()["status"] == "in_progress"


def test_task_reassignment(client, auth_headers, test_user_2):
    # User 1 creates project & task
    proj_res = client.post(
        "/api/v1/projects", json={"name": "Collab Project"}, headers=auth_headers
    )
    project_id = proj_res.json()["id"]

    task_res = client.post(
        f"/api/v1/projects/{project_id}/tasks", json={"title": "Collab Task"}, headers=auth_headers
    )
    task_id = task_res.json()["id"]

    # Assign task to test_user_2
    res_assign = client.patch(
        f"/api/v1/tasks/{task_id}", json={"assignee_id": test_user_2.id}, headers=auth_headers
    )
    assert res_assign.status_code == 200
    assert res_assign.json()["assignee_id"] == test_user_2.id


def test_task_deletion_boundary(client, auth_headers, auth_headers_user_2):
    proj_res = client.post(
        "/api/v1/projects", json={"name": "Project for Delete"}, headers=auth_headers
    )
    project_id = proj_res.json()["id"]

    task_res = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "To be deleted"},
        headers=auth_headers,
    )
    task_id = task_res.json()["id"]

    # User 2 cannot delete User 1's task -> 403
    res_del_forbidden = client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers_user_2)
    assert res_del_forbidden.status_code == 403

    # User 1 deletes task -> 204
    res_del = client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert res_del.status_code == 204
