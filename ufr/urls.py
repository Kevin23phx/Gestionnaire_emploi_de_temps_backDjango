from django.urls import path

from ufr.views import GestionnaireCreateView, PeriodeAcademiqueView, UfrListCreateView

urlpatterns = [
    path("api/ufrs", UfrListCreateView.as_view()),
    # [V3] Déclaré AVANT la route à segment variable : "periode" n'est pas
    # un identifiant d'UFR.
    path("api/ufrs/periode", PeriodeAcademiqueView.as_view()),
    path("api/ufrs/<str:ufr_id>/gestionnaire", GestionnaireCreateView.as_view()),
]
