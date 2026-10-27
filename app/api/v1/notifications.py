import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import NotificationOut, NotificationUpdate, PaginatedNotifications

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("", response_model=PaginatedNotifications)
def list_notifications(
    is_read: Optional[bool] = Query(None, description="Filter by read status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve simulated notifications for the authenticated user."""
    base_query = db.query(Notification).filter(Notification.user_id == current_user.id)
    unread_count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .count()
    )

    query = base_query
    if is_read is not None:
        query = query.filter(Notification.is_read == is_read)

    total = query.count()
    offset = (page - 1) * page_size
    notifications = (
        query.order_by(Notification.created_at.desc()).offset(offset).limit(page_size).all()
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    return PaginatedNotifications(
        items=notifications,
        total=total,
        unread_count=unread_count,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.patch("/{notification_id}/read", response_model=NotificationOut)
def mark_notification_as_read(
    notification_id: int,
    update_in: NotificationUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a notification as read or unread.

    Enforces authorization: only the notification recipient can update it.
    """
    notification = db.query(Notification).filter(Notification.id == notification_id).first()
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification with ID {notification_id} not found.",
        )

    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You cannot modify notifications belonging to another user.",
        )

    notification.is_read = update_in.is_read
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/mark-all-read", status_code=status.HTTP_200_OK)
def mark_all_notifications_as_read(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Mark all unread notifications for the authenticated user as read."""
    updated = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .update({Notification.is_read: True})
    )
    db.commit()
    return {"message": f"Marked {updated} notifications as read."}
