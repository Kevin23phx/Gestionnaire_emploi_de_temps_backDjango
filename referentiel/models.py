from django.db import models
from django.db.models.functions import Lower

from core.models import Ufr
from core.utils import generate_id


class TypeUsageSalle(models.TextChoices):
    PROPRE = "propre"
    COMMUNE = "commune"
    LOUEE = "louee"
    GRATUITE = "gratuite"


class StructureGestionnaire(models.TextChoices):
    """"UFR" (ufr_id renseigné) ou "DEP" (salle commune/louée transversale,
    ufr_id toujours null, administrée par l'Admin — cf. 01_PRD note
    2026-08-27)."""

    UFR = "UFR"
    DEP = "DEP"


class Groupe(models.Model):
    """"effectif" n'est jamais une colonne : toujours calculé (COUNT(Etudiant)).
    "annee_academique" (FR-REF-12) : année EN COURS de CE groupe précis,
    distincte d'Etudiant.annee_academique (année d'inscription, immuable) —
    une promotion se fait en créant un nouveau Groupe, jamais en modifiant
    celui-ci sur place."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    nom = models.CharField(max_length=255)
    filiere = models.CharField(max_length=255)
    niveau = models.CharField(max_length=32)
    annee_academique = models.CharField(max_length=16)

    ufr = models.ForeignKey(Ufr, related_name="groupes", on_delete=models.PROTECT)

    class Meta:
        db_table = "groupe"
        indexes = [models.Index(fields=["ufr"])]
        constraints = [
            models.UniqueConstraint(Lower("nom"), name="groupe_nom_lower_unique"),
        ]

    def __str__(self) -> str:
        return self.nom


class Etudiant(models.Model):
    """Distinct de Utilisateur pour la même raison qu'Enseignant en est
    distinct : la scolarité doit pouvoir rattacher un étudiant à un groupe
    avant même que son compte existe. "annee_academique" (FR-REF-09) : année
    d'inscription, immuable — sert au filtrage (FR-REF-11), jamais à
    assouplir l'unicité de l'INE (FR-REF-08). "ufr_id" (INV-09) : toujours
    rattaché à exactement une UFR ; changement réservé à l'Admin
    (FR-ADMIN-05)."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    ine = models.CharField(max_length=64, unique=True)
    nom = models.CharField(max_length=255)
    prenom = models.CharField(max_length=255)
    filiere = models.CharField(max_length=255)
    niveau = models.CharField(max_length=32)
    annee_academique = models.CharField(max_length=16)

    ufr = models.ForeignKey(Ufr, related_name="etudiants", on_delete=models.PROTECT)
    groupe = models.ForeignKey(Groupe, related_name="etudiants", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "etudiant"
        indexes = [
            models.Index(fields=["groupe"]),
            models.Index(fields=["ufr"]),
            models.Index(fields=["ufr", "annee_academique"]),
            models.Index(fields=["ufr", "filiere"]),
        ]

    def __str__(self) -> str:
        return f"{self.prenom} {self.nom} ({self.ine})"


class Salle(models.Model):
    """"structure_gestionnaire" = "UFR" (ufr_id non-null) ou "DEP" (ufr_id
    toujours null) — jamais saisi librement par le client, dérivé du
    contexte de création (rôle de l'appelant, cf. referentiel/services.py)."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    nom = models.CharField(max_length=255)
    batiment = models.CharField(max_length=255)
    capacite = models.PositiveIntegerField()
    structure_gestionnaire = models.CharField(
        max_length=8, choices=StructureGestionnaire.choices, default=StructureGestionnaire.UFR
    )
    type_usage = models.CharField(max_length=16, choices=TypeUsageSalle.choices)

    ufr = models.ForeignKey(Ufr, related_name="salles", on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        db_table = "salle"
        indexes = [models.Index(fields=["ufr"])]
        constraints = [
            models.UniqueConstraint(Lower("nom"), name="salle_nom_lower_unique"),
            models.CheckConstraint(
                condition=(
                    (models.Q(structure_gestionnaire=StructureGestionnaire.UFR) & models.Q(ufr__isnull=False))
                    | (models.Q(structure_gestionnaire=StructureGestionnaire.DEP) & models.Q(ufr__isnull=True))
                ),
                name="salle_structure_gestionnaire_coherente",
            ),
        ]

    def __str__(self) -> str:
        return self.nom


class UniteEnseignement(models.Model):
    """"niveau" (FR-REF-13, L1...M2) : à quel niveau ce cours s'adresse —
    affiché à côté de l'intitulé, indépendant de l'année académique."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    code = models.CharField(max_length=64, null=True, blank=True)
    intitule = models.CharField(max_length=255)
    niveau = models.CharField(max_length=32)

    ufr = models.ForeignKey(Ufr, related_name="ues", on_delete=models.PROTECT)

    class Meta:
        db_table = "unite_enseignement"
        indexes = [models.Index(fields=["ufr"])]
        constraints = [
            models.UniqueConstraint(Lower("intitule"), name="ue_intitule_lower_unique"),
        ]

    def __str__(self) -> str:
        return self.intitule
