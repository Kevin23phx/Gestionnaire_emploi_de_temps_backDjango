from django.urls import path

from referentiel.views import (
    AffecterEtudiantsView,
    CoursView,
    EtudiantsView,
    GroupesView,
    SallesView,
    TransfererUfrView,
)

urlpatterns = [
    path("api/groupes", GroupesView.as_view()),
    path("api/salles", SallesView.as_view()),
    path("api/cours", CoursView.as_view()),
    path("api/etudiants", EtudiantsView.as_view()),
    path("api/etudiants/affecter", AffecterEtudiantsView.as_view()),
    path("api/etudiants/<str:etudiant_id>/transferer-ufr", TransfererUfrView.as_view()),
]
