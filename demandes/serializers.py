from rest_framework import serializers

from accounts.serializers import EnseignantSerializer
from core.time_utils import minutes_to_hhmm
from demandes.models import DemandeEnseignant


class DemandeEnseignantSerializer(serializers.ModelSerializer):
    enseignant = EnseignantSerializer()
    creneauConcerneId = serializers.CharField(source="creneau_concerne_id")
    creneauProposeId = serializers.CharField(source="creneau_propose_id", allow_null=True)
    jourPropose = serializers.CharField(source="jour_propose", allow_null=True)
    heureDebutProposee = serializers.SerializerMethodField()
    heureFinProposee = serializers.SerializerMethodField()
    salleProposeeId = serializers.CharField(source="salle_proposee_id", allow_null=True)
    motifDecision = serializers.CharField(source="motif_decision", allow_null=True)
    decideLe = serializers.DateTimeField(source="decide_le", allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at")

    class Meta:
        model = DemandeEnseignant
        fields = [
            "id",
            "enseignant",
            "type",
            "statut",
            "creneauConcerneId",
            "creneauProposeId",
            "motif",
            "jourPropose",
            "heureDebutProposee",
            "heureFinProposee",
            "salleProposeeId",
            "motifDecision",
            "decideLe",
            "createdAt",
        ]

    def get_heureDebutProposee(self, obj):
        return minutes_to_hhmm(obj.heure_debut_proposee_minutes) if obj.heure_debut_proposee_minutes is not None else None

    def get_heureFinProposee(self, obj):
        return minutes_to_hhmm(obj.heure_fin_proposee_minutes) if obj.heure_fin_proposee_minutes is not None else None
