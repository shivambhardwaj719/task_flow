from celery import Celery
from app.config import settings

celery_app = Celery(
    "taskflow",
    broker=settings.get_celery_broker_url(),
    backend=settings.get_celery_result_backend(),
    include=["app.workers.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
    beat_schedule={
        "check-overdue-tasks-periodically": {
            "task": "app.workers.tasks.check_and_notify_overdue_tasks",
            "schedule": float(settings.OVERDUE_TASK_CHECK_INTERVAL_SECONDS),
        },
    }
)

if settings.ENVIRONMENT == "testing":
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
