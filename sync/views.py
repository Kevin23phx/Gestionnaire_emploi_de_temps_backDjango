from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from sync.models import SyncQueueEntry


class SyncQueueView(APIView):
    def post(self, request):
        payload = request.data.get("payload")
        if not isinstance(payload, dict):
            raise ValidationError("Le champ 'payload' est obligatoire.")
        entry = SyncQueueEntry.objects.create(utilisateur_id=request.user.id, payload=payload)
        return Response({"id": entry.id}, status=202)
