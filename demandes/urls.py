from django.urls import path

from demandes.views import DeciderView, DemandesView

urlpatterns = [
    path("api/demandes", DemandesView.as_view()),
    path("api/demandes/<str:demande_id>/decider", DeciderView.as_view()),
]
