"""End-to-End Live Verification Script for TaskFlow.

Tests all core API endpoints, authentication, projects, tasks, caching,
notifications, and operational endpoints (/health, /metrics).
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine
from app.workers.celery_app import celery_app
import fakeredis
import app.core.cache as cache_module

# Configure Celery for in-process synchronous execution during e2e testing
celery_app.conf.update(
    task_always_eager=True,
    task_eager_propagates=True,
    broker_url="memory://",
    result_backend="cache+memory://",
)

# Provide in-memory Redis for local test execution
_fake_redis = fakeredis.FakeRedis(decode_responses=True)
cache_module.get_redis_client = lambda: _fake_redis
cache_module._redis_client = _fake_redis


def run_e2e_tests():
    print("=" * 60)
    print(" TASKFLOW END-TO-END VERIFICATION")
    print("=" * 60)

    # Initialize tables
    print("[1/9] Ensuring database tables exist...")
    Base.metadata.create_all(bind=engine)
    print(" -> Tables verified.")

    client = TestClient(app)

    # 1. Operational Endpoints
    print("\n[2/9] Testing Operational Endpoints...")
    res_root = client.get("/")
    assert res_root.status_code == 200, f"Root failed: {res_root.text}"
    print(f" -> GET /: {res_root.json()['message']}")

    res_health = client.get("/health")
    assert res_health.status_code == 200, f"Health check failed: {res_health.text}"
    health_data = res_health.json()
    print(f" -> GET /health: status={health_data['status']}, components={list(health_data['components'].keys())}")

    res_metrics = client.get("/metrics")
    assert res_metrics.status_code == 200, "Metrics endpoint failed"
    assert "taskflow_http_requests_total" in res_metrics.text
    print(" -> GET /metrics: Prometheus metrics format confirmed.")

    # 2. Authentication Flow
    print("\n[3/9] Testing User Signup & Login...")
    user1_email = "shivam.dev@example.com"
    user1_username = "shivam_dev"
    user1_pass = "SecurePass123!"

    signup_res = client.post("/api/v1/auth/signup", json={
        "email": user1_email,
        "username": user1_username,
        "password": user1_pass
    })
    # Either 201 or 400 if already exists from earlier run
    if signup_res.status_code == 201:
        print(f" -> POST /api/v1/auth/signup: Created user ID {signup_res.json()['id']}")
    else:
        print(" -> User already exists, proceeding to login.")

    # Login
    login_res = client.post("/api/v1/auth/login", json={
        "username_or_email": user1_email,
        "password": user1_pass
    })
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token_data = login_res.json()
    access_token = token_data["access_token"]
    user1_id = token_data["user"]["id"]
    headers = {"Authorization": f"Bearer {access_token}"}
    print(f" -> POST /api/v1/auth/login: Success! Token acquired (expires_in={token_data['expires_in']}s)")

    # Current User Profile
    me_res = client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == user1_email
    print(f" -> GET /api/v1/auth/me: Verified email={me_res.json()['email']}")

    # 3. Create Second User for Assignee / Authorization tests
    print("\n[4/9] Setting up second user for collaboration testing...")
    user2_email = "colleague@example.com"
    client.post("/api/v1/auth/signup", json={
        "email": user2_email,
        "username": "colleague_user",
        "password": "Password123!"
    })
    login_res2 = client.post("/api/v1/auth/login", json={
        "username_or_email": user2_email,
        "password": "Password123!"
    })
    token2 = login_res2.json()["access_token"]
    user2_id = login_res2.json()["user"]["id"]
    headers_user2 = {"Authorization": f"Bearer {token2}"}
    print(f" -> User 2 setup complete (ID {user2_id}).")

    # 4. Projects CRUD
    print("\n[5/9] Testing Projects CRUD & Authorization...")
    proj_res = client.post("/api/v1/projects", json={
        "name": "TaskFlow Core Platform",
        "description": "Production task management and notifications system"
    }, headers=headers)
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]
    print(f" -> POST /api/v1/projects: Created project ID {project_id}")

    # List Projects
    list_proj = client.get("/api/v1/projects", headers=headers)
    assert list_proj.status_code == 200
    print(f" -> GET /api/v1/projects: Total projects = {list_proj.json()['total']}")

    # Authorization Check: User 2 trying to access User 1's project -> 403
    forbidden_proj = client.get(f"/api/v1/projects/{project_id}", headers=headers_user2)
    assert forbidden_proj.status_code == 403, f"Expected 403, got {forbidden_proj.status_code}"
    print(" -> Authorization boundary verified: User 2 cannot access User 1's project (403 Forbidden).")

    # 5. Tasks CRUD
    print("\n[6/9] Testing Tasks CRUD...")
    task_res = client.post(f"/api/v1/projects/{project_id}/tasks", json={
        "title": "Set up Prometheus and Redis Cache",
        "description": "Ensure zero stale reads with versioned keys",
        "status": "todo",
        "due_date": "2026-11-01T12:00:00Z"
    }, headers=headers)
    assert task_res.status_code == 201
    task_id = task_res.json()["id"]
    print(f" -> POST /api/v1/projects/{project_id}/tasks: Created task ID {task_id}")

    # 6. Search, Filtering, and Cache Invalidation
    print("\n[7/9] Testing Search, Filtering & Redis Cache Invalidation...")
    # First search
    search1 = client.get("/api/v1/tasks?status=todo", headers=headers)
    assert search1.status_code == 200
    assert any(t["id"] == task_id for t in search1.json()["items"])
    print(f" -> GET /api/v1/tasks?status=todo: Found {search1.json()['total']} matching tasks.")

    # Reassign task to User 2 and update status to in_progress
    patch_res = client.patch(f"/api/v1/tasks/{task_id}", json={
        "status": "in_progress",
        "assignee_id": user2_id
    }, headers=headers)
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "in_progress"
    print(f" -> PATCH /api/v1/tasks/{task_id}: Updated status=in_progress, assignee={user2_id}")

    # Subsequent search: MUST reflect status change immediately (no stale read)
    search2 = client.get("/api/v1/tasks?status=in_progress", headers=headers)
    assert search2.status_code == 200
    assert any(t["id"] == task_id for t in search2.json()["items"]), "Stale read detected!"
    print(" -> Verified immediate cache invalidation: Task reflected in status=in_progress query.")

    # 7. Notifications Verification
    print("\n[8/9] Testing Notifications Delivery & Read Status...")
    notif_res = client.get("/api/v1/notifications", headers=headers_user2)
    assert notif_res.status_code == 200
    notif_data = notif_res.json()
    print(f" -> GET /api/v1/notifications (User 2): Total notifications = {notif_data['total']}, unread = {notif_data['unread_count']}")
    if notif_data["total"] > 0:
        notif_id = notif_data["items"][0]["id"]
        # Mark read
        read_res = client.patch(f"/api/v1/notifications/{notif_id}/read", json={"is_read": True}, headers=headers_user2)
        assert read_res.status_code == 200
        assert read_res.json()["is_read"] is True
        print(f" -> PATCH /api/v1/notifications/{notif_id}/read: Marked as read successfully.")

    # 8. Clean Up
    print("\n[9/9] Testing Deletion & Cleanup...")
    del_task = client.delete(f"/api/v1/tasks/{task_id}", headers=headers)
    assert del_task.status_code == 204
    print(f" -> DELETE /api/v1/tasks/{task_id}: Task deleted (204 No Content).")

    del_proj = client.delete(f"/api/v1/projects/{project_id}", headers=headers)
    assert del_proj.status_code == 204
    print(f" -> DELETE /api/v1/projects/{project_id}: Project deleted (204 No Content).")

    print("\n" + "=" * 60)
    print(" ALL END-TO-END CHECKS COMPLETED SUCCESSFULLY! ")
    print("=" * 60)


if __name__ == "__main__":
    try:
        run_e2e_tests()
    except Exception as e:
        print(f"\n[ERROR] E2E verification failed: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
