from django.urls import path

from notifications.views import MarkReadView, NotificationsView

urlpatterns = [
    path("api/notifications", NotificationsView.as_view()),
    path("api/notifications/<str:notification_id>/lue", MarkReadView.as_view()),
]
