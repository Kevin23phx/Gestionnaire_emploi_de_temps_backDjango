from rest_framework import serializers

from core.models import Ufr


class UfrSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ufr
        fields = ["id", "nom", "sigle"]
