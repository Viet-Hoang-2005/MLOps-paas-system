from django.urls import path
from .views import (
    NotificationDeleteEndpoint,
    NotificationListEndpoint,
    NotificationMarkAllReadEndpoint,
    NotificationMarkReadEndpoint,
    NotificationUnreadCountEndpoint,
)

urlpatterns = [
    path("", NotificationListEndpoint.as_view(), name="notification-list"),
    path("unread-count/", NotificationUnreadCountEndpoint.as_view(), name="notification-unread-count"),
    path("mark-all-read/", NotificationMarkAllReadEndpoint.as_view(), name="notification-mark-all-read"),
    path("<uuid:public_id>/read/", NotificationMarkReadEndpoint.as_view(), name="notification-mark-read"),
    path("<uuid:public_id>/", NotificationDeleteEndpoint.as_view(), name="notification-delete"),
]
