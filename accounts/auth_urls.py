from django.urls import path

from accounts.auth_views import ActivateView, LoginView, LogoutView, MeView, MotDePasseView

urlpatterns = [
    path("api/auth/login", LoginView.as_view()),
    path("api/auth/activate", ActivateView.as_view()),
    path("api/auth/logout", LogoutView.as_view()),
    path("api/auth/me", MeView.as_view()),
    # [V8.3] Changement de mot de passe par son titulaire (FR-AUTH-07).
    path("api/auth/mot-de-passe", MotDePasseView.as_view()),
]
