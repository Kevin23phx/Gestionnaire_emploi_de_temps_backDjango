from django.urls import path

from sync.views import SyncQueueView

urlpatterns = [
    path("api/sync/queue", SyncQueueView.as_view()),
]
