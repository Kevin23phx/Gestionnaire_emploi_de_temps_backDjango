from django.conf import settings
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import auth_service


def _requis(data: dict, *champs: str) -> None:
    for champ in champs:
        if not data.get(champ):
            raise ValidationError(f"Le champ '{champ}' est obligatoire.")


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        _requis(request.data, "identifiant", "motDePasse")
        response = Response()
        resultat = auth_service.login(request.data["identifiant"], request.data["motDePasse"], response)
        response.data = resultat
        response.status_code = 200
        return response


class ActivateView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        _requis(request.data, "identifiant", "nouveauMotDePasse", "confirmationMotDePasse")
        response = Response()
        resultat = auth_service.activate(
            request.data["identifiant"],
            request.data["nouveauMotDePasse"],
            request.data["confirmationMotDePasse"],
            response,
        )
        response.data = resultat
        response.status_code = 200
        return response


class LogoutView(APIView):
    def post(self, request):
        raw_token = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        response = Response()
        auth_service.logout(raw_token, response)
        response.data = {"ok": True}
        response.status_code = 200
        return response


class MeView(APIView):
    def get(self, request):
        user = request.user
        return Response({"nom": user.nom, "prenom": user.prenom, "role": user.role, "ufrId": user.ufr_id})
