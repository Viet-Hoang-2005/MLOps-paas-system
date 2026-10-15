from django.db.models import Q
from .models import Notification


def list_user_notifications(user, *, is_read=None, type=None, search=None):
    """Retrieve notifications belonging to a specific user with filtering."""
    qs = Notification.objects.filter(user=user)
    if is_read is not None:
        qs = qs.filter(is_read=is_read)
    if type:
        qs = qs.filter(type=type)
    if search:
        qs = qs.filter(Q(title__icontains=search) | Q(message__icontains=search))
    return qs


def get_user_unread_count(user) -> int:
    """Return count of unread notifications for a specific user."""
    return Notification.objects.filter(user=user, is_read=False).count()


def get_notification_by_public_id(user, public_id):
    """Retrieve a single notification by public_id ensuring user ownership."""
    return Notification.objects.filter(user=user, public_id=public_id).first()
