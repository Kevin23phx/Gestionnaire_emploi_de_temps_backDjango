from rest_framework.exceptions import ValidationError

from conflict_engine.constants import PAUSES
from conflict_engine.types import CandidateCreneau, ConflitDetecteResult
from core.time_utils import minutes_to_hhmm

# Version faisant foi du moteur de détection de conflits (FR-CONF-01→04),
# décalque du web/src/lib/conflict-detection.ts frontend. Fonction pure : ne
# touche jamais la base, ne lève jamais d'exception pour un conflit détecté
# (c'est à l'appelant — planning/services.py — de décider quoi en faire).
#
# Un créneau "annulé" libère la salle/l'enseignant/le groupe — il est exclu
# de toutes les vérifications (bloquant ET capacité).


def _chevauchent(a: CandidateCreneau, b: CandidateCreneau) -> bool:
    # [V4] Comparaison sur la DATE : deux cours du lundi ne se gênent que
    # s'il s'agit du même lundi. Avec l'ancien modèle récurrent, la question
    # ne se posait pas — tous les lundis étaient le même.
    if a.date != b.date:
        return False
    return a.heure_debut_minutes < b.heure_fin_minutes and b.heure_debut_minutes < a.heure_fin_minutes


def evaluate(
    candidat: CandidateCreneau, contexte: list[CandidateCreneau], exclude_id: str | None = None
) -> list[ConflitDetecteResult]:
    conflits: list[ConflitDetecteResult] = []
    if candidat.statut == "annule":
        return conflits

    autres = [c for c in contexte if c.id != candidat.id and c.id != exclude_id and c.statut != "annule"]

    for autre in autres:
        if not _chevauchent(candidat, autre):
            continue
        plage = f"{candidat.date} {minutes_to_hhmm(candidat.heure_debut_minutes)}-{minutes_to_hhmm(candidat.heure_fin_minutes)}"

        if candidat.salle_id == autre.salle_id:
            conflits.append(
                ConflitDetecteResult(
                    type="salle",
                    gravite="bloquant",
                    titre=f"Double réservation — {candidat.salle_nom}",
                    description=f"{candidat.ue_intitule} et {autre.ue_intitule} sur le même créneau ({plage}).",
                    creneau_a_id=candidat.id,
                    creneau_b_id=autre.id,
                )
            )
        if candidat.enseignant_id == autre.enseignant_id:
            conflits.append(
                ConflitDetecteResult(
                    type="enseignant",
                    gravite="bloquant",
                    titre=f"Double affectation — {candidat.enseignant_prenom} {candidat.enseignant_nom}",
                    description=f"{candidat.enseignant_prenom} {candidat.enseignant_nom} est affecté à deux créneaux simultanés.",
                    creneau_a_id=candidat.id,
                    creneau_b_id=autre.id,
                )
            )
        if candidat.groupe_id == autre.groupe_id:
            conflits.append(
                ConflitDetecteResult(
                    type="groupe",
                    gravite="bloquant",
                    titre=f"Double cours — {candidat.groupe_nom}",
                    description=f"{candidat.groupe_nom} est affecté à deux cours simultanés.",
                    creneau_a_id=candidat.id,
                    creneau_b_id=autre.id,
                )
            )

    if candidat.groupe_effectif > candidat.salle_capacite:
        plage = f"{candidat.date} {minutes_to_hhmm(candidat.heure_debut_minutes)}-{minutes_to_hhmm(candidat.heure_fin_minutes)}"
        conflits.append(
            ConflitDetecteResult(
                type="capacite",
                gravite="avertissement",
                titre=f"Capacité dépassée — {candidat.salle_nom}",
                description=(
                    f"Groupe {candidat.groupe_nom} ({candidat.groupe_effectif} pers.) assigné dans une salle de "
                    f"{candidat.salle_capacite} places ({plage})."
                ),
                creneau_a_id=candidat.id,
                creneau_b_id=None,
            )
        )

    return conflits


def assert_no_pause_overlap(heure_debut_minutes: int, heure_fin_minutes: int) -> None:
    """Défense en profondeur : le frontend découpe déjà une plage saisie
    autour des pauses avant l'envoi, mais le serveur ne doit jamais faire
    confiance à ce découpage côté client."""
    for pause in PAUSES:
        chevauche = heure_debut_minutes < pause["fin_minutes"] and pause["debut_minutes"] < heure_fin_minutes
        if chevauche:
            raise ValidationError(
                f"Ce créneau chevauche une pause fixe ({pause['label']} "
                f"{minutes_to_hhmm(pause['debut_minutes'])}-{minutes_to_hhmm(pause['fin_minutes'])})."
            )
