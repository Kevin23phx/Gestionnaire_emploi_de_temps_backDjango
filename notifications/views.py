from rest_framework.response import Response
from rest_framework.views import APIView

from notifications import services
from notifications.serializers import NotificationItemSerializer


class NotificationsView(APIView):
    def get(self, request):
        notifications = services.list_notifications(request.user.id)
        return Response({"notifications": NotificationItemSerializer(notifications, many=True).data})


class MarkReadView(APIView):
    def patch(self, request, notification_id: str):
        notification = services.mark_read(notification_id, request.user.id)
        return Response(NotificationItemSerializer(notification).data)
