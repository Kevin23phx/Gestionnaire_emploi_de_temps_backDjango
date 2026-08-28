from django.db import models

from core.models import Ufr
from core.utils import generate_id


class Role(models.TextChoices):
    ETUDIANT = "etudiant"
    ENSEIGNANT = "enseignant"
    SCOLARITE = "scolarite"
    ADMIN = "admin"


class Enseignant(models.Model):
    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    nom = models.CharField(max_length=255)
    prenom = models.CharField(max_length=255)

    class Meta:
        db_table = "enseignant"

    def __str__(self) -> str:
        return f"{self.prenom} {self.nom}"


class EnseignantUfr(models.Model):
    """FR-REF-06 : affectation Enseignant<->UFR — enregistrée automatiquement
    à la première intervention dans une UFR (jamais un blocus, retour
    d'usage 2026-08-27, cf. planning/services.py)."""

    enseignant = models.ForeignKey(Enseignant, related_name="ufrs", on_delete=models.CASCADE)
    ufr = models.ForeignKey(Ufr, related_name="enseignants", on_delete=models.CASCADE)

    class Meta:
        db_table = "enseignant_ufr"
        constraints = [
            models.UniqueConstraint(fields=["enseignant", "ufr"], name="enseignant_ufr_unique"),
        ]


class Utilisateur(models.Model):
    """Un compte a exactement un rôle, jamais choisi par le client (INV-03).
    "mot_de_passe_hash" absent/null = compte pré-provisionné, pas encore
    activé (FR-AUTH-03). "ufr_id" non-null SSI role="scolarite" (INV-10),
    appliqué par une contrainte CHECK en base (voir la migration)."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    identifiant = models.CharField(max_length=255, unique=True)
    mot_de_passe_hash = models.CharField(max_length=255, null=True, blank=True)
    nom = models.CharField(max_length=255)
    prenom = models.CharField(max_length=255)
    role = models.CharField(max_length=32, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    ufr = models.ForeignKey(Ufr, related_name="gestionnaires", on_delete=models.PROTECT, null=True, blank=True)
    etudiant = models.OneToOneField(
        "referentiel.Etudiant", related_name="utilisateur", on_delete=models.CASCADE, null=True, blank=True
    )
    enseignant = models.OneToOneField(
        Enseignant, related_name="utilisateur", on_delete=models.CASCADE, null=True, blank=True
    )

    class Meta:
        db_table = "utilisateur"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(role=Role.SCOLARITE) & models.Q(ufr__isnull=False))
                    | (~models.Q(role=Role.SCOLARITE) & models.Q(ufr__isnull=True))
                ),
                name="utilisateur_scolarite_requiert_ufr",
            ),
        ]

    def __str__(self) -> str:
        return self.identifiant


class Session(models.Model):
    """Session serveur opaque : seul sha256(valeur brute du cookie) est
    stocké — jamais la valeur elle-même (voir accounts/authentication.py)."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    token_hash = models.CharField(max_length=128, unique=True)
    utilisateur = models.ForeignKey(Utilisateur, related_name="sessions", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    user_agent = models.CharField(max_length=512, null=True, blank=True)
    ip_address = models.CharField(max_length=64, null=True, blank=True)

    class Meta:
        db_table = "session"
        indexes = [models.Index(fields=["utilisateur"])]
