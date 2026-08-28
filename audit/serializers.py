from rest_framework import serializers

from audit.models import AuditEntry


class AuditEntrySerializer(serializers.ModelSerializer):
    dateHeure = serializers.DateTimeField(source="date_heure")

    class Meta:
        model = AuditEntry
        fields = ["id", "auteur", "dateHeure", "action", "motif"]
