import datetime
import uuid

from django.db import transaction
from django.utils import timezone
from django.db.models import F, Q
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import Enseignant, EnseignantUfr
from audit import services as audit_services
from conflict_engine import services as conflict_engine
from conflict_engine.types import CandidateCreneau
from core.exceptions_helpers import Conflict, ConflictWithBody
from core.time_utils import hhmm_to_minutes, minutes_to_hhmm
from core.ufr_scope import resolve_ufr_scope
from planning.models import JOURS_SEMAINE, Creneau, ConflitJournal
from public import diffusion
from referentiel.models import Groupe, Salle, UniteEnseignement

# [V3] EXEMPTION_TECHNIQUE_PERMUTATION a disparu avec le circuit de
# permutation (02_SRS §2.7 retirée) : c'était un marqueur posé sur une
# dérogation le temps d'échanger deux créneaux de même salle, et plus
# personne n'échange de créneaux. Le paramètre `exclude_ids` de
# write_one_in_transaction, qui n'existait que pour lui, part avec.

CRENEAU_SELECT_RELATED = ("ue", "enseignant", "salle", "groupe")


def _effectifs_par_groupe(groupe_ids: list[str]) -> dict[str, int]:
    # [V3.1] Lecture directe de la colonne : l'effectif est saisi par le
    # Gestionnaire depuis la suppression du référentiel des étudiants.
    uniques = list(set(groupe_ids))
    return dict(Groupe.objects.filter(id__in=uniques).values_list("id", "effectif"))


def _denormaliser(creneau: Creneau, effectif: int) -> dict:
    return {
        "id": creneau.id,
        "ue": {"id": creneau.ue.id, "code": creneau.ue.code, "intitule": creneau.ue.intitule, "ufrId": creneau.ue.ufr_id},
        "enseignant": {"id": creneau.enseignant.id, "nom": creneau.enseignant.nom, "prenom": creneau.enseignant.prenom},
        "groupe": {
            "id": creneau.groupe.id,
            "nom": creneau.groupe.nom,
            "departement": creneau.groupe.departement,
            "niveau": creneau.groupe.niveau,
            "anneeAcademique": creneau.groupe.annee_academique,
            "ufrId": creneau.groupe.ufr_id,
            "effectif": effectif,
        },
        "salle": {
            "id": creneau.salle.id,
            "nom": creneau.salle.nom,
            "capacite": creneau.salle.capacite,
            "typeUsage": creneau.salle.type_usage,
        },
        # [V4] La date réelle. "jour" reste fourni pour l'affichage, mais il
        # est DÉDUIT de la date côté modèle — jamais stocké deux fois.
        "date": creneau.date.isoformat(),
        "jour": creneau.jour,
        "heureDebut": minutes_to_hhmm(creneau.heure_debut_minutes),
        "heureFin": minutes_to_hhmm(creneau.heure_fin_minutes),
        "statut": creneau.statut,
        "motif": creneau.motif,
        # [V8.1] Spécialité affectée ; chaîne vide = tout le groupe.
        "specialite": creneau.specialite,
        # [V3] Le numéro de révision voyage jusqu'au client : c'est lui qui
        # permet de savoir qu'un créneau affiché est périmé sans comparer
        # champ à champ.
        "version": creneau.version,
    }


def _conflit_to_dto(c) -> dict:
    return {
        "type": c.type,
        "gravite": c.gravite,
        "titre": c.titre,
        "description": c.description,
        "creneauxConcernes": [x for x in [c.creneau_a_id, c.creneau_b_id] if x],
    }


