from django.urls import path

from planning.views import AnnulerView, CreneauDetailView, CreneauxView, ProgrammeCompletView, VerifierView

# "pour-permutation" et "verifier" déclarés AVANT "<creneau_id>" — sinon
# Django les matcherait comme un id de créneau.
urlpatterns = [
    path("api/creneaux", CreneauxView.as_view()),
    path("api/creneaux/pour-permutation", ProgrammeCompletView.as_view()),
    path("api/creneaux/verifier", VerifierView.as_view()),
    path("api/creneaux/<str:creneau_id>", CreneauDetailView.as_view()),
    path("api/creneaux/<str:creneau_id>/annuler", AnnulerView.as_view()),
]
