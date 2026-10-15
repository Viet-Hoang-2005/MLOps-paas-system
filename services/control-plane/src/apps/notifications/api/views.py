from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from common.api.pagination import DefaultPagination
from ..selectors import get_user_unread_count, list_user_notifications
from ..services import (
    delete_notification,
    mark_all_notifications_as_read,
    mark_notification_as_read,
)
from .serializers import NotificationSerializer, UnreadCountSerializer


class NotificationListEndpoint(APIView):
    permission_classes = (IsAuthenticated,)
    pagination_class = DefaultPagination

    def get(self, request):
        is_read_raw = request.query_params.get("is_read")
        is_read = None
        if is_read_raw is not None:
            is_read = is_read_raw.lower() in ("true", "1")
        notification_type = request.query_params.get("type")
        search = request.query_params.get("search")

        qs = list_user_notifications(
            request.user,
            is_read=is_read,
            type=notification_type,
            search=search,
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            serializer = NotificationSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = NotificationSerializer(qs, many=True)
        return Response(serializer.data)


class NotificationUnreadCountEndpoint(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request):
        count = get_user_unread_count(request.user)
        return Response(UnreadCountSerializer({"unread_count": count}).data)


class NotificationMarkReadEndpoint(APIView):
    permission_classes = (IsAuthenticated,)

    def patch(self, request, public_id):
        notification = mark_notification_as_read(request.user, public_id)
        if not notification:
            return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(NotificationSerializer(notification).data)


class NotificationMarkAllReadEndpoint(APIView):
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        updated_count = mark_all_notifications_as_read(request.user)
        return Response({"updated": updated_count}, status=status.HTTP_200_OK)


class NotificationDeleteEndpoint(APIView):
    permission_classes = (IsAuthenticated,)

    def delete(self, request, public_id):
        deleted = delete_notification(request.user, public_id)
        if not deleted:
            return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
