from django.urls import path

from dashboard.views import StatsView

urlpatterns = [
    path("api/dashboard/stats", StatsView.as_view()),
]
