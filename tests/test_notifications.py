from datetime import datetime, timedelta, timezone

from app.models.notification import Notification, NotificationType
from app.models.task import Task
from app.workers.tasks import check_and_notify_overdue_tasks


def test_reassignment_notification_trigger(client, auth_headers, auth_headers_user_2, test_user_2):
    # User 1 creates project & task
    p = client.post(
        "/api/v1/projects", json={"name": "Reassignment Proj"}, headers=auth_headers
    ).json()
    project_id = p["id"]

    t = client.post(
        f"/api/v1/projects/{project_id}/tasks", json={"title": "Urgent Task"}, headers=auth_headers
    ).json()
    task_id = t["id"]

    # Assign to User 2
    client.patch(
        f"/api/v1/tasks/{task_id}", json={"assignee_id": test_user_2.id}, headers=auth_headers
    )

    # User 2 checks notifications
    res_notif = client.get("/api/v1/notifications", headers=auth_headers_user_2)
    assert res_notif.status_code == 200
    data = res_notif.json()
    assert data["total"] >= 1
    assert data["unread_count"] >= 1
    notif = data["items"][0]
    assert notif["notification_type"] == NotificationType.TASK_REASSIGNED.value
    assert "assigned" in notif["message"].lower()
    assert notif["task_id"] == task_id


def test_overdue_tasks_background_job(client, auth_headers, test_user, db_session):
    # Create project
    p = client.post(
        "/api/v1/projects", json={"name": "Overdue Inspection Project"}, headers=auth_headers
    ).json()
    project_id = p["id"]

    now = datetime.now(timezone.utc)
    past_due = now - timedelta(days=2)
    future_due = now + timedelta(days=2)

    # 1. Overdue & TODO -> Should notify
    t1 = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "title": "Overdue Task",
            "due_date": past_due.isoformat(),
            "status": "todo",
            "assignee_id": test_user.id,
        },
        headers=auth_headers,
    ).json()

    # 2. Overdue & DONE -> Should NOT notify
    client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Done Task", "due_date": past_due.isoformat(), "status": "done"},
        headers=auth_headers,
    ).json()

    # 3. Future & TODO -> Should NOT notify
    client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={"title": "Future Task", "due_date": future_due.isoformat(), "status": "todo"},
        headers=auth_headers,
    ).json()

    # Clear any previous notifications for clean test
    db_session.query(Notification).filter(Notification.user_id == test_user.id).delete()
    db_session.commit()

    # Run background overdue inspection
    result = check_and_notify_overdue_tasks()
    assert result["status"] == "success"
    assert result["overdue_tasks_notified"] == 1

    # Verify notification created
    notifs = db_session.query(Notification).filter(Notification.user_id == test_user.id).all()
    assert len(notifs) == 1
    assert notifs[0].notification_type == NotificationType.TASK_OVERDUE.value
    assert notifs[0].task_id == t1["id"]
    assert "overdue" in notifs[0].title.lower()

    # Verify task.is_overdue_notified is now True
    task1_db = db_session.query(Task).filter(Task.id == t1["id"]).first()
    assert task1_db.is_overdue_notified is True

    # Re-running background job should NOT duplicate notifications
    result2 = check_and_notify_overdue_tasks()
    assert result2["overdue_tasks_notified"] == 0
    notifs_after = db_session.query(Notification).filter(Notification.user_id == test_user.id).all()
    assert len(notifs_after) == 1


def test_notifications_mark_read_and_authorization(
    client, auth_headers, auth_headers_user_2, test_user, test_user_2, db_session
):
    # Create notification for User 1
    notif = Notification(
        user_id=test_user.id,
        notification_type="task_alert",
        title="Alert 1",
        message="Important alert message",
        is_read=False,
    )
    db_session.add(notif)
    db_session.commit()
    db_session.refresh(notif)

    # User 2 tries to mark User 1's notification as read -> 403 Forbidden
    res_forbidden = client.patch(
        f"/api/v1/notifications/{notif.id}/read",
        json={"is_read": True},
        headers=auth_headers_user_2,
    )
    assert res_forbidden.status_code == 403

    # User 1 marks it as read -> 200 OK
    res_ok = client.patch(
        f"/api/v1/notifications/{notif.id}/read", json={"is_read": True}, headers=auth_headers
    )
    assert res_ok.status_code == 200
    assert res_ok.json()["is_read"] is True

    # User 1 marks all as read
    res_all = client.post("/api/v1/notifications/mark-all-read", headers=auth_headers)
    assert res_all.status_code == 200
