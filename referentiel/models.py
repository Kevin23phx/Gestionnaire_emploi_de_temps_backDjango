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
    # [V5] Nommé "departement" — c'était "filiere" jusqu'ici, et le double
    # vocabulaire avec le modèle `Departement` (le référentiel officiel dont
    # cette valeur est censée reprendre un `libelle`) semait la confusion.
    # Reste une chaîne dénormalisée et non une FK, délibérément : un groupe
    # garde le libellé de son département au moment de sa création, même si
    # celui-ci est renommé ou fermé ensuite (cf. Departement, plus haut).
    departement = models.CharField(max_length=255)
    niveau = models.CharField(max_length=32)
    annee_academique = models.CharField(max_length=16)
    effectif = models.PositiveIntegerField(default=0)

    # [V6] FR-REF-12 le disait depuis la V2 ("une promotion se fait en créant
    # un nouveau Groupe, jamais en modifiant celui-ci sur place") sans que le
    # mécanisme existe jamais : le Gestionnaire ressaisissait le groupe de
    # zéro chaque rentrée. `promu_de` relie le groupe de l'année N+1 à celui
    # dont il descend en N — trace de filiation, jamais modifiée après coup
    # (comme un Creneau déplacé garde son fantôme, cf. V4). OneToOne : un
    # groupe ne peut être promu qu'une seule fois (empêche de créer deux L2
    # à partir du même L1 par erreur de double clic).
    promu_de = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="groupe_suivant"
    )

    ufr = models.ForeignKey(Ufr, related_name="groupes", on_delete=models.PROTECT)

    class Meta:
        db_table = "groupe"
        indexes = [models.Index(fields=["ufr"])]
        constraints = [
            # [V6] Unicité PAR ANNÉE ACADÉMIQUE, plus globale. Avant le
            # passage de niveau (FR-REF-29), un nom de groupe historique ne
            # restait jamais indéfiniment en base au même niveau qu'un
            # groupe actif — la question ne se posait pas. Depuis, le groupe
            # d'une année promue (ex. "L1 Médecine - Groupe A", 2025-2026)
            # est délibérément conservé (historique, jamais supprimé). Une
            # unicité globale interdirait alors pour toujours de nommer ainsi
            # la PROCHAINE promotion de L1 (nouveaux admis 2026-2027) — un nom
            # de cohorte est censé se répéter d'année en année, pas être
            # consommé une fois pour toutes.
            models.UniqueConstraint(Lower("nom"), "annee_academique", name="groupe_nom_lower_annee_unique"),
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
    affiché à côté de l'intitulé, indépendant de l'année académique.

    [V3.3] "departements" : à quels départements ce cours est dispensé.
    **Plusieurs**, et c'est le point : un cours mutualisé (« Tronc Commun
    SEA », une UE d'anglais, une statistique de base) est enseigné à
    plusieurs départements à la fois. Le modéliser par un simple champ
    unique obligerait à recréer le même cours autant de fois qu'il y a de
    départements concernés — donc à maintenir N fiches pour une seule
    réalité, et à ne jamais pouvoir répondre à « qui suit ce cours ? ».

    Relation directe vers Departement, sans table intermédiaire porteuse de
    données : le rattachement n'a pas d'attribut propre (ni volume horaire,
    ni coefficient) tant que personne ne l'a demandé.
    """

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    code = models.CharField(max_length=64, null=True, blank=True)
    intitule = models.CharField(max_length=255)
    niveau = models.CharField(max_length=32)

    ufr = models.ForeignKey(Ufr, related_name="ues", on_delete=models.PROTECT)
    departements = models.ManyToManyField("referentiel.Departement", related_name="cours", blank=True)

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

    Reste une chaîne dénormalisée sur `Groupe.departement` plutôt qu'une clé
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
