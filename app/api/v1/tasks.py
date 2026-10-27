import math
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_

from app.database import get_db
from app.models.user import User
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.schemas.task import TaskCreate, TaskUpdate, TaskOut, PaginatedTasks
from app.core.auth import get_current_user
from app.core.cache import TaskCacheManager
from app.workers.tasks import notify_task_reassigned, notify_task_status_changed

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Tasks"])


def dispatch_task_safely(celery_task, *args, **kwargs):
    """Safely dispatches a background task via Celery delay().
    
    If Celery broker/Redis is unavailable or in mock environment, logs gracefully without failing the HTTP request.
    """
    try:
        celery_task.delay(*args, **kwargs)
    except Exception as e:
        logger.warning("Could not dispatch Celery task %s asynchronously (%s). Executing directly or logging.", celery_task.__name__, str(e))
        try:
            celery_task(*args, **kwargs)
        except Exception as inner_e:
            logger.error("Direct fallback execution of %s failed: %s", celery_task.__name__, str(inner_e))


def get_task_with_authorization(task_id: int, user_id: int, db: Session, require_owner: bool = False) -> Task:
    """Helper to verify task existence and authorization boundaries.
    
    If require_owner is True, only the project owner may perform the action (e.g. deletion, reassignment).
    Otherwise, both project owner and assigned user have permission.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with ID {task_id} not found."
        )

    project = db.query(Project).filter(Project.id == task.project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated project not found."
        )

    is_owner = project.owner_id == user_id
    is_assignee = task.assignee_id == user_id

    if require_owner and not is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Only the project owner can perform this operation."
        )

    if not is_owner and not is_assignee:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have permission to view or edit this task."
        )

    return task


def parse_datetime_query(val: Optional[str]) -> Optional[datetime]:
    if not val:
        return None
    try:
        cleaned = val.replace(" ", "+")
        if cleaned.endswith("Z"):
            cleaned = cleaned[:-1] + "+00:00"
        return datetime.fromisoformat(cleaned)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid ISO datetime format: {val}"
        )


@router.get("/tasks", response_model=PaginatedTasks)
def search_and_filter_tasks(
    status_filter: Optional[TaskStatus] = Query(None, alias="status", description="Filter by status: todo, in_progress, done"),
    assignee_id: Optional[int] = Query(None, description="Filter by assignee user ID"),
    due_date_from: Optional[str] = Query(None, description="Filter tasks due on or after this UTC timestamp (ISO 8601)"),
    due_date_to: Optional[str] = Query(None, description="Filter tasks due on or before this UTC timestamp (ISO 8601)"),
    project_id: Optional[int] = Query(None, description="Filter by project ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Page size"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search and filter tasks with pagination and Redis caching.
    
    Stale reads are mathematically prevented through versioned cache keys.
    """
    dt_from = parse_datetime_query(due_date_from)
    dt_to = parse_datetime_query(due_date_to)

    # Build deterministic cache query parameters
    cache_params = {
        "status": status_filter.value if status_filter else None,
        "assignee_id": assignee_id,
        "due_date_from": dt_from.isoformat() if dt_from else None,
        "due_date_to": dt_to.isoformat() if dt_to else None,
        "project_id": project_id,
        "page": page,
        "page_size": page_size,
    }

    cache_key = TaskCacheManager.generate_cache_key(current_user.id, cache_params)
    cached_result = TaskCacheManager.get_cached_tasks(cache_key)
    if cached_result is not None:
        return cached_result

    # Base query: user can view tasks in projects they own OR tasks assigned to them
    user_project_ids = db.query(Project.id).filter(Project.owner_id == current_user.id).scalar_subquery()
    query = db.query(Task).filter(
        or_(
            Task.project_id.in_(user_project_ids),
            Task.assignee_id == current_user.id
        )
    )

    # Apply filters
    if project_id is not None:
        # Check authorization if explicitly querying a project
        proj = db.query(Project).filter(Project.id == project_id).first()
        if not proj or proj.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: You do not have access to this project's tasks."
            )
        query = query.filter(Task.project_id == project_id)

    if status_filter is not None:
        query = query.filter(Task.status == status_filter.value)

    if assignee_id is not None:
        query = query.filter(Task.assignee_id == assignee_id)

    if due_date_from is not None:
        query = query.filter(Task.due_date >= due_date_from)

    if due_date_to is not None:
        query = query.filter(Task.due_date <= due_date_to)

    total = query.count()
    offset = (page - 1) * page_size
    tasks = query.order_by(Task.due_date.asc().nulls_last(), Task.created_at.desc()).offset(offset).limit(page_size).all()
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    # Format result
    result_data = {
        "items": [
            {
                "id": t.id,
                "project_id": t.project_id,
                "title": t.title,
                "description": t.description,
                "status": t.status,
                "assignee_id": t.assignee_id,
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "is_overdue_notified": t.is_overdue_notified,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "updated_at": t.updated_at.isoformat() if t.updated_at else None,
            }
            for t in tasks
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }

    # Cache response in Redis
    TaskCacheManager.set_cached_tasks(cache_key, result_data)

    return result_data


@router.post("/projects/{project_id}/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    project_id: int,
    task_in: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new task within a project.
    
    Enforces authorization: only the project owner can create tasks in the project.
    Invalidates task cache to ensure zero stale reads.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found."
        )
    if project.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot create tasks in a project you do not own."
        )

    # Verify assignee if provided
    if task_in.assignee_id:
        assignee = db.query(User).filter(User.id == task_in.assignee_id).first()
        if not assignee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Assignee with ID {task_in.assignee_id} does not exist."
            )

    new_task = Task(
        project_id=project_id,
        title=task_in.title,
        description=task_in.description,
        status=task_in.status.value,
        assignee_id=task_in.assignee_id,
        due_date=task_in.due_date,
        is_overdue_notified=False
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    # Cache invalidation for creator and assignee
    users_to_invalidate = [current_user.id]
    if new_task.assignee_id:
        users_to_invalidate.append(new_task.assignee_id)
        # Dispatch background notification for assignment
        dispatch_task_safely(
            notify_task_reassigned,
            task_id=new_task.id,
            old_assignee_id=None,
            new_assignee_id=new_task.assignee_id,
            actor_id=current_user.id
        )

    TaskCacheManager.invalidate_user_tasks_cache(users_to_invalidate)

    return new_task


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Retrieve details of a single task.
    
    Enforces authorization: user must be project owner or assignee.
    """
    return get_task_with_authorization(task_id, current_user.id, db)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: int,
    task_in: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update task status, assignee, title, description, or due date.
    
    Invalidates Redis task caches immediately to guarantee zero stale reads.
    Dispatches asynchronous background notifications on status change or reassignment.
    """
    task = get_task_with_authorization(task_id, current_user.id, db, require_owner=False)
    project = db.query(Project).filter(Project.id == task.project_id).first()

    old_status = task.status
    old_assignee_id = task.assignee_id

    # If reassigning, verify new assignee exists and ensure user is project owner
    if task_in.assignee_id is not None and task_in.assignee_id != old_assignee_id:
        if project.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Only the project owner can reassign tasks."
            )
        new_assignee = db.query(User).filter(User.id == task_in.assignee_id).first()
        if not new_assignee:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Assignee with ID {task_in.assignee_id} does not exist."
            )
        task.assignee_id = task_in.assignee_id

    if task_in.title is not None:
        task.title = task_in.title
    if task_in.description is not None:
        task.description = task_in.description
    if task_in.due_date is not None:
        task.due_date = task_in.due_date
        # If due date changed to future, reset overdue notified
        if task.due_date and task.due_date > datetime.now(task.due_date.tzinfo):
            task.is_overdue_notified = False

    status_changed = False
    if task_in.status is not None and task_in.status.value != old_status:
        task.status = task_in.status.value
        status_changed = True
        if task.status == TaskStatus.DONE.value:
            task.is_overdue_notified = True

    db.commit()
    db.refresh(task)

    # Users whose caches must be invalidated immediately
    users_to_invalidate = [project.owner_id, current_user.id]
    if old_assignee_id:
        users_to_invalidate.append(old_assignee_id)
    if task.assignee_id:
        users_to_invalidate.append(task.assignee_id)

    # Invalidate cache
    TaskCacheManager.invalidate_user_tasks_cache(users_to_invalidate)

    # Background notifications
    if task_in.assignee_id is not None and task_in.assignee_id != old_assignee_id:
        dispatch_task_safely(
            notify_task_reassigned,
            task_id=task.id,
            old_assignee_id=old_assignee_id,
            new_assignee_id=task.assignee_id,
            actor_id=current_user.id
        )

    if status_changed:
        dispatch_task_safely(
            notify_task_status_changed,
            task_id=task.id,
            old_status=old_status,
            new_status=task.status,
            actor_id=current_user.id
        )

    return task


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a task.
    
    Enforces authorization: only the project owner can delete tasks.
    Immediately invalidates Redis caches.
    """
    task = get_task_with_authorization(task_id, current_user.id, db, require_owner=True)
    project = db.query(Project).filter(Project.id == task.project_id).first()
    
    users_to_invalidate = [project.owner_id]
    if task.assignee_id:
        users_to_invalidate.append(task.assignee_id)

    db.delete(task)
    db.commit()

    TaskCacheManager.invalidate_user_tasks_cache(users_to_invalidate)
    return None
