from django.urls import path

from planning.views import AnnulerView, CreneauDetailView, CreneauxView, VerifierView

# "verifier" déclaré AVANT "<creneau_id>" — sinon Django le matcherait comme
# un id de créneau. [V4] La route "/seance" a disparu avec le modèle des
# séances annulées : un créneau porte désormais sa propre date, l'annuler
# revient donc à annuler cette séance-là et aucune autre.
urlpatterns = [
    path("api/creneaux", CreneauxView.as_view()),
    path("api/creneaux/verifier", VerifierView.as_view()),
    path("api/creneaux/<str:creneau_id>", CreneauDetailView.as_view()),
    path("api/creneaux/<str:creneau_id>/annuler", AnnulerView.as_view()),
]
