"""Fixtures partagées — équivalent Python de test/utils/fixtures.ts côté
backend NestJS de référence. Une UFR de test implicite et partagée
("ufr-test") est provisionnée par défaut pour ne pas alourdir les tests qui
ne portent pas spécifiquement sur le cloisonnement multi-UFR."""

import datetime
import json

from argon2 import PasswordHasher
from django.test import Client

from accounts.models import Enseignant, EnseignantUfr, Role, Utilisateur
from core.models import Ufr
from referentiel.models import Groupe, Salle, UniteEnseignement

_hasher = PasswordHasher()
_hash_partage = None


def hash_mot_de_passe_test() -> str:
    global _hash_partage
    if _hash_partage is None:
        _hash_partage = _hasher.hash("password")
    return _hash_partage


# [V3] Toute UFR de test porte une période académique englobant la date du
# jour : sans elle, une annulation datée serait rejetée par INT-11 et le flux
# calendrier n'aurait aucune borne de récurrence (FR-REF-16).
PERIODE_TEST = {
    "periode_libelle": "Semestre de test",
    "periode_debut": datetime.date.today() - datetime.timedelta(days=30),
    "periode_fin": datetime.date.today() + datetime.timedelta(days=120),
}


def ufr_par_defaut() -> str:
    Ufr.objects.get_or_create(id="ufr-test", defaults={"nom": "UFR Test", "sigle": "test", **PERIODE_TEST})
    return "ufr-test"


def creer_ufr(ufr_id: str, nom: str, sigle: str) -> Ufr:
    return Ufr.objects.create(id=ufr_id, nom=nom, sigle=sigle, **PERIODE_TEST)


def prochain(jour: str, apres: datetime.date | None = None) -> datetime.date:
    """Prochaine date tombant sur ce jour de semaine — les tests d'annulation
    datée ont besoin d'une date réelle et cohérente avec le jour du créneau."""
    index = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"].index(jour)
    depart = apres or datetime.date.today()
    return depart + datetime.timedelta(days=(index - depart.weekday()) % 7 or 7)


def creer_ue(intitule: str, code: str = "COD1", ufr_id: str | None = None, niveau: str = "L3") -> UniteEnseignement:
    return UniteEnseignement.objects.create(intitule=intitule, code=code, niveau=niveau, ufr_id=ufr_id or ufr_par_defaut())


def creer_salle(nom: str, capacite: int = 50, type_usage: str = "propre", ufr_id: str | None = None) -> Salle:
    return Salle.objects.create(nom=nom, batiment="Bâtiment Test", capacite=capacite, type_usage=type_usage, ufr_id=ufr_id or ufr_par_defaut())


def creer_groupe(
    nom: str, filiere: str = "Informatique", niveau: str = "L3", ufr_id: str | None = None,
    annee_academique: str = "2025-2026", effectif: int = 0,
) -> Groupe:
    """[V3.1] "effectif" est une valeur saisie, plus un COUNT(Etudiant) : les
    tests de conflit de capacité la posent directement au lieu de créer des
    étudiants un par un."""
    return Groupe.objects.create(
        nom=nom, filiere=filiere, niveau=niveau, annee_academique=annee_academique,
        effectif=effectif, ufr_id=ufr_id or ufr_par_defaut(),
    )


def creer_enseignant(nom: str, prenom: str, ufr_id: str | None = None) -> Enseignant:
    enseignant = Enseignant.objects.create(nom=nom, prenom=prenom)
    EnseignantUfr.objects.create(enseignant=enseignant, ufr_id=ufr_id or ufr_par_defaut())
    return enseignant


def affecter_enseignant_ufr(enseignant: Enseignant, ufr_id: str | None = None) -> EnseignantUfr:
    return EnseignantUfr.objects.create(enseignant=enseignant, ufr_id=ufr_id or ufr_par_defaut())


def creer_compte(
    identifiant: str, nom: str, prenom: str, role: str, active: bool = True, ufr_id: str | None = None,
) -> Utilisateur:
    """[V3] Les paramètres `etudiant`/`enseignant` ont disparu avec les rôles
    correspondants : un compte n'est plus jamais adossé à une fiche de
    référentiel (INV-03, deux rôles)."""
    return Utilisateur.objects.create(
        identifiant=identifiant,
        mot_de_passe_hash=hash_mot_de_passe_test() if active else None,
        nom=nom,
        prenom=prenom,
        role=role,
        ufr_id=(ufr_id or ufr_par_defaut()) if role == Role.SCOLARITE else None,
    )


def login(client: Client, identifiant: str, mot_de_passe: str = "password"):
    return client.post("/api/auth/login", data=json.dumps({"identifiant": identifiant, "motDePasse": mot_de_passe}), content_type="application/json")


def post_json(client: Client, path: str, data: dict):
    return client.post(path, data=json.dumps(data), content_type="application/json")


def patch_json(client: Client, path: str, data: dict):
    return client.patch(path, data=json.dumps(data), content_type="application/json")
