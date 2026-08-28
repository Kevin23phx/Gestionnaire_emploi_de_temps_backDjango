import uuid

from django.db import transaction
from django.db.models import Count, Q
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import Enseignant, EnseignantUfr
from audit import services as audit_services
from conflict_engine import services as conflict_engine
from conflict_engine.types import CandidateCreneau
from core.exceptions_helpers import ConflictWithBody
from core.time_utils import hhmm_to_minutes, minutes_to_hhmm
from core.ufr_scope import resolve_ufr_scope
from notifications import services as notification_services
from planning.models import ConflitJournal, Creneau
from referentiel.models import Groupe, Salle, UniteEnseignement

# Marqueur technique, jamais montré à l'utilisateur : voir _ecrire_un pour
# le problème qu'il résout (permutation entre deux créneaux de la même
# salle). Une chaîne fixe et reconnaissable pour que demandes/services.py
# puisse la nettoyer précisément sans jamais toucher une vraie dérogation.
EXEMPTION_TECHNIQUE_PERMUTATION = "__exemption_technique_permutation__"

CRENEAU_SELECT_RELATED = ("ue", "enseignant", "salle", "groupe")


def _effectifs_par_groupe(groupe_ids: list[str]) -> dict[str, int]:
    uniques = list(set(groupe_ids))
    lignes = Groupe.objects.filter(id__in=uniques).annotate(effectif=Count("etudiants"))
    return {g.id: g.effectif for g in lignes}


def _denormaliser(creneau: Creneau, effectif: int) -> dict:
    return {
        "id": creneau.id,
        "ue": {"id": creneau.ue.id, "code": creneau.ue.code, "intitule": creneau.ue.intitule, "niveau": creneau.ue.niveau, "ufrId": creneau.ue.ufr_id},
        "enseignant": {"id": creneau.enseignant.id, "nom": creneau.enseignant.nom, "prenom": creneau.enseignant.prenom},
        "groupe": {
            "id": creneau.groupe.id,
            "nom": creneau.groupe.nom,
            "filiere": creneau.groupe.filiere,
            "niveau": creneau.groupe.niveau,
            "anneeAcademique": creneau.groupe.annee_academique,
            "ufrId": creneau.groupe.ufr_id,
            "effectif": effectif,
        },
        "salle": {
            "id": creneau.salle.id,
            "nom": creneau.salle.nom,
            "batiment": creneau.salle.batiment,
            "capacite": creneau.salle.capacite,
            "structureGestionnaire": creneau.salle.structure_gestionnaire,
            "ufrId": creneau.salle.ufr_id,
            "typeUsage": creneau.salle.type_usage,
        },
        "jour": creneau.jour,
        "heureDebut": minutes_to_hhmm(creneau.heure_debut_minutes),
        "heureFin": minutes_to_hhmm(creneau.heure_fin_minutes),
        "statut": creneau.statut,
        "motif": creneau.motif,
    }


def _conflit_to_dto(c) -> dict:
    return {
        "type": c.type,
        "gravite": c.gravite,
        "titre": c.titre,
        "description": c.description,
        "creneauxConcernes": [x for x in [c.creneau_a_id, c.creneau_b_id] if x],
    }


# INT-06 : un étudiant ne voit jamais que son propre groupe, un enseignant
# que son propre planning — le filtre est appliqué ici, en ignorant
# silencieusement tout paramètre fourni par le client pour ces deux rôles.
def list_creneaux(user, groupe_id_filtre=None, enseignant_id_filtre=None, ufr_id_pour_admin=None):
    if user.role == "etudiant":
        groupe_id = user.etudiant.groupe_id if user.etudiant else "__aucun__"
        qs = Creneau.objects.filter(groupe_id=groupe_id or "__aucun__")
    elif user.role == "enseignant":
        enseignant_id = user.enseignant.id if user.enseignant else "__aucun__"
        qs = Creneau.objects.filter(enseignant_id=enseignant_id)
    else:
        # INT-07 (V2) : un Gestionnaire ne voit jamais les créneaux d'une
        # autre UFR, même en le demandant explicitement. L'Admin voit tout
        # (FR-ADMIN-03), ou une seule UFR choisie (FR-ADMIN-06).
        scope = resolve_ufr_scope(user, ufr_id_pour_admin)
        qs = Creneau.objects.all()
        if not scope.toutes:
            qs = qs.filter(groupe__ufr_id__in=scope.ufr_ids)
        if groupe_id_filtre:
            qs = qs.filter(groupe_id=groupe_id_filtre)
        if enseignant_id_filtre:
            qs = qs.filter(enseignant_id=enseignant_id_filtre)

    creneaux = list(qs.select_related(*CRENEAU_SELECT_RELATED))
    effectifs = _effectifs_par_groupe([c.groupe_id for c in creneaux])
    return [_denormaliser(c, effectifs.get(c.groupe_id, 0)) for c in creneaux]


