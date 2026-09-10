from django.urls import path

from ufr.views import GestionnaireCreateView, UfrListCreateView

urlpatterns = [
    path("api/ufrs", UfrListCreateView.as_view()),
    path("api/ufrs/<str:ufr_id>/gestionnaire", GestionnaireCreateView.as_view()),
]
