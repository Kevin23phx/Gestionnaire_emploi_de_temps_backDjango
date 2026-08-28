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
    """GET lisible par tous les rôles authentifiés (permission par défaut) ;
    POST réservé à la scolarité (INT-02 : seul point d'entrée de création
    de compte enseignant, en dehors du seed)."""

    def get(self, request):
        enseignants = enseignant_service.list_enseignants()
        return Response({"enseignants": EnseignantSerializer(enseignants, many=True).data})

    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite")()]
        return super().get_permissions()

    def post(self, request):
        _requis(request.data, "nom", "prenom", "identifiant")
        resultat = enseignant_service.create_enseignant(
            request.data["nom"], request.data["prenom"], request.data["identifiant"], request.user.ufr_id
        )
        return Response(
            {"identifiant": resultat["identifiant"], "enseignant": EnseignantSerializer(resultat["enseignant"]).data},
            status=201,
        )


class AffecterUfrView(APIView):
    permission_classes = [require_roles("scolarite")]

    def post(self, request, enseignant_id: str):
        enseignant_service.affecter_ufr(enseignant_id, request.user.ufr_id)
        return Response(status=201)
