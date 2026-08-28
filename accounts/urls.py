from django.urls import path

from accounts.views import AffecterUfrView, EnseignantsView

urlpatterns = [
    path("api/enseignants", EnseignantsView.as_view()),
    path("api/enseignants/<str:enseignant_id>/affecter-ufr", AffecterUfrView.as_view()),
]
