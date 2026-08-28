from conflict_engine import services as conflict_engine
from conflict_engine.constants import PAUSES
from conflict_engine.types import CandidateCreneau
from core.ufr_scope import resolve_ufr_scope
from planning.models import ConflitJournal, Creneau
from referentiel.models import Salle

JOURS_OUVRABLES = 6  # lundi -> samedi
HEURE_OUVERTURE_MINUTES = 7 * 60
HEURE_FERMETURE_MINUTES = 18 * 60
MINUTES_PAUSES = sum(p["fin_minutes"] - p["debut_minutes"] for p in PAUSES)
MINUTES_DISPONIBLES_PAR_SALLE_PAR_SEMAINE = JOURS_OUVRABLES * (
    HEURE_FERMETURE_MINUTES - HEURE_OUVERTURE_MINUTES - MINUTES_PAUSES
)

# FR-DASH-01. Limitation assumée : Creneau est un gabarit hebdomadaire
# récurrent, sans date calendaire — "taux_occupation_salles" ignore donc le
# filtre de période. Les 3 autres statistiques sont dérivées d'un signal
# daté (AuditEntry.date_heure/ConflitJournal.detecte_le).
#
# INT-07 (V2) : chaque statistique est calculée sur le seul périmètre UFR de
# l'appelant (Gestionnaire : sa propre UFR ; Admin : tout ou une UFR choisie).


def stats(user, date_from=None, date_to=None, ufr_id_pour_admin=None) -> dict:
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)

    conflits_qs = ConflitJournal.objects.all()
    if date_from:
        conflits_qs = conflits_qs.filter(detecte_le__gte=date_from)
    if date_to:
        conflits_qs = conflits_qs.filter(detecte_le__lte=date_to)
    if not scope.toutes:
        conflits_qs = conflits_qs.filter(creneau_a__groupe__ufr_id__in=scope.ufr_ids)
    conflits_periode = list(conflits_qs)

    return {
        "tauxOccupationSalles": _calculer_taux_occupation(scope),
        "conflitsDetectes": len(conflits_periode),
        "conflitsResolus": _compter_resolus(conflits_periode),
        "coursAnnulesPeriode": _compter_annulations(scope, date_from, date_to),
    }


def _calculer_taux_occupation(scope) -> int:
    salles_qs = Salle.objects.all()
    creneaux_qs = Creneau.objects.exclude(statut="annule")
    if not scope.toutes:
        salles_qs = salles_qs.filter(ufr_id__in=scope.ufr_ids)
        creneaux_qs = creneaux_qs.filter(groupe__ufr_id__in=scope.ufr_ids)

    salles = salles_qs.count()
    if salles == 0:
        return 0

    minutes_occupees = sum(c.heure_fin_minutes - c.heure_debut_minutes for c in creneaux_qs.only("heure_debut_minutes", "heure_fin_minutes"))
    minutes_disponibles = salles * MINUTES_DISPONIBLES_PAR_SALLE_PAR_SEMAINE
    return min(100, round((minutes_occupees / minutes_disponibles) * 100))


def _compter_annulations(scope, date_from, date_to) -> int:
    from audit.models import AuditEntry

    qs = AuditEntry.objects.filter(creneau__isnull=False, action__startswith="Annulation")
    if date_from:
        qs = qs.filter(date_heure__gte=date_from)
    if date_to:
        qs = qs.filter(date_heure__lte=date_to)
    if not scope.toutes:
        qs = qs.filter(creneau__groupe__ufr_id__in=scope.ufr_ids)
    return qs.values("creneau_id").distinct().count()


def _compter_resolus(conflits: list[ConflitJournal]) -> int:
    if not conflits:
        return 0

    ids_concernes = set()
    for c in conflits:
        ids_concernes.add(c.creneau_a_id)
        if c.creneau_b_id:
            ids_concernes.add(c.creneau_b_id)

    creneaux = Creneau.objects.filter(id__in=ids_concernes).select_related("ue", "enseignant", "salle", "groupe")
    candidats_par_id: dict[str, CandidateCreneau] = {}
    for c in creneaux:
        candidats_par_id[c.id] = CandidateCreneau(
            id=c.id,
            jour=c.jour,
            heure_debut_minutes=c.heure_debut_minutes,
            heure_fin_minutes=c.heure_fin_minutes,
            statut=c.statut,
            ue_intitule=c.ue.intitule,
            enseignant_id=c.enseignant_id,
            enseignant_nom=c.enseignant.nom,
            enseignant_prenom=c.enseignant.prenom,
            groupe_id=c.groupe_id,
            groupe_nom=c.groupe.nom,
            groupe_effectif=c.groupe.etudiants.count(),
            salle_id=c.salle_id,
            salle_nom=c.salle.nom,
            salle_capacite=c.salle.capacite,
        )

    resolus = 0
    for c in conflits:
        candidat_a = candidats_par_id.get(c.creneau_a_id)
        if not candidat_a:
            resolus += 1  # le créneau n'existe plus dans l'état chargé — considéré résolu
            continue
        contexte = [candidats_par_id[c.creneau_b_id]] if c.creneau_b_id and c.creneau_b_id in candidats_par_id else []
        conflits_actuels = conflict_engine.evaluate(candidat_a, contexte)
        toujours_present = any(actuel.type == c.type for actuel in conflits_actuels)
        if not toujours_present:
            resolus += 1
    return resolus
