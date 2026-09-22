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


# Index 0 = lundi (datetime.date.weekday()). Le dimanche (index 6) est
# volontairement absent : il n'y a pas cours le dimanche à l'UJKZ, et une
# date qui tomberait ce jour-là est refusée à la saisie plutôt que rangée
# dans une septième case que personne ne regarde.
JOURS_SEMAINE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]


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

    # [V4] Une DATE réelle, plus un jour de semaine récurrent.
    #
    # À l'UJKZ, l'emploi du temps n'est pas fixé pour le semestre : il est
    # publié semaine par semaine, en fin de semaine précédente, et le contenu
    # change d'une semaine à l'autre (cette semaine Maths, la suivante
    # Algorithmique). Le modèle « jour de semaine + récurrence », hérité des
    # universités où le programme est arrêté pour tout un semestre, ne
    # pouvait pas représenter ça : il produisait un cours répété à
    # l'identique de la rentrée aux examens, vacances comprises.
    #
    # Le jour de la semaine reste utile pour l'affichage — il se DÉDUIT de la
    # date (voir la propriété `jour`), il n'est plus stocké : deux champs
    # pour la même information finissent toujours par diverger.
    date = models.DateField()
    heure_debut_minutes = models.PositiveIntegerField()
    heure_fin_minutes = models.PositiveIntegerField()

    # [V8.1, 2026-09-21] AFFECTATION du créneau à une spécialité.
    #
    # Vide = le créneau concerne TOUT le groupe (tronc commun). Renseignée =
    # il ne concerne que les étudiants de cette spécialité-là.
    #
    # ## Pourquoi ici et pas sur le Groupe
    #
    # La V8 permettait déjà de porter une spécialité sur le Groupe, ce qui
    # obligeait à créer autant de groupes que de spécialités — quatre « L2
    # Médecine » là où la scolarité n'en voit qu'un. Chaque cours du tronc
    # commun devait alors être ressaisi quatre fois, et une correction
    # d'horaire appliquée quatre fois aussi. Retour du porteur de projet le
    # 2026-09-21 : un groupe UNIQUE, et c'est le créneau qu'on affecte.
    #
    # C'est aussi la modélisation juste. Une promotion de L2 Médecine est
    # une cohorte : elle a des cours communs à tous et des cours propres à
    # chaque spécialité. Ce qui se spécialise, c'est l'ENSEIGNEMENT, pas la
    # cohorte — la porter sur le groupe forçait à nier les cours communs.
    #
    # Chaîne dénormalisée, comme `Groupe.specialite` et pour la même raison
    # (INV-21) : un créneau garde le libellé qu'avait sa spécialité le jour
    # de sa saisie, même si le Gestionnaire la renomme ou la referme.
    #
    # ## Conséquence sur la détection de conflits
    #
    # Deux créneaux du même groupe au même moment cessaient d'être
    # automatiquement un conflit : « Maths » et « Chimie » le mardi à 8h
    # sont deux cours simultanés pour deux sous-populations disjointes. La
    # règle est reprise dans conflict_engine/services.py — sans elle, le
    # mécanisme serait inutilisable, chaque cours de spécialité bloquant
    # tous les autres.
    specialite = models.CharField(max_length=255, blank=True, default="")

    statut = models.CharField(max_length=16, choices=StatutCreneau.choices, default=StatutCreneau.NORMAL)
    motif = models.TextField(null=True, blank=True)
    derogation_motif = models.TextField(null=True, blank=True)

    # [V3] INV-13 / FR-PUB-06 : numéro de révision, incrémenté à CHAQUE
    # écriture du créneau. Alimente le champ SEQUENCE du flux calendrier.
    # Ce n'est pas une commodité : Google Agenda et Outlook comparent
    # SEQUENCE pour décider si un événement déjà importé doit être remplacé.
    # Sans incrément, une annulation publiée est purement et simplement
    # ignorée par l'agenda du visiteur — l'abonnement semblerait fonctionner
    # tout en ne transmettant jamais le seul message qui compte.
    version = models.PositiveIntegerField(default=1)

    # [V3] FR-PUB-07 : trace du dernier déplacement, et rien d'autre. Quand
    # un cours change de date ou d'heure, l'événement se contente de bouger
    # dans l'agenda du visiteur — un déplacement est silencieux par nature,
    # l'étudiant continue de venir à l'ancienne heure. Ces champs permettent
    # de laisser un événement "fantôme" à l'ancienne case, qui dit où le
    # cours est parti. Écrasés à chaque nouveau déplacement : on ne garde
    # jamais qu'un seul ancien horaire, le plus récent, parce que c'est le
    # seul auquel quelqu'un puisse encore se présenter.
    ancienne_date = models.DateField(null=True, blank=True)
    ancien_heure_debut_minutes = models.PositiveIntegerField(null=True, blank=True)
    ancien_heure_fin_minutes = models.PositiveIntegerField(null=True, blank=True)
    deplace_le = models.DateTimeField(null=True, blank=True)

    @property
    def jour(self) -> str:
        """Jour de la semaine, déduit de la date. Dimanche n'apparaît jamais
        dans un programme : la validation refuse cette date en amont."""
        return JOURS_SEMAINE[self.date.weekday()]

    class Meta:
        db_table = "creneau"
        indexes = [
            models.Index(fields=["salle", "date"]),
            models.Index(fields=["enseignant", "date"]),
            # Le plus sollicité de tous : afficher le programme d'un groupe
            # pour une semaine donnée, côté public comme côté gestion.
            models.Index(fields=["groupe", "date"]),
            # [V8.1] Le programme public d'une spécialité : (groupe, date)
            # filtré sur la spécialité. Sans cet index, chaque consultation
            # d'une L2 spécialisée relirait tous les créneaux du groupe.
            models.Index(fields=["groupe", "specialite", "date"]),
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
