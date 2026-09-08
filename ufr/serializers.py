from rest_framework import serializers

from core.models import Ufr


class UfrSerializer(serializers.ModelSerializer):
    # [V3] FR-REF-16 : la période académique voyage avec l'UFR, le
    # Gestionnaire en ayant besoin sur chaque écran de planning pour savoir
    # quelles semaines il peut atteindre.
    # [V3.2] "sigleAffiche" est composé côté serveur ("UFR/SH" vs "IBAM") :
    # la règle de préfixe dépend du type, et la dupliquer dans le frontend
    # garantirait qu'elle diverge un jour.
    sigleAffiche = serializers.CharField(source="sigle_affiche", read_only=True)
    periodeLibelle = serializers.CharField(source="periode_libelle", allow_null=True, required=False)
    periodeDebut = serializers.DateField(source="periode_debut", allow_null=True, required=False)
    periodeFin = serializers.DateField(source="periode_fin", allow_null=True, required=False)

    class Meta:
        model = Ufr
        fields = ["id", "nom", "sigle", "type", "sigleAffiche", "periodeLibelle", "periodeDebut", "periodeFin"]