# [V3] INT-06 est levée (tout programme est public, FR-PUB-01) : les
# branches "etudiant" et "enseignant" qui restreignaient la lecture ont
# disparu avec les rôles correspondants. Ce qui subsiste ici — et qui n'a
# rien perdu de sa force — c'est INT-07 : le cloisonnement inter-UFR du
# Gestionnaire, qui porte sur la GESTION, pas sur la consultation.
#
# La lecture publique ne passe pas par cette fonction : elle a sa propre
# projection dans public/services.py, délibérément séparée (cf.
# 04_Exigence_Architecture ligne 20).
def list_creneaux(user, groupe_id_filtre=None, enseignant_id_filtre=None, ufr_id_pour_admin=None, recherche=None):
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
    # [V3] FR-FILT-01/06 : filtrage côté serveur, jamais un tri du tout
    # dans le navigateur — les créneaux d'une UFR se comptent en milliers.
    if recherche:
        # FR-FILT-02 : `unaccent` avant `icontains` — sans quoi « reseaux »
        # ne trouverait pas « Réseaux », ce qui, sur un clavier de téléphone
        # sans accents, revient à ne pas avoir de recherche du tout.
        qs = qs.filter(
            Q(ue__intitule__unaccent__icontains=recherche)
            | Q(ue__code__unaccent__icontains=recherche)
            | Q(enseignant__nom__unaccent__icontains=recherche)
            | Q(salle__nom__unaccent__icontains=recherche)
            | Q(groupe__nom__unaccent__icontains=recherche)
        )

    creneaux = list(qs.select_related(*CRENEAU_SELECT_RELATED))
    effectifs = _effectifs_par_groupe([c.groupe_id for c in creneaux])
    return [_denormaliser(c, effectifs.get(c.groupe_id, 0)) for c in creneaux]


def find_one(creneau_id: str) -> dict:
    try:
        creneau = (
            Creneau.objects.select_related(*CRENEAU_SELECT_RELATED).get(id=creneau_id)
        )
    except Creneau.DoesNotExist:
        raise NotFound("Créneau introuvable.")
    effectif = _effectifs_par_groupe([creneau.groupe_id]).get(creneau.groupe_id, 0)
    return _denormaliser(creneau, effectif)


def _valider_date(valeur) -> datetime.date:
    """[V4] Une date réelle, jamais un dimanche.

    Il n'y a pas cours le dimanche à l'UJKZ. Refuser ici plutôt que de ranger
    la séance dans une septième colonne que la grille n'affiche pas : le
    Gestionnaire croirait avoir programmé un cours qui n'apparaît nulle part."""
    try:
        date = datetime.date.fromisoformat(valeur)
    except (TypeError, ValueError):
        raise ValidationError("Date invalide (format attendu : AAAA-MM-JJ).")
    if date.weekday() >= len(JOURS_SEMAINE):
        raise ValidationError("Il n'y a pas cours le dimanche.")
    return date


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
            date=c.date.isoformat(),
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
            # [V8.1] Sans elle, deux cours de spécialités différentes à la
            # même heure se bloqueraient l'un l'autre — cf. `_memes_etudiants`.
            specialite=c.specialite,
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
        groupe = Groupe.objects.get(id=item["groupeId"])
    except Groupe.DoesNotExist:
        raise NotFound("Groupe introuvable.")

    candidat = CandidateCreneau(
        id=item.get("id") or f"temp-{uuid.uuid4().hex}",
        date=item["date"],
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
        specialite=_specialite_de(item),
    )
    return candidat, {"ue_intitule": ue.intitule, "salle_nom": salle.nom}


def _specialite_de(item: dict) -> str:
    """[V8.1] Spécialité affectée au créneau, normalisée. Absente ou vide =
    le créneau concerne tout le groupe.

    Pas de vérification contre le référentiel des spécialités, délibérément,
    et pour la même raison que `Groupe.departement` et `Groupe.specialite`
    (FR-REF-34) : la valeur est choisie dans une liste déroulante alimentée
    par ce référentiel, et un créneau doit pouvoir conserver une spécialité
    que le Gestionnaire a refermée depuis. La cascade publique le prévoit —
    elle propose aussi les spécialités effectivement portées, pas seulement
    celles encore déclarées (public/services.py).
    """
    return (item.get("specialite") or "").strip()


def _libelle_action(action: str) -> str:
    return {"creation": "Création", "annulation": "Annulation", "modification": "Modification"}[action]


