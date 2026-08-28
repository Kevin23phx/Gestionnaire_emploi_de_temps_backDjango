from django.db import IntegrityError, transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import Role, Utilisateur
from core.ufr_scope import resolve_ufr_scope, ufr_filter_kwargs
from referentiel.models import Etudiant, Groupe


def list_etudiants(user, annee_academique: str | None, filiere: str | None, ufr_id_pour_admin: str | None = None):
    """FR-REF-11 : filtrage par année académique et par filière
    ("département" dans le vocabulaire du porteur de projet), en plus du
    périmètre UFR habituel (INT-07)."""
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    qs = Etudiant.objects.filter(**ufr_filter_kwargs(scope)).order_by("nom", "prenom")
    if annee_academique:
        qs = qs.filter(annee_academique=annee_academique)
    if filiere:
        qs = qs.filter(filiere__iexact=filiere)
    return qs


def import_etudiants(lignes: list[dict], groupe_id: str | None, ufr_id: str) -> dict:
    """ufr_id : toujours celui du Gestionnaire authentifié (INT-07), jamais
    choisi par le client."""
    if groupe_id:
        try:
            groupe = Groupe.objects.get(id=groupe_id)
        except Groupe.DoesNotExist:
            raise NotFound("Groupe introuvable.")
        if groupe.ufr_id != ufr_id:
            raise PermissionDenied("Ce groupe appartient à une autre UFR.")

    invalides: list[str] = []
    candidats: list[dict] = []
    for ligne in lignes:
        ine = (ligne.get("ine") or "").strip()
        nom = (ligne.get("nom") or "").strip()
        prenom = (ligne.get("prenom") or "").strip()
        annee_academique = (ligne.get("anneeAcademique") or "").strip()
        if not ine or not nom or not prenom or not annee_academique:
            invalides.append(ine or "(INE manquant)")
            continue
        candidats.append(
            {
                "ine": ine,
                "nom": nom,
                "prenom": prenom,
                "filiere": (ligne.get("filiere") or "").strip(),
                "niveau": (ligne.get("niveau") or "").strip(),
                "annee_academique": annee_academique,
            }
        )

    # FR-REF-08 : un INE déjà présent est TOUJOURS un doublon, quelle que
    # soit l'UFR ou l'année visées par ce nouvel import — c'est aussi ce qui
    # empêche structurellement un étudiant de se retrouver inscrit dans deux
    # UFR à la fois (INT-08).
    ines_existants = set(
        Etudiant.objects.filter(ine__in=[c["ine"] for c in candidats]).values_list("ine", flat=True)
    )

    doublons: list[str] = []
    a_creer = []
    for c in candidats:
        if c["ine"] in ines_existants:
            doublons.append(c["ine"])
        else:
            a_creer.append(c)

    crees: list[Etudiant] = []
    for candidat in a_creer:
        try:
            with transaction.atomic():
                etudiant = Etudiant.objects.create(**candidat, groupe_id=groupe_id, ufr_id=ufr_id)
                # motDePasseHash absent : compte non activé, comme pour un
                # enseignant nouvellement provisionné (FR-AUTH-03).
                Utilisateur.objects.create(
                    identifiant=etudiant.ine,
                    nom=etudiant.nom,
                    prenom=etudiant.prenom,
                    role=Role.ETUDIANT,
                    etudiant=etudiant,
                )
            crees.append(etudiant)
        except IntegrityError:
            # Course entre deux imports concurrents du même INE, jamais vue
            # par le pré-contrôle ci-dessus — reclassé en doublon plutôt que
            # de faire échouer tout le lot.
            doublons.append(candidat["ine"])

    return {"etudiants": crees, "doublons": doublons, "invalides": invalides}


def affecter(etudiant_ids: list[str], groupe_id: str | None, ufr_id: str):
    """INT-07/INT-08 : un Gestionnaire ne peut affecter à un groupe de sa
    propre UFR que des étudiants déjà rattachés à cette même UFR — jamais
    "récupérer" un étudiant d'une autre UFR (seul l'Admin le peut, via
    transferer_ufr, FR-ADMIN-05).

    FR-REF-15 : affecter un étudiant à un nouveau groupe synchronise son
    niveau/filiere sur ceux du groupe de destination — c'est le mécanisme
    de PROMOTION."""
    groupe = None
    if groupe_id:
        try:
            groupe = Groupe.objects.get(id=groupe_id)
        except Groupe.DoesNotExist:
            raise NotFound("Groupe introuvable.")
        if groupe.ufr_id != ufr_id:
            raise PermissionDenied("Ce groupe appartient à une autre UFR.")

    etudiants = list(Etudiant.objects.filter(id__in=etudiant_ids))
    if any(e.ufr_id != ufr_id for e in etudiants):
        raise PermissionDenied(
            "Au moins un étudiant sélectionné appartient à une autre UFR — seul l'Admin peut transférer un étudiant d'UFR."
        )

    if groupe:
        Etudiant.objects.filter(id__in=etudiant_ids).update(
            groupe_id=groupe_id, niveau=groupe.niveau, filiere=groupe.filiere
        )
    else:
        Etudiant.objects.filter(id__in=etudiant_ids).update(groupe_id=None)

    return Etudiant.objects.filter(id__in=etudiant_ids)


def transferer_ufr(etudiant_id: str, nouvel_ufr_id: str) -> Etudiant:
    """FR-ADMIN-05/INT-08 : seul point d'entrée pour changer l'UFR d'un
    étudiant déjà inscrit — réservé à l'Admin par la vue (@require_roles).
    Le groupe est toujours réinitialisé : un groupe de l'ancienne UFR n'a
    structurellement aucun sens dans la nouvelle (INT-07)."""
    from core.models import Ufr

    try:
        etudiant = Etudiant.objects.get(id=etudiant_id)
    except Etudiant.DoesNotExist:
        raise NotFound("Étudiant introuvable.")

    if not Ufr.objects.filter(id=nouvel_ufr_id).exists():
        raise NotFound("UFR introuvable.")

    if etudiant.ufr_id == nouvel_ufr_id:
        raise ValidationError("Cet étudiant est déjà rattaché à cette UFR.")

    etudiant.ufr_id = nouvel_ufr_id
    etudiant.groupe_id = None
    etudiant.save(update_fields=["ufr_id", "groupe_id"])
    return etudiant
