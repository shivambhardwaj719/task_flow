from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class NotificationOut(BaseModel):
    id: int
    user_id: int
    task_id: Optional[int] = None
    notification_type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationUpdate(BaseModel):
    is_read: bool = Field(True, description="Mark notification as read or unread")


class PaginatedNotifications(BaseModel):
    items: List[NotificationOut]
    total: int
    unread_count: int
    page: int
    page_size: int
    total_pages: int