def find_one(creneau_id: str) -> dict:
    try:
        creneau = Creneau.objects.select_related(*CRENEAU_SELECT_RELATED).get(id=creneau_id)
    except Creneau.DoesNotExist:
        raise NotFound("Créneau introuvable.")
    effectif = _effectifs_par_groupe([creneau.groupe_id]).get(creneau.groupe_id, 0)
    return _denormaliser(creneau, effectif)


# Vue DÉLIBÉRÉMENT non filtrée par INT-06 — nécessaire pour qu'un enseignant
# puisse choisir, au moment de proposer une permutation, un créneau
# appartenant à un AUTRE enseignant.
def list_programme_complet(user) -> list[dict]:
    scope = resolve_ufr_scope(user)
    qs = Creneau.objects.exclude(statut="annule")
    if not scope.toutes:
        qs = qs.filter(groupe__ufr_id__in=scope.ufr_ids)
    creneaux = list(qs.select_related(*CRENEAU_SELECT_RELATED))
    effectifs = _effectifs_par_groupe([c.groupe_id for c in creneaux])
    return [_denormaliser(c, effectifs.get(c.groupe_id, 0)) for c in creneaux]


def _valider_horaire(heure_debut_minutes: int, heure_fin_minutes: int) -> None:
    if heure_fin_minutes <= heure_debut_minutes:
        raise ValidationError("L'heure de fin doit être après l'heure de début.")
    conflict_engine.assert_no_pause_overlap(heure_debut_minutes, heure_fin_minutes)


def _charger_candidats(exclude_id: str | None = None) -> list[CandidateCreneau]:
    qs = Creneau.objects.select_related(*CRENEAU_SELECT_RELATED)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    creneaux = list(qs)
    effectifs = _effectifs_par_groupe([c.groupe_id for c in creneaux])
    return [
        CandidateCreneau(
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
            groupe_effectif=effectifs.get(c.groupe_id, 0),
            salle_id=c.salle_id,
            salle_nom=c.salle.nom,
            salle_capacite=c.salle.capacite,
        )
        for c in creneaux
    ]


def _construire_candidat(item: dict, statut: str, heure_debut_minutes: int, heure_fin_minutes: int) -> tuple[CandidateCreneau, dict]:
    try:
        ue = UniteEnseignement.objects.get(id=item["ueId"])
    except UniteEnseignement.DoesNotExist:
        raise NotFound("Unité d'enseignement introuvable.")
    try:
        enseignant = Enseignant.objects.get(id=item["enseignantId"])
    except Enseignant.DoesNotExist:
        raise NotFound("Enseignant introuvable.")
    try:
        salle = Salle.objects.get(id=item["salleId"])
    except Salle.DoesNotExist:
        raise NotFound("Salle introuvable.")
    try:
        groupe = Groupe.objects.annotate(effectif=Count("etudiants")).get(id=item["groupeId"])
    except Groupe.DoesNotExist:
        raise NotFound("Groupe introuvable.")

    candidat = CandidateCreneau(
        id=item.get("id") or f"temp-{uuid.uuid4().hex}",
        jour=item["jour"],
        heure_debut_minutes=heure_debut_minutes,
        heure_fin_minutes=heure_fin_minutes,
        statut=statut,
        ue_intitule=ue.intitule,
        enseignant_id=enseignant.id,
        enseignant_nom=enseignant.nom,
        enseignant_prenom=enseignant.prenom,
        groupe_id=groupe.id,
        groupe_nom=groupe.nom,
        groupe_effectif=groupe.effectif,
        salle_id=salle.id,
        salle_nom=salle.nom,
        salle_capacite=salle.capacite,
    )
    return candidat, {"ue_intitule": ue.intitule, "salle_nom": salle.nom}


