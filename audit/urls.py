from django.urls import path

from audit.views import AuditBatchView, AuditListCreateView

urlpatterns = [
    path("api/audit", AuditListCreateView.as_view()),
    path("api/audit/batch", AuditBatchView.as_view()),
]
