from django.db import models

from core.models import Ufr
from core.utils import generate_id


class Role(models.TextChoices):
    """[V3] INV-03 / RM-03 : deux rôles, et deux seulement.

    "etudiant" et "enseignant" ont été retirés le 2026-09-07 : le programme
    étant désormais public (FR-PUB-01), il n'y a plus rien à ouvrir derrière
    un compte pour eux. Les *entités* Etudiant et Enseignant, elles,
    demeurent au référentiel — un créneau porte toujours un enseignant
    (INV-01) et l'effectif d'un groupe alimente toujours le conflit de
    capacité (RM-02).
    """

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
    appliqué par une contrainte CHECK en base (voir la migration).

    [V3] Les relations vers Etudiant et Enseignant ont été retirées le
    2026-09-07 avec les rôles correspondants : un compte n'est plus jamais
    la doublure d'une fiche de référentiel, il est toujours un compte de
    gestion. C'est ce qui rend INT-02 (aucun compte hors création par
    l'Admin) vérifiable d'un coup d'œil : `ufr/services.py` est le seul
    endroit du code qui crée un Utilisateur.
    """

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    identifiant = models.CharField(max_length=255, unique=True)
    mot_de_passe_hash = models.CharField(max_length=255, null=True, blank=True)
    nom = models.CharField(max_length=255)
    prenom = models.CharField(max_length=255)
    role = models.CharField(max_length=32, choices=Role.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    ufr = models.ForeignKey(Ufr, related_name="gestionnaires", on_delete=models.PROTECT, null=True, blank=True)

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