def _libelle_action(action: str) -> str:
    return {"creation": "Création", "annulation": "Annulation", "modification": "Modification"}[action]


def _ecrire_un(
    item: dict, auteur: str, contexte: list[CandidateCreneau], exemption_technique: bool = False, user=None
) -> str:
    statut = item.get("statut") or "normal"
    if statut != "normal" and not (item.get("motif") or "").strip():
        raise ValidationError("Le motif est obligatoire pour modifier ou annuler un créneau.")

    heure_debut_minutes = hhmm_to_minutes(item["heureDebut"])
    heure_fin_minutes = hhmm_to_minutes(item["heureFin"])
    _valider_horaire(heure_debut_minutes, heure_fin_minutes)

    # INT-07 (V2) : un Gestionnaire n'écrit jamais un créneau dont le
    # groupe appartient à une autre UFR que la sienne.
    if user is not None and user.role == "scolarite":
        groupe = Groupe.objects.filter(id=item["groupeId"]).first()
        if groupe and groupe.ufr_id != user.ufr_id:
            raise PermissionDenied("Ce groupe appartient à une autre UFR.")

        # FR-REF-06 (révisé 2026-08-27) : jamais bloquant — l'affectation
        # s'enregistre automatiquement au premier usage, pour que le
        # planning agrégé de l'enseignant reste exact.
        EnseignantUfr.objects.get_or_create(enseignant_id=item["enseignantId"], ufr_id=user.ufr_id)

    candidat, refs = _construire_candidat(item, statut, heure_debut_minutes, heure_fin_minutes)

    conflits = conflict_engine.evaluate(candidat, contexte, item.get("id"))
    if conflits and not (item.get("motifDerogation") or "").strip():
        raise ConflictWithBody(
            {"erreur": "Conflit détecté — dérogation requise pour enregistrer malgré tout.", "conflits": [_conflit_to_dto(c) for c in conflits]}
        )

    ancien_groupe_id = None
    ancien_enseignant_id = None
    salle_changee = False

    if item.get("id"):
        try:
            existant = Creneau.objects.get(id=item["id"])
        except Creneau.DoesNotExist:
            raise NotFound("Créneau introuvable.")
        ancien_groupe_id = existant.groupe_id if existant.groupe_id != item["groupeId"] else None
        ancien_enseignant_id = existant.enseignant_id if existant.enseignant_id != item["enseignantId"] else None
        salle_changee = existant.salle_id != item["salleId"]
        action = "annulation" if statut == "annule" else "modification"
    else:
        action = "creation"

    derogation_motif_a_ecrire = None
    if conflits:
        derogation_motif_a_ecrire = item["motifDerogation"].strip()
    elif exemption_technique:
        derogation_motif_a_ecrire = EXEMPTION_TECHNIQUE_PERMUTATION

    donnees = dict(
        ue_id=item["ueId"],
        enseignant_id=item["enseignantId"],
        groupe_id=item["groupeId"],
        salle_id=item["salleId"],
        jour=item["jour"],
        heure_debut_minutes=heure_debut_minutes,
        heure_fin_minutes=heure_fin_minutes,
        statut=statut,
        motif=(item.get("motif") or "").strip() or None,
        derogation_motif=derogation_motif_a_ecrire,
    )

    if item.get("id"):
        Creneau.objects.filter(id=item["id"]).update(**donnees)
        creneau_id = item["id"]
    else:
        creneau = Creneau.objects.create(**donnees)
        creneau_id = creneau.id

    if conflits:
        _enregistrer_conflits(conflits, creneau_id, item["motifDerogation"].strip(), auteur)
        audit_services.record(
            auteur, f"{_libelle_action(action)} créneau — {refs['ue_intitule']} (dérogation conflit)", item.get("motifDerogation"), creneau_id
        )

    audit_services.record(auteur, f"{_libelle_action(action)} créneau — {refs['ue_intitule']}", item.get("motif"), creneau_id)

    notification_services.on_creneau_changed(
        creneau_id=creneau_id,
        action=action,
        ue_intitule=refs["ue_intitule"],
        jour=item["jour"],
        heure_debut=item["heureDebut"],
        heure_fin=item["heureFin"],
        salle_nom=refs["salle_nom"],
        salle_changee=salle_changee,
        groupe_id=item["groupeId"],
        enseignant_id=item["enseignantId"],
        groupe_id_precedent=ancien_groupe_id,
        enseignant_id_precedent=ancien_enseignant_id,
    )

    return creneau_id