def _ecrire_un(item: dict, auteur: str, contexte: list[CandidateCreneau], user=None) -> str:
    statut = item.get("statut") or "normal"
    if statut != "normal" and not (item.get("motif") or "").strip():
        raise ValidationError("Le motif est obligatoire pour modifier ou annuler un créneau.")

    date = _valider_date(item.get("date"))
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
    deplacement: dict = {}

    if item.get("id"):
        try:
            existant = Creneau.objects.get(id=item["id"])
        except Creneau.DoesNotExist:
            raise NotFound("Créneau introuvable.")
        ancien_groupe_id = existant.groupe_id if existant.groupe_id != item["groupeId"] else None
        ancien_enseignant_id = existant.enseignant_id if existant.enseignant_id != item["enseignantId"] else None
        salle_changee = existant.salle_id != item["salleId"]
        action = "annulation" if statut == "annule" else "modification"

        # [V3] FR-PUB-07 : un déplacement d'horaire est le seul changement
        # qui passe inaperçu dans un agenda — l'événement bouge, sans rien
        # dire. On mémorise l'ancienne case pour y laisser un fantôme
        # pendant une semaine (voir public/ical.py).
        if existant.date != date or existant.heure_debut_minutes != heure_debut_minutes:
            deplacement = dict(
                ancienne_date=existant.date,
                ancien_heure_debut_minutes=existant.heure_debut_minutes,
                ancien_heure_fin_minutes=existant.heure_fin_minutes,
                deplace_le=timezone.now(),
            )
    else:
        action = "creation"

    derogation_motif_a_ecrire = item["motifDerogation"].strip() if conflits else None

    donnees = dict(
        ue_id=item["ueId"],
        enseignant_id=item["enseignantId"],
        groupe_id=item["groupeId"],
        salle_id=item["salleId"],
        date=date,
        heure_debut_minutes=heure_debut_minutes,
        heure_fin_minutes=heure_fin_minutes,
        statut=statut,
        motif=(item.get("motif") or "").strip() or None,
        specialite=_specialite_de(item),
        derogation_motif=derogation_motif_a_ecrire,
    )

    if item.get("id"):
        # [V3] INV-13/FR-PUB-06 : le numéro de révision monte à chaque
        # écriture. C'est ce qui fait qu'un agenda déjà abonné accepte de
        # remplacer l'événement qu'il détient au lieu de l'ignorer.
        # F("version") + 1 plutôt qu'une lecture puis une écriture : deux
        # gestionnaires qui modifient le même créneau au même instant ne
        # doivent pas produire deux fois la même révision.
        Creneau.objects.filter(id=item["id"]).update(version=F("version") + 1, **donnees, **deplacement)
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

    # [V3] INV-06 : la diffusion part dans la MÊME transaction que
    # l'écriture — jamais "créneau enregistré mais changement non diffusé",
    # ni l'inverse. Ce qui change par rapport à la V2, c'est le destinataire :
    # il n'y a plus d'utilisateurs nominatifs à résoudre en base, seulement
    # un groupe dont le programme public vient de changer.
    diffusion.on_creneau_changed(
        creneau_id=creneau_id,
        action=action,
        ue_intitule=refs["ue_intitule"],
        date=date.isoformat(),
        heure_debut=item["heureDebut"],
        heure_fin=item["heureFin"],
        salle_nom=refs["salle_nom"],
        salle_changee=salle_changee,
        groupe_id=item["groupeId"],
        groupe_id_precedent=ancien_groupe_id,
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
    return write_one_in_transaction(item, auteur, user)


def write_one_in_transaction(item: dict, auteur: str, user=None) -> str:
    return _ecrire_un(item, auteur, _charger_candidats(), user=user)


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
        "date": existant.date.isoformat(),
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
        "date": existant.date.isoformat(),
        "heureDebut": minutes_to_hhmm(existant.heure_debut_minutes),
        "heureFin": minutes_to_hhmm(existant.heure_fin_minutes),
        "statut": "annule",
        "motif": motif,
    }
    return write_one(item, auteur, user)
