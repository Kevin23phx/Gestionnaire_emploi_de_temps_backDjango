from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import require_roles
from audit import services
from audit.serializers import AuditEntrySerializer


class AuditListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [require_roles("scolarite", "admin")()]
        return [require_roles("scolarite")()]

    def get(self, request):
        ufr_id = request.query_params.get("ufrId")
        entries = services.list_entries(request.user, ufr_id)
        return Response({"entries": AuditEntrySerializer(entries, many=True).data})

    def post(self, request):
        auteur = request.data.get("auteur")
        action = request.data.get("action")
        if not auteur or not action:
            raise ValidationError("Les champs 'auteur' et 'action' sont obligatoires.")
        entry = services.record(auteur, action, request.data.get("motif"), request.data.get("creneauId"))
        return Response({"entry": AuditEntrySerializer(entry).data}, status=201)


class AuditBatchView(APIView):
    permission_classes = [require_roles("scolarite")]

    def post(self, request):
        entries_data = request.data.get("entries")
        if not entries_data or not isinstance(entries_data, list):
            raise ValidationError("Le champ 'entries' est obligatoire.")
        entries = services.record_batch(
            [
                {
                    "auteur": e["auteur"],
                    "action": e["action"],
                    "motif": e.get("motif"),
                    "creneau_id": e.get("creneauId"),
                }
                for e in entries_data
            ]
        )
        return Response({"entries": AuditEntrySerializer(entries, many=True).data}, status=201)
