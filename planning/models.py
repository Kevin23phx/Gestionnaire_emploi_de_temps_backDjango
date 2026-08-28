from django.db import models
from django.db.models import Q

from accounts.models import Enseignant
from core.utils import generate_id
from referentiel.models import Groupe, Salle, UniteEnseignement


class JourSemaine(models.TextChoices):
    LUNDI = "lundi"
    MARDI = "mardi"
    MERCREDI = "mercredi"
    JEUDI = "jeudi"
    VENDREDI = "vendredi"
    SAMEDI = "samedi"


class StatutCreneau(models.TextChoices):
    NORMAL = "normal"
    MODIFIE = "modifie"
    ANNULE = "annule"


class TypeConflit(models.TextChoices):
    SALLE = "salle"
    ENSEIGNANT = "enseignant"
    GROUPE = "groupe"
    CAPACITE = "capacite"


class GraviteConflit(models.TextChoices):
    BLOQUANT = "bloquant"
    AVERTISSEMENT = "avertissement"


class Creneau(models.Model):
    """INV-01 : toujours rattaché à exactement une salle/horaire/groupe/
    enseignant/UE. INV-07 : id stable pour toute la durée de vie — une mise
    à jour est toujours un vrai UPDATE, jamais un delete+recreate (garanti
    au niveau service, cf. planning/services.py).

    "derogation_motif" : renseigné uniquement si ce créneau a été enregistré
    malgré un conflit détecté — la contrainte EXCLUDE ci-dessous a besoin de
    le voir directement sur la ligne pour l'exempter de la garantie physique
    anti-double-réservation (sinon la dérogation elle-même serait rendue
    impossible par son propre filet de sécurité).
    """

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)

    ue = models.ForeignKey(UniteEnseignement, related_name="creneaux", on_delete=models.PROTECT)
    enseignant = models.ForeignKey(Enseignant, related_name="creneaux", on_delete=models.PROTECT)
    groupe = models.ForeignKey(Groupe, related_name="creneaux", on_delete=models.PROTECT)
    salle = models.ForeignKey(Salle, related_name="creneaux", on_delete=models.PROTECT)

    jour = models.CharField(max_length=16, choices=JourSemaine.choices)
    heure_debut_minutes = models.PositiveIntegerField()
    heure_fin_minutes = models.PositiveIntegerField()

    statut = models.CharField(max_length=16, choices=StatutCreneau.choices, default=StatutCreneau.NORMAL)
    motif = models.TextField(null=True, blank=True)
    derogation_motif = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "creneau"
        indexes = [
            models.Index(fields=["salle", "jour"]),
            models.Index(fields=["enseignant", "jour"]),
            models.Index(fields=["groupe", "jour"]),
        ]
        constraints = [
            # INT-03 : un créneau modifié/annulé sans motif est rejeté — la
            # validation applicative (services.py) le vérifie déjà, ceci est
            # le filet de sécurité en base.
            models.CheckConstraint(
                condition=Q(statut=StatutCreneau.NORMAL) | (Q(motif__isnull=False) & ~Q(motif="")),
                name="creneau_motif_requis_si_non_normal",
            ),
            # INV-02 : la contrainte EXCLUDE USING gist réelle (anti-double-
            # réservation physique) est ajoutée en SQL brut dans une migration
            # dédiée (planning/migrations/0002_creneau_exclude_constraint.py)
            # — colonne générée "plage" + EXCLUDE, comme pour le backend
            # NestJS d'origine (cf. backend/prisma/migrations/
            # *_creneau_exclude_constraint) : trop spécifique à PostgreSQL
            # pour être exprimé proprement via l'API déclarative de Meta.
        ]


class ConflitJournal(models.Model):
    """Journal d'événements append-only — PAS "les conflits actuels" (qui
    sont toujours recalculés à la demande par le moteur de conflits).
    Existe pour donner à DashboardModule un signal daté."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    type = models.CharField(max_length=16, choices=TypeConflit.choices)
    gravite = models.CharField(max_length=16, choices=GraviteConflit.choices)
    titre = models.CharField(max_length=255)
    description = models.TextField()

    creneau_a = models.ForeignKey(Creneau, related_name="conflits_a", on_delete=models.PROTECT)
    creneau_b = models.ForeignKey(
        Creneau, related_name="conflits_b", on_delete=models.SET_NULL, null=True, blank=True
    )

    derogation_motif = models.TextField(null=True, blank=True)
    detecte_le = models.DateTimeField(auto_now_add=True)
    detecte_par = models.CharField(max_length=255)

    class Meta:
        db_table = "conflit_journal"
        indexes = [models.Index(fields=["detecte_le"])]
