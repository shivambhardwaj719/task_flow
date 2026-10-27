from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class TaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Task title")
    description: Optional[str] = Field(None, description="Detailed task description")
    status: TaskStatus = Field(
        default=TaskStatus.TODO, description="Task status: todo, in_progress, done"
    )
    due_date: Optional[datetime] = Field(None, description="Task due date/time with UTC timezone")


class TaskCreate(TaskBase):
    assignee_id: Optional[int] = Field(None, description="User ID of the assignee")


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    assignee_id: Optional[int] = None
    due_date: Optional[datetime] = None


class TaskOut(TaskBase):
    id: int
    project_id: int
    assignee_id: Optional[int] = None
    is_overdue_notified: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedTasks(BaseModel):
    items: List[TaskOut]
    total: int
    page: int
    page_size: int
    total_pages: int
