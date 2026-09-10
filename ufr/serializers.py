from rest_framework import serializers

from core.models import Ufr


class UfrSerializer(serializers.ModelSerializer):
    # [V3.2] "sigleAffiche" est composé côté serveur ("UFR/SH" vs "IBAM") :
    # la règle de préfixe dépend du type, et la dupliquer dans le frontend
    # garantirait qu'elle diverge un jour.
    sigleAffiche = serializers.CharField(source="sigle_affiche", read_only=True)
    class Meta:
        model = Ufr
        fields = ["id", "nom", "sigle", "type", "sigleAffiche"]
