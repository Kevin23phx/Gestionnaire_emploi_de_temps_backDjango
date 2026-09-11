from django.urls import path

from public.views import (
    AlertesView,
    CalendrierView,
    CleAlerteView,
    DepartementsView,
    GroupesView,
    NiveauxView,
    ProgrammeView,
    UfrsView,
)

# [V3] TOUTES les routes de ce fichier sont ouvertes sans authentification
# (FR-AUTH-05) et exclusivement en lecture, sauf l'abonnement aux alertes qui
# n'écrit que sa propre table d'abonnements anonymes. Aucune autre route du
# projet n'est publique : voir la note dans config/urls.py.
urlpatterns = [
    path("api/public/ufrs", UfrsView.as_view()),
    path("api/public/departements", DepartementsView.as_view()),
    path("api/public/niveaux", NiveauxView.as_view()),
    path("api/public/groupes", GroupesView.as_view()),
    path("api/public/programme/<str:groupe_id>", ProgrammeView.as_view()),
    # L'extension .ics dans l'URL : beaucoup de clients d'agenda refusent de
    # s'abonner à une adresse qui n'y ressemble pas, quel que soit le
    # Content-Type renvoyé.
    path("api/public/calendrier/<str:groupe_id>.ics", CalendrierView.as_view()),
    path("api/public/alertes", AlertesView.as_view()),
    path("api/public/alertes/cle", CleAlerteView.as_view()),
]
