from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import require_roles
from demandes import services
from demandes.serializers import DemandeEnseignantSerializer

TYPES_DEMANDE = {"absence", "report", "permutation"}
JOURS = {"lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"}
DECISIONS = {"validee", "refusee"}


class DemandesView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("enseignant")()]
        return [require_roles("enseignant", "scolarite")()]

    def post(self, request):
        if not request.user.enseignant:
            raise PermissionDenied("Compte enseignant requis.")
        dto = request.data
        if dto.get("type") not in TYPES_DEMANDE:
            raise ValidationError("Type de demande invalide.")
        if not dto.get("creneauConcerneId") or not dto.get("motif"):
            raise ValidationError("Les champs 'creneauConcerneId' et 'motif' sont obligatoires.")
        demande = services.create(request.user.enseignant.id, dto)
        return Response(DemandeEnseignantSerializer(demande).data, status=201)

    def get(self, request):
        demandes = services.list_demandes(request.user)
        return Response({"demandes": DemandeEnseignantSerializer(demandes, many=True).data})


class DeciderView(APIView):
    permission_classes = [require_roles("scolarite")]

    def post(self, request, demande_id: str):
        dto = request.data
        if dto.get("decision") not in DECISIONS:
            raise ValidationError("Décision invalide.")
        demande = services.decider(demande_id, dto, request.user)
        return Response(DemandeEnseignantSerializer(demande).data, status=201)
