from rest_framework import serializers

from accounts.models import Enseignant


class EnseignantUfrSerializer(serializers.Serializer):
    ufrId = serializers.CharField(source="ufr_id")


class EnseignantSerializer(serializers.ModelSerializer):
    ufrs = EnseignantUfrSerializer(many=True, read_only=True)

    class Meta:
        model = Enseignant
        fields = ["id", "nom", "prenom", "ufrs"]
