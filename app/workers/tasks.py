import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.workers.celery_app import celery_app
from app.database import SessionLocal
from app.config import settings
from app.models.task import Task, TaskStatus
from app.models.project import Project
from app.models.user import User
from app.models.notification import Notification, NotificationType

logger = logging.getLogger("taskflow.worker")


def get_worker_db():
    """Returns database session, honoring testing environment if active."""
    if settings.ENVIRONMENT == "testing":
        try:
            from tests.conftest import TestingSessionLocal
            return TestingSessionLocal()
        except ImportError:
            pass
    return SessionLocal()


def simulate_delivery(channel: str, recipient: str, title: str, message: str) -> None:
    """Simulates real-world delivery (email/SMS/push) by logging structured notification payload."""
    log_line = (
        f"\n=======================================================\n"
        f"[SIMULATED NOTIFICATION DELIVERY]\n"
        f"Channel:   {channel.upper()}\n"
        f"Recipient: {recipient}\n"
        f"Title:     {title}\n"
        f"Body:      {message}\n"
        f"Timestamp: {datetime.now(timezone.utc).isoformat()}\n"
        f"======================================================="
    )
    logger.info(log_line)


@celery_app.task(name="app.workers.tasks.notify_task_reassigned")
def notify_task_reassigned(
    task_id: int,
    old_assignee_id: Optional[int],
    new_assignee_id: Optional[int],
    actor_id: int
) -> dict:
    """Background task to record and dispatch reassignment notifications."""
    db: Session = get_worker_db()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.warning("Task %d not found for reassignment notification", task_id)
            return {"status": "task_not_found"}

        actor = db.query(User).filter(User.id == actor_id).first()
        actor_name = actor.username if actor else "A team member"

        # Notify new assignee
        if new_assignee_id and new_assignee_id != actor_id:
            new_assignee = db.query(User).filter(User.id == new_assignee_id).first()
            if new_assignee:
                title = f"Assigned to Task: {task.title}"
                body = f"You have been assigned to task '{task.title}' by {actor_name}."
                notification = Notification(
                    user_id=new_assignee.id,
                    task_id=task.id,
                    notification_type=NotificationType.TASK_REASSIGNED.value,
                    title=title,
                    message=body
                )
                db.add(notification)
                simulate_delivery("email", new_assignee.email, title, body)

        # Notify old assignee if unassigned
        if old_assignee_id and old_assignee_id != new_assignee_id and old_assignee_id != actor_id:
            old_assignee = db.query(User).filter(User.id == old_assignee_id).first()
            if old_assignee:
                title = f"Unassigned from Task: {task.title}"
                body = f"You were unassigned from task '{task.title}' by {actor_name}."
                notification = Notification(
                    user_id=old_assignee.id,
                    task_id=task.id,
                    notification_type=NotificationType.TASK_REASSIGNED.value,
                    title=title,
                    message=body
                )
                db.add(notification)
                simulate_delivery("email", old_assignee.email, title, body)

        db.commit()
        return {"status": "success", "task_id": task_id}
    except Exception as e:
        db.rollback()
        logger.error("Error creating reassignment notification: %s", str(e))
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.notify_task_status_changed")
def notify_task_status_changed(
    task_id: int,
    old_status: str,
    new_status: str,
    actor_id: int
) -> dict:
    """Background task to record and dispatch status change notifications."""
    db: Session = get_worker_db()
    try:
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            return {"status": "task_not_found"}

        project = db.query(Project).filter(Project.id == task.project_id).first()
        actor = db.query(User).filter(User.id == actor_id).first()
        actor_name = actor.username if actor else "A team member"

        # Determine whom to notify: assignee and project owner
        recipients_to_notify = set()
        if task.assignee_id and task.assignee_id != actor_id:
            recipients_to_notify.add(task.assignee_id)
        if project and project.owner_id != actor_id:
            recipients_to_notify.add(project.owner_id)

        title = f"Task Status Changed: {task.title}"
        body = f"Task '{task.title}' status was updated from '{old_status}' to '{new_status}' by {actor_name}."

        for recipient_id in recipients_to_notify:
            recipient = db.query(User).filter(User.id == recipient_id).first()
            if recipient:
                notification = Notification(
                    user_id=recipient.id,
                    task_id=task.id,
                    notification_type=NotificationType.TASK_STATUS_CHANGED.value,
                    title=title,
                    message=body
                )
                db.add(notification)
                simulate_delivery("email", recipient.email, title, body)

        db.commit()
        return {"status": "success", "task_id": task_id, "recipients_notified": len(recipients_to_notify)}
    except Exception as e:
        db.rollback()
        logger.error("Error creating status change notification: %s", str(e))
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


@celery_app.task(name="app.workers.tasks.check_and_notify_overdue_tasks")
def check_and_notify_overdue_tasks() -> dict:
    """Periodic Celery Beat task that identifies overdue tasks and dispatches notification records."""
    db: Session = get_worker_db()
    try:
        now = datetime.now(timezone.utc)
        # Find tasks where due_date < now, status is not done, and overdue notification hasn't been sent
        overdue_tasks = (
            db.query(Task)
            .filter(
                Task.due_date.isnot(None),
                Task.due_date < now,
                Task.status != TaskStatus.DONE.value,
                Task.is_overdue_notified.is_(False)
            )
            .all()
        )

        notified_count = 0
        for task in overdue_tasks:
            # Find recipient: assigned user or project owner
            recipient_id = task.assignee_id
            if not recipient_id:
                project = db.query(Project).filter(Project.id == task.project_id).first()
                if project:
                    recipient_id = project.owner_id

            if recipient_id:
                recipient = db.query(User).filter(User.id == recipient_id).first()
                if recipient:
                    due_date_str = task.due_date.strftime("%Y-%m-%d %H:%M UTC") if task.due_date else "N/A"
                    title = f"Task Overdue: {task.title}"
                    body = f"Task '{task.title}' is overdue! The due date was {due_date_str} and it has not been marked as done."
                    notification = Notification(
                        user_id=recipient.id,
                        task_id=task.id,
                        notification_type=NotificationType.TASK_OVERDUE.value,
                        title=title,
                        message=body
                    )
                    db.add(notification)
                    simulate_delivery("email", recipient.email, title, body)

            task.is_overdue_notified = True
            notified_count += 1

        db.commit()
        logger.info("Checked overdue tasks: %d overdue notifications generated.", notified_count)
        return {"status": "success", "overdue_tasks_notified": notified_count}
    except Exception as e:
        db.rollback()
        logger.error("Error during overdue task check: %s", str(e))
        return {"status": "error", "error": str(e)}
    finally:
        db.close()
