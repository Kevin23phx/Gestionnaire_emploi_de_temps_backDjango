import re

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import require_roles
from ufr import services
from ufr.serializers import UfrSerializer

SIGLE_RE = re.compile(r"^[a-zA-Z]{2,10}$")


class UfrListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return []  # ouvert à tout rôle authentifié (IsAuthenticatedCM par défaut)
        return [require_roles("admin")()]

    def get(self, request):
        return Response({"ufrs": services.list_ufrs()})

    def post(self, request):
        nom = request.data.get("nom")
        sigle = request.data.get("sigle")
        if not nom:
            raise ValidationError("Le nom est obligatoire.")
        if not sigle or not SIGLE_RE.match(sigle):
            raise ValidationError("Le sigle doit contenir entre 2 et 10 lettres, sans espace ni accent.")

        auteur = f"{request.user.prenom} {request.user.nom}"
        ufr = services.create(nom, sigle, auteur)
        return Response({"ufr": UfrSerializer(ufr).data}, status=201)


class GestionnaireCreateView(APIView):
    permission_classes = [require_roles("admin")]

    def post(self, request, ufr_id: str):
        nom = request.data.get("nom")
        prenom = request.data.get("prenom")
        if not nom or not prenom:
            raise ValidationError("Le nom et le prénom sont obligatoires.")

        auteur = f"{request.user.prenom} {request.user.nom}"
        resultat = services.create_gestionnaire(ufr_id, nom, prenom, auteur)
        return Response(
            {"identifiant": resultat["identifiant"], "ufr": UfrSerializer(resultat["ufr"]).data}, status=201
        )
