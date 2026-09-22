from django.db import models
from django.db.models.functions import Lower

from core.models import Ufr
from core.utils import generate_id


class TypeUsageSalle(models.TextChoices):
    """[2026-09] Usage pédagogique de la salle — retour des gestionnaires
    lors de la présentation : l'ancien enum (propre/commune/louée/gratuite)
    décrivait en réalité qui gère la salle. Ce champ dit À QUOI la salle
    sert, seule classification qui reste (cf. Salle, plus bas : la salle
    n'a plus d'UFR propriétaire du tout)."""

    COURS = "cours", "Cours"
    TD = "td", "TD"
    TP = "tp", "TP"
    LABORATOIRE = "laboratoire", "Laboratoire"


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

    # [V8] Spécialité suivie par ce groupe — vide quand le niveau n'en
    # propose aucune. Chaîne dénormalisée et non une FK vers `Specialite`,
    # exactement pour la même raison que `departement` juste au-dessus : le
    # groupe garde le libellé qu'avait sa spécialité le jour de sa création,
    # même si le Gestionnaire la renomme ou la ferme ensuite. Un emploi du
    # temps de l'an dernier ne doit pas changer de nom rétroactivement.
    #
    # Vide par défaut, et jamais NULL : "pas de spécialité à ce niveau" et
    # "spécialité pas encore renseignée" ne sont pas deux états différents
    # ici — dans les deux cas le groupe n'en porte aucune, et une colonne
    # nullable obligerait chaque lecture à traiter les deux cas.
    specialite = models.CharField(max_length=255, blank=True, default="")

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
    """[2026-09] Retour des gestionnaires : plus d'appartenance à une UFR
    (ni "structure_gestionnaire" UFR/DEP, ni FK `ufr`). Une salle est un
    référentiel unique, université entière — n'importe quel Gestionnaire ou
    l'Admin peut en créer une et toutes les utiliser, précisément pour
    couvrir le cas où les salles propres à une UFR sont toutes occupées.
    C'est une exception délibérée, ciblée sur ce seul référentiel, à
    INT-07 (cf. 03_Contrat_Invariants_Campus_Manager.md [V7]) : le
    cloisonnement inter-UFR reste entier sur le planning, les conflits et
    l'audit — seule la liste des salles devient partagée. Seule
    l'unicité du nom est encore garantie (`salle_nom_lower_unique`).

    Pas de champ "bâtiment" non plus : retour des gestionnaires, ce n'est
    pas une information nécessaire à la saisie d'une salle."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    nom = models.CharField(max_length=255)
    capacite = models.PositiveIntegerField()
    type_usage = models.CharField(max_length=16, choices=TypeUsageSalle.choices)

    class Meta:
        db_table = "salle"
        constraints = [
            models.UniqueConstraint(Lower("nom"), name="salle_nom_lower_unique"),
        ]

    def __str__(self) -> str:
        return self.nom


class UniteEnseignement(models.Model):
    """[2026-09] Pas de champ "niveau" séparé : retour des gestionnaires,
    le code du cours porte déjà cette information, un champ dédié ferait
    doublon.

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


class Specialite(models.Model):
    """[V8, 2026-09-21] Spécialité ouverte par un département à un NIVEAU
    donné — la « réforme des parcours » demandée par le chef de projet.

    ## Ce qui change

    Jusqu'ici l'écran disait « Parcours » pour désigner en réalité le niveau
    du cycle LMD (L1…M2) : un seul mot pour deux notions, et aucune place
    pour la troisième. Le vocabulaire est remis d'aplomb :

    - **Niveau** = L1, L2, L3, M1, M2 — liste close, la même partout
      (`referentiel.services.groupes.NIVEAUX`), jamais saisie.
    - **Spécialité** = ce modèle — liste ouverte, créée par le Gestionnaire,
      rattachée à un département ET à un niveau.

    ## Pourquoi le rattachement porte sur le COUPLE (département, niveau)

    C'est le cas MPCI qui l'impose, et c'est précisément l'exemple donné par
    le chef de projet : en L1, MPCI est un tronc commun sans aucun choix ;
    c'est en L2 que l'étudiant se répartit entre Mathématiques, Physique,
    Chimie et Informatique. Rattacher la spécialité au seul département
    ferait apparaître ces quatre choix dès la L1, où ils n'existent pas.

    Ce n'est pas une particularité locale : la recherche menée le
    2026-09-21 sur les licences « portail » (MPCI à Aix-Marseille, MPCSI à
    Lille, MPMEI à Brest) montre le même schéma partout — une première
    année pluridisciplinaire commune, puis une spécialisation progressive.
    Le niveau est donc constitutif de l'existence de la spécialité, pas une
    simple propriété de celle-ci.

    ## Pourquoi une entité, et pas une colonne libre sur Groupe

    Même raisonnement que `Departement` (FR-REF-22) : une chaîne libre
    ressaisie à chaque groupe redeviendrait un référentiel de qualité
    décroissante — « Informatique », « informatique » et « Info » feraient
    trois spécialités dans la cascade publique, face auxquelles l'étudiant
    ne saurait pas laquelle est la sienne. C'est le Gestionnaire qui déclare
    la spécialité une fois ; les groupes la sélectionnent ensuite.

    Pas de FK vers `Ufr` : l'établissement se lit par `departement.ufr`. Le
    dupliquer ouvrirait la porte à l'incohérence (une spécialité rattachée à
    l'UFR/SEA via un département de l'UFR/SDS), exactement ce que
    `Ufr.sigle_affiche` évite déjà en se calculant plutôt qu'en se stockant.
    """

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    departement = models.ForeignKey(
        "referentiel.Departement", related_name="specialites", on_delete=models.CASCADE
    )
    # Volontairement une CharField libre et non un TextChoices : `NIVEAUX`
    # vit dans referentiel/services/groupes.py, d'où le reste du projet le
    # lit déjà (cascade publique, passage d'année). Le dupliquer en choices
    # ici obligerait à une migration le jour où le cycle évolue, pour une
    # valeur que le service valide déjà à l'entrée.
    niveau = models.CharField(max_length=32)
    libelle = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "specialite"
        ordering = ["libelle"]
        indexes = [models.Index(fields=["departement", "niveau"])]
        constraints = [
            # Insensible à la casse, comme pour Departement : « Informatique »
            # et « informatique » sont la même spécialité, et c'est ce
            # doublon-là que ce modèle existe pour empêcher.
            #
            # Scopée au COUPLE (département, niveau) et non au seul
            # département : « Informatique » peut légitimement exister en L2
            # et en L3 du même département — ce sont deux choix distincts
            # offerts à deux cohortes distinctes, pas un doublon.
            models.UniqueConstraint(
                "departement", "niveau", Lower("libelle"), name="specialite_libelle_dep_niveau_unique"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.libelle} ({self.niveau})"