def _enregistrer_conflits(conflits, creneau_id: str, derogation_motif: str, detecte_par: str) -> None:
    ConflitJournal.objects.bulk_create(
        [
            ConflitJournal(
                type=c.type,
                gravite=c.gravite,
                titre=c.titre,
                description=c.description,
                creneau_a_id=creneau_id,
                creneau_b_id=c.creneau_b_id,
                derogation_motif=derogation_motif,
                detecte_par=detecte_par,
            )
            for c in conflits
        ]
    )


def verifier(items: list[dict]) -> list[dict]:
    """Dry-run : mêmes vérifications que l'écriture, aucune persistance."""
    contexte = _charger_candidats()
    conflits_par_item: list[list[dict]] = []

    for item in items:
        statut = item.get("statut") or "normal"
        heure_debut_minutes = hhmm_to_minutes(item["heureDebut"])
        heure_fin_minutes = hhmm_to_minutes(item["heureFin"])
        _valider_horaire(heure_debut_minutes, heure_fin_minutes)

        candidat, _ = _construire_candidat(item, statut, heure_debut_minutes, heure_fin_minutes)
        conflits = conflict_engine.evaluate(candidat, contexte, item.get("id"))
        conflits_par_item.append([_conflit_to_dto(c) for c in conflits])

        contexte = [c for c in contexte if c.id != candidat.id] + [candidat]

    return [c for sous_liste in conflits_par_item for c in sous_liste]


@transaction.atomic
def write_batch(items: list[dict], auteur: str, user) -> list[str]:
    ids_ecrits = []
    contexte = _charger_candidats()
    for item in items:
        creneau_id = _ecrire_un(item, auteur, contexte, user=user)
        ids_ecrits.append(creneau_id)
        contexte = _charger_candidats()
    return ids_ecrits


@transaction.atomic
def write_one(item: dict, auteur: str, user) -> str:
    return write_one_in_transaction(item, auteur, [], user)


def write_one_in_transaction(item: dict, auteur: str, exclude_ids: list[str] | None = None, user=None) -> str:
    exclude_ids = exclude_ids or []
    contexte = _charger_candidats()
    if exclude_ids:
        contexte = [c for c in contexte if c.id not in exclude_ids]
    return _ecrire_un(item, auteur, contexte, exemption_technique=bool(exclude_ids), user=user)


def charger_comme_dto(creneau_id: str) -> dict:
    try:
        existant = Creneau.objects.get(id=creneau_id)
    except Creneau.DoesNotExist:
        raise NotFound("Créneau introuvable.")
    return {
        "id": existant.id,
        "ueId": existant.ue_id,
        "enseignantId": existant.enseignant_id,
        "groupeId": existant.groupe_id,
        "salleId": existant.salle_id,
        "jour": existant.jour,
        "heureDebut": minutes_to_hhmm(existant.heure_debut_minutes),
        "heureFin": minutes_to_hhmm(existant.heure_fin_minutes),
        "statut": existant.statut,
        "motif": existant.motif,
    }


@transaction.atomic
def annuler(creneau_id: str, motif: str, auteur: str, user) -> str:
    try:
        existant = Creneau.objects.get(id=creneau_id)
    except Creneau.DoesNotExist:
        raise NotFound("Créneau introuvable.")

    item = {
        "id": creneau_id,
        "ueId": existant.ue_id,
        "enseignantId": existant.enseignant_id,
        "groupeId": existant.groupe_id,
        "salleId": existant.salle_id,
        "jour": existant.jour,
        "heureDebut": minutes_to_hhmm(existant.heure_debut_minutes),
        "heureFin": minutes_to_hhmm(existant.heure_fin_minutes),
        "statut": "annule",
        "motif": motif,
    }
    return write_one(item, auteur, user)
