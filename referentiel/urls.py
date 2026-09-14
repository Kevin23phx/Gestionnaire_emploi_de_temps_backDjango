from django.urls import path

from referentiel.views import (
    CoursDetailView,
    CoursView,
    DepartementsView,
    GroupeDetailView,
    GroupesPassageView,
    GroupesView,
    SallesView,
)

# [V3.1] Les routes /etudiants ont été supprimées avec le référentiel
# nominatif des étudiants : l'effectif d'un groupe est désormais un nombre
# saisi (voir referentiel/models.py).
urlpatterns = [
    path("api/departements", DepartementsView.as_view()),
    # [V6] "passage" AVANT "<str:groupe_id>" — sinon Django résout
    # /api/groupes/passage comme GroupeDetailView avec groupe_id="passage".
    path("api/groupes/passage", GroupesPassageView.as_view()),
    path("api/groupes", GroupesView.as_view()),
    path("api/groupes/<str:groupe_id>", GroupeDetailView.as_view()),
    path("api/salles", SallesView.as_view()),
    path("api/cours", CoursView.as_view()),
    path("api/cours/<str:cours_id>", CoursDetailView.as_view()),
]
