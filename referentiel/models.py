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
    """"annee_academique" (FR-REF-12) : année EN COURS de CE groupe précis.
    Une promotion se fait en créant un nouveau Groupe, jamais en modifiant
    celui-ci sur place.

    [V3.1, 2026-09-07] "effectif" est désormais une COLONNE, saisie par le
    Gestionnaire. Il était auparavant calculé (COUNT(Etudiant)), ce qui
    supposait de tenir à jour la liste nominative des inscrits de chaque
    groupe — un travail d'import considérable pour une seule valeur
    réellement consommée : le nombre, comparé à la capacité d'une salle
    (RM-02). Le référentiel des étudiants a donc été supprimé au profit de
    ce champ. Conséquence assumée : l'effectif n'est plus vérifiable par le
    système, il vaut ce que le Gestionnaire a saisi."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    nom = models.CharField(max_length=255)
    filiere = models.CharField(max_length=255)
    niveau = models.CharField(max_length=32)
    annee_academique = models.CharField(max_length=16)
    effectif = models.PositiveIntegerField(default=0)

    ufr = models.ForeignKey(Ufr, related_name="groupes", on_delete=models.PROTECT)

    class Meta:
        db_table = "groupe"
        indexes = [models.Index(fields=["ufr"])]
        constraints = [
            models.UniqueConstraint(Lower("nom"), name="groupe_nom_lower_unique"),
        ]

    def __str__(self) -> str:
        return self.nom


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


class Departement(models.Model):
    """[V3.2] Département (= « filière ») officiel d'un établissement.

    Introduit à la réception de la liste officielle de l'UJKZ le
    2026-09-07 : 53 départements répartis sur 12 établissements. Jusque-là,
    la filière d'un groupe était une chaîne libre, et les valeurs proposées
    à la saisie étaient déduites des groupes déjà créés — ce qui ne pouvait
    donner qu'un référentiel de qualité décroissante, chaque faute de frappe
    devenant une filière de plus dans la recherche publique (FR-PUB-02).

    Reste une chaîne dénormalisée sur `Groupe.filiere` plutôt qu'une clé
    étrangère, délibérément : un groupe garde le libellé de sa filière au
    moment de sa création, même si le département est renommé ou fermé
    ensuite. Un emploi du temps de l'an dernier ne doit pas changer de nom
    rétroactivement.
    """

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    ufr = models.ForeignKey(Ufr, related_name="departements", on_delete=models.CASCADE)
    libelle = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "departement"
        ordering = ["libelle"]
        indexes = [models.Index(fields=["ufr"])]
        constraints = [
            # Insensible à la casse : "Informatique" et "informatique" sont
            # le même département, et c'est précisément le doublon que ce
            # modèle existe pour empêcher.
            models.UniqueConstraint(Lower("libelle"), "ufr", name="departement_libelle_ufr_unique"),
        ]

    def __str__(self) -> str:
        return self.libelle
