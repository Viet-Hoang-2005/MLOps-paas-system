from django.utils import timezone
from .models import Notification
from .selectors import get_notification_by_public_id


def create_notification(
    user,
    *,
    title: str,
    message: str,
    type: str = Notification.Type.SYSTEM,
    level: str = Notification.Level.INFO,
    link: str = "",
    metadata: dict | None = None,
) -> Notification:
    """Create a persistent notification for a user."""
    tenant_id = getattr(user, "tenant_id", "")
    return Notification.objects.create(
        user=user,
        tenant_id=tenant_id,
        title=title,
        message=message,
        type=type,
        level=level,
        link=link,
        metadata=metadata or {},
    )


def mark_notification_as_read(user, public_id) -> Notification | None:
    """Mark a specific notification as read."""
    notification = get_notification_by_public_id(user, public_id)
    if notification and not notification.is_read:
        notification.mark_as_read()
    return notification


def mark_all_notifications_as_read(user) -> int:
    """Mark all unread notifications for a user as read."""
    return Notification.objects.filter(user=user, is_read=False).update(
        is_read=True,
        read_at=timezone.now(),
    )


def delete_notification(user, public_id) -> bool:
    """Delete a specific notification."""
    notification = get_notification_by_public_id(user, public_id)
    if notification:
        notification.delete()
        return True
    return False
