from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import enseignant_service
from accounts.permissions import require_roles
from accounts.serializers import EnseignantSerializer


def _requis(data: dict, *champs: str) -> None:
    for champ in champs:
        if not data.get(champ):
            raise ValidationError(f"Le champ '{champ}' est obligatoire.")


class EnseignantsView(APIView):
    """GET lisible par tout compte authentifié ; POST réservé à la scolarité.

    [V3] Ne crée plus de compte, seulement une fiche de référentiel — la
    création de comptes est désormais l'affaire exclusive de `ufr`
    (INT-02)."""

    def get(self, request):
        recherche = (request.query_params.get("recherche") or "").strip() or None
        enseignants = enseignant_service.list_enseignants(recherche)
        return Response({"enseignants": EnseignantSerializer(enseignants, many=True).data})

    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite")()]
        return super().get_permissions()

    def post(self, request):
        _requis(request.data, "nom", "prenom")
        enseignant = enseignant_service.create_enseignant(
            request.data["nom"], request.data["prenom"], request.user.ufr_id
        )
        return Response({"enseignant": EnseignantSerializer(enseignant).data}, status=201)


class AffecterUfrView(APIView):
    permission_classes = [require_roles("scolarite")]

    def post(self, request, enseignant_id: str):
        enseignant_service.affecter_ufr(enseignant_id, request.user.ufr_id)
        return Response(status=201)
