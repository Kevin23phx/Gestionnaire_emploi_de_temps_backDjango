from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import require_roles
from dashboard import services


class StatsView(APIView):
    permission_classes = [require_roles("scolarite", "admin")]

    def get(self, request):
        date_from = parse_datetime(request.query_params["from"]) if request.query_params.get("from") else None
        date_to = parse_datetime(request.query_params["to"]) if request.query_params.get("to") else None
        return Response(services.stats(request.user, date_from, date_to, request.query_params.get("ufrId")))
