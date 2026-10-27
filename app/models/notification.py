import enum

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class NotificationType(str, enum.Enum):
    TASK_OVERDUE = "task_overdue"
    TASK_REASSIGNED = "task_reassigned"
    TASK_STATUS_CHANGED = "task_status_changed"


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_id = Column(Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True, index=True)
    notification_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    user = relationship("User", back_populates="notifications")
    task = relationship("Task", back_populates="notifications")
