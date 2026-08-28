from django.urls import path

from accounts.auth_views import ActivateView, LoginView, LogoutView, MeView

urlpatterns = [
    path("api/auth/login", LoginView.as_view()),
    path("api/auth/activate", ActivateView.as_view()),
    path("api/auth/logout", LogoutView.as_view()),
    path("api/auth/me", MeView.as_view()),
]
