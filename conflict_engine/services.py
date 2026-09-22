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


def _memes_etudiants(a: CandidateCreneau, b: CandidateCreneau) -> bool:
    """[V8.1] Deux créneaux d'un MÊME groupe concernent-ils les mêmes
    étudiants ?

    C'est la question que posait implicitement le conflit « groupe » —
    « cette promotion est affectée à deux cours simultanés » — et à laquelle
    la réponse était forcément oui tant qu'un groupe était indivisible.
    Depuis que le créneau porte une affectation (planning/models.py), elle
    ne l'est plus :

    - aucun des deux n'a de spécialité → les deux concernent toute la
      promotion : conflit ;
    - un seul en a une → le cours commun concerne AUSSI les étudiants de
      cette spécialité, qui ne peuvent pas être aux deux : conflit ;
    - les deux en ont une, la même → même sous-population : conflit ;
    - les deux en ont une, différentes → sous-populations disjointes, deux
      salles, deux enseignants : **pas de conflit**. C'est tout l'objet de
      la réforme du 2026-09-21, et le cas normal d'une L2 de portail où
      Mathématiques et Chimie tombent à la même heure.

    Les conflits de SALLE et d'ENSEIGNANT ne passent pas par ici, et c'est
    voulu : une salle ne peut pas héberger deux cours simultanés, ni un
    enseignant être à deux endroits, quelle que soit la spécialité des
    étudiants en face. Seule l'assistance des ÉTUDIANTS se divise.
    """
    if not a.specialite or not b.specialite:
        return True
    return a.specialite.casefold() == b.specialite.casefold()


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
        if candidat.groupe_id == autre.groupe_id and _memes_etudiants(candidat, autre):
            # [V8.1] Le titre nomme la sous-population réellement en cause :
            # « Double cours — L2 Médecine » est trompeur quand seuls les
            # étudiants d'une spécialité sont concernés, et le Gestionnaire
            # chercherait l'erreur dans le mauvais emploi du temps.
            qui = candidat.groupe_nom
            if candidat.specialite or autre.specialite:
                qui = f"{candidat.groupe_nom} — {candidat.specialite or autre.specialite}"
            conflits.append(
                ConflitDetecteResult(
                    type="groupe",
                    gravite="bloquant",
                    titre=f"Double cours — {qui}",
                    description=f"{qui} est affecté à deux cours simultanés ({plage}).",
                    creneau_a_id=candidat.id,
                    creneau_b_id=autre.id,
                )
            )

    if candidat.groupe_effectif > candidat.salle_capacite:
        plage = f"{candidat.date} {minutes_to_hhmm(candidat.heure_debut_minutes)}-{minutes_to_hhmm(candidat.heure_fin_minutes)}"
        # [V8.1] L'alerte reste émise pour un créneau affecté à une
        # spécialité, mais le dit : l'effectif connu est celui de TOUTE la
        # promotion (FR-REF-19 — une valeur saisie par groupe, il n'en
        # existe aucune par spécialité), alors que le cours ne réunit
        # qu'une partie des étudiants. Le chiffre surestime donc, et
        # l'alerte peut être un faux positif.
        #
        # Ne pas l'émettre du tout serait pire : ce serait désactiver en
        # silence la seule vérification de capacité du système dès qu'un
        # cours est spécialisé, y compris quand la salle est réellement
        # trop petite. On la laisse, et on donne au Gestionnaire de quoi
        # juger — plutôt qu'un avertissement muet sur lequel il ne peut
        # rien conclure.
        if candidat.specialite:
            description = (
                f"Groupe {candidat.groupe_nom} ({candidat.groupe_effectif} pers. au total) assigné dans une "
                f"salle de {candidat.salle_capacite} places ({plage}). Ce cours ne concerne que la spécialité "
                f"« {candidat.specialite} » : l'effectif connu est celui de toute la promotion, le nombre réel "
                f"d'étudiants attendus est plus faible."
            )
        else:
            description = (
                f"Groupe {candidat.groupe_nom} ({candidat.groupe_effectif} pers.) assigné dans une salle de "
                f"{candidat.salle_capacite} places ({plage})."
            )
        conflits.append(
            ConflitDetecteResult(
                type="capacite",
                gravite="avertissement",
                titre=f"Capacité dépassée — {candidat.salle_nom}",
                description=description,
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
