from django.db import models

from accounts.models import Enseignant
from core.utils import generate_id
from planning.models import Creneau, JourSemaine


class TypeDemande(models.TextChoices):
    ABSENCE = "absence"
    REPORT = "report"
    PERMUTATION = "permutation"


class StatutDemande(models.TextChoices):
    EN_ATTENTE = "en_attente"
    VALIDEE = "validee"
    REFUSEE = "refusee"


class DemandeEnseignant(models.Model):
    """RM-04 : exactement 3 états, transition unique en_attente ->
    {validee, refusee}, jamais de retour en arrière (appliqué au niveau
    service via un UPDATE conditionné sur le statut courant)."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    enseignant = models.ForeignKey(Enseignant, related_name="demandes", on_delete=models.PROTECT)
    type = models.CharField(max_length=16, choices=TypeDemande.choices)
    statut = models.CharField(max_length=16, choices=StatutDemande.choices, default=StatutDemande.EN_ATTENTE)
    motif = models.TextField()

    creneau_concerne = models.ForeignKey(Creneau, related_name="demandes_concerne", on_delete=models.PROTECT)

    # "report" : nouvelle plage proposée (le créneau cible n'existe pas encore)
    jour_propose = models.CharField(max_length=16, choices=JourSemaine.choices, null=True, blank=True)
    heure_debut_proposee_minutes = models.PositiveIntegerField(null=True, blank=True)
    heure_fin_proposee_minutes = models.PositiveIntegerField(null=True, blank=True)
    salle_proposee_id = models.CharField(max_length=64, null=True, blank=True)

    # "permutation" : échange avec un créneau déjà existant
    creneau_propose = models.ForeignKey(
        Creneau, related_name="demandes_propose", on_delete=models.SET_NULL, null=True, blank=True
    )

    motif_decision = models.TextField(null=True, blank=True)
    decide_par_id = models.CharField(max_length=64, null=True, blank=True)
    decide_le = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "demande_enseignant"
        indexes = [models.Index(fields=["enseignant"]), models.Index(fields=["statut"])]
