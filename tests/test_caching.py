from datetime import datetime, timezone, timedelta
import pytest
from app.core.cache import TaskCacheManager, get_redis_client


def test_filter_tasks_by_status(client, auth_headers):
    # Create project
    p = client.post("/api/v1/projects", json={"name": "Filter Test Project"}, headers=auth_headers).json()
    project_id = p["id"]

    # Create 3 tasks with different statuses
    client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "Task 1", "status": "todo"}, headers=auth_headers)
    client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "Task 2", "status": "in_progress"}, headers=auth_headers)
    client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "Task 3", "status": "done"}, headers=auth_headers)

    # Filter by todo
    res_todo = client.get("/api/v1/tasks?status=todo", headers=auth_headers)
    assert res_todo.status_code == 200
    items = res_todo.json()["items"]
    assert all(t["status"] == "todo" for t in items)
    assert any(t["title"] == "Task 1" for t in items)

    # Filter by done
    res_done = client.get("/api/v1/tasks?status=done", headers=auth_headers)
    assert res_done.status_code == 200
    items = res_done.json()["items"]
    assert all(t["status"] == "done" for t in items)
    assert any(t["title"] == "Task 3" for t in items)


def test_filter_tasks_by_assignee(client, auth_headers, test_user_2):
    p = client.post("/api/v1/projects", json={"name": "Assignee Filter Proj"}, headers=auth_headers).json()
    project_id = p["id"]

    client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "Unassigned Task"}, headers=auth_headers)
    client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "Assigned Task", "assignee_id": test_user_2.id}, headers=auth_headers)

    res = client.get(f"/api/v1/tasks?assignee_id={test_user_2.id}", headers=auth_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Assigned Task"
    assert items[0]["assignee_id"] == test_user_2.id


def test_filter_tasks_by_due_date_range(client, auth_headers):
    p = client.post("/api/v1/projects", json={"name": "Date Range Project"}, headers=auth_headers).json()
    project_id = p["id"]

    now = datetime.now(timezone.utc)
    t1 = now + timedelta(days=1)
    t2 = now + timedelta(days=5)
    t3 = now + timedelta(days=10)

    client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "Task In Range 1", "due_date": t1.isoformat()}, headers=auth_headers)
    client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "Task In Range 2", "due_date": t2.isoformat()}, headers=auth_headers)
    client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "Task Far Out", "due_date": t3.isoformat()}, headers=auth_headers)

    from_date = (now + timedelta(hours=12)).isoformat()
    to_date = (now + timedelta(days=6)).isoformat()

    res = client.get(f"/api/v1/tasks?due_date_from={from_date}&due_date_to={to_date}", headers=auth_headers)
    assert res.status_code == 200
    items = res.json()["items"]
    titles = [t["title"] for t in items]
    assert "Task In Range 1" in titles
    assert "Task In Range 2" in titles
    assert "Task Far Out" not in titles


def test_pagination(client, auth_headers):
    p = client.post("/api/v1/projects", json={"name": "Pagination Project"}, headers=auth_headers).json()
    project_id = p["id"]

    for i in range(15):
        client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": f"Task #{i+1}"}, headers=auth_headers)

    # Page 1, size 5
    res_p1 = client.get(f"/api/v1/tasks?project_id={project_id}&page=1&page_size=5", headers=auth_headers)
    assert res_p1.status_code == 200
    data1 = res_p1.json()
    assert len(data1["items"]) == 5
    assert data1["total"] == 15
    assert data1["total_pages"] == 3
    assert data1["page"] == 1

    # Page 2, size 5
    res_p2 = client.get(f"/api/v1/tasks?project_id={project_id}&page=2&page_size=5", headers=auth_headers)
    assert res_p2.status_code == 200
    data2 = res_p2.json()
    assert len(data2["items"]) == 5
    assert data2["page"] == 2


def test_cache_hit_and_invalidation_on_status_change(client, auth_headers):
    """Critical Test: Verify cache is populated on first read, and invalidated on status change."""
    p = client.post("/api/v1/projects", json={"name": "Cache Test Project"}, headers=auth_headers).json()
    project_id = p["id"]

    task = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Cache Invalidation Task", "status": "todo"},
        headers=auth_headers
    ).json()
    task_id = task["id"]

    # First read: Cache Miss -> populates cache
    read1 = client.get(f"/api/v1/tasks?project_id={project_id}", headers=auth_headers)
    assert read1.status_code == 200
    assert read1.json()["items"][0]["status"] == "todo"

    # Mutate task status: todo -> done
    patch_res = client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
        headers=auth_headers
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "done"

    # Second read: MUST return "done", never stale "todo"
    read2 = client.get(f"/api/v1/tasks?project_id={project_id}", headers=auth_headers)
    assert read2.status_code == 200
    assert read2.json()["items"][0]["status"] == "done", "BUG: Stale read detected after task status change!"


def test_cache_invalidation_on_create_and_delete(client, auth_headers):
    """Verify cache invalidation when tasks are created or deleted."""
    p = client.post("/api/v1/projects", json={"name": "Cache Mutation Project"}, headers=auth_headers).json()
    project_id = p["id"]

    # Initial query (empty)
    read_empty = client.get(f"/api/v1/tasks?project_id={project_id}", headers=auth_headers)
    assert read_empty.json()["total"] == 0

    # Create task
    t = client.post(f"/api/v1/projects/{project_id}/tasks", json={"title": "New Task"}, headers=auth_headers).json()
    task_id = t["id"]

    # Immediate read must show total=1 (no stale empty read)
    read_after_create = client.get(f"/api/v1/tasks?project_id={project_id}", headers=auth_headers)
    assert read_after_create.json()["total"] == 1

    # Delete task
    del_res = client.delete(f"/api/v1/tasks/{task_id}", headers=auth_headers)
    assert del_res.status_code == 204

    # Immediate read must show total=0 (no stale read)
    read_after_del = client.get(f"/api/v1/tasks?project_id={project_id}", headers=auth_headers)
    assert read_after_del.json()["total"] == 0
