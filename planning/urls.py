from django.urls import path

from planning.views import AnnulerView, CreneauDetailView, CreneauxView, SeanceView, VerifierView

# "verifier" déclaré AVANT "<creneau_id>" — sinon Django le matcherait comme
# un id de créneau. [V3] "pour-permutation" a disparu avec le circuit de
# permutation (02_SRS §2.7 retirée).
urlpatterns = [
    path("api/creneaux", CreneauxView.as_view()),
    path("api/creneaux/verifier", VerifierView.as_view()),
    path("api/creneaux/<str:creneau_id>", CreneauDetailView.as_view()),
    path("api/creneaux/<str:creneau_id>/annuler", AnnulerView.as_view()),
    # [V3] FR-EDT-07 : annulation/rétablissement d'une séance datée.
    path("api/creneaux/<str:creneau_id>/seance", SeanceView.as_view()),
]
