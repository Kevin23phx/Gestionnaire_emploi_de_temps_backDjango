import datetime

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from accounts.models import Role, Utilisateur
from audit import services as audit_services
from core.exceptions_helpers import Conflict
from core.models import TypeEtablissement, Ufr


def list_ufrs():
    """FR-ADMIN-06 : ouvert à tout rôle authentifié — sert aussi de source
    pour les sélecteurs d'UFR côté frontend."""
    ufrs = Ufr.objects.prefetch_related("gestionnaires").order_by("nom")
    resultat = []
    for u in ufrs:
        gestionnaire = next((g for g in u.gestionnaires.all() if g.role == Role.SCOLARITE), None)
        resultat.append(
            {
                "id": u.id,
                "nom": u.nom,
                "sigle": u.sigle,
                # [V3.2] Le type distingue UFR, institut et école doctorale ;
                # "sigleAffiche" porte la règle de préfixe ("UFR/SH" mais
                # "IBAM"), composée côté serveur pour n'exister qu'une fois.
                "type": u.type,
                "sigleAffiche": u.sigle_affiche,
                "gestionnaire": (
                    {"identifiant": gestionnaire.identifiant, "active": gestionnaire.mot_de_passe_hash is not None}
                    if gestionnaire
                    else None
                ),
            }
        )
    return resultat


def create(nom: str, sigle: str, type_etablissement: str, auteur: str) -> Ufr:
    """[V3.2] Crée un établissement — UFR, institut ou école doctorale.

    L'identifiant technique garde le préfixe historique `ufr-` quel que soit
    le type : il est référencé par toutes les données existantes et par les
    identifiants de comptes, le changer casserait plus qu'il ne clarifierait.
    """
    sigle_normalise = sigle.strip().lower()
    if Ufr.objects.filter(sigle=sigle_normalise).exists():
        raise Conflict("Un établissement porte déjà ce sigle.")
    if type_etablissement not in TypeEtablissement.values:
        raise ValidationError("Type d'établissement inconnu.")
    ufr = Ufr.objects.create(
        id=f"ufr-{sigle_normalise}", nom=nom.strip(), sigle=sigle_normalise, type=type_etablissement
    )
    audit_services.record(auteur, f"Création établissement — {ufr.sigle_affiche} ({ufr.nom})")
    return ufr


def create_gestionnaire(ufr_id: str, nom: str, prenom: str, auteur: str) -> dict:
    """FR-ADMIN-02 : identifiant scolarite.<sigle>, jamais choisi par
    l'Admin. Un compte Gestionnaire par UFR (l'unicité de l'identifiant
    dérivé l'impose de toute façon ; vérifié explicitement pour un message
    clair)."""
    try:
        ufr = Ufr.objects.get(id=ufr_id)
    except Ufr.DoesNotExist:
        raise NotFound("UFR introuvable.")

    if Utilisateur.objects.filter(ufr_id=ufr_id, role=Role.SCOLARITE).exists():
        raise Conflict("Cette UFR a déjà un compte Gestionnaire.")

    identifiant = f"scolarite.{ufr.sigle}"
    # mot_de_passe_hash absent : compte pré-provisionné, non activé, à
    # activer par le Gestionnaire lui-même (FR-AUTH-03).
    Utilisateur.objects.create(identifiant=identifiant, nom=nom.strip(), prenom=prenom.strip(), role=Role.SCOLARITE, ufr=ufr)
    audit_services.record(auteur, f"Création compte Gestionnaire — {identifiant} ({ufr.nom})")

    return {"identifiant": identifiant, "ufr": ufr}
