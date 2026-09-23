import logging

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from rest_framework.exceptions import APIException, NotFound, ValidationError

from accounts import session_service
from accounts.models import Utilisateur

_hasher = PasswordHasher()

# [V8.8] OWASP A09 « Security Logging and Monitoring Failures ». Les échecs
# d'authentification n'étaient tracés nulle part : le journal d'audit ne
# consigne que les actions métier réussies d'un utilisateur identifié, et
# une tentative refusée n'a précisément pas d'utilisateur. Une campagne de
# force brute ne laissait donc aucune trace exploitable — on ne pouvait ni
# la détecter, ni l'attester après coup.
#
# Ce que la ligne contient est délibérément pauvre : l'identifiant VISÉ et
# l'adresse d'origine, jamais le mot de passe essayé ni aucun fragment.
# Un journal qui contient des mots de passe devient lui-même le secret à
# protéger.
logger = logging.getLogger(__name__)

IDENTIFIANT_OU_MOT_DE_PASSE_INCORRECT = "Identifiant ou mot de passe incorrect."


class CompteNonActive(APIException):
    status_code = 401
    default_detail = {
        "erreur": "Ce compte n'est pas encore activé. Rendez-vous sur la page d'activation pour définir votre mot de passe.",
        "codeErreur": "compte_non_active",
    }


class IdentifiantOuMotDePasseIncorrect(APIException):
    status_code = 401
    default_detail = IDENTIFIANT_OU_MOT_DE_PASSE_INCORRECT


# [V8.3] Longueur minimale d'un mot de passe.
#
# Huit caractères : c'est le plancher recommandé par le NIST (SP 800-63B)
# pour un secret choisi par un humain, et le seul critère que cette
# publication retient vraiment — elle déconseille explicitement d'imposer
# une composition (majuscule + chiffre + symbole), qui pousse aux
# variations prévisibles du type « Passw0rd! » sans rien ajouter de solide.
#
# Le contexte le justifie aussi : une douzaine de comptes nominatifs, sur
# un outil interne dont la surface d'écriture est déjà cloisonnée par UFR
# (INT-07). Un plancher trop haut ici produirait surtout des mots de passe
# écrits sur un papier collé à l'écran.
LONGUEUR_MIN_MOT_DE_PASSE = 8


def _valider_mot_de_passe(nouveau: str, confirmation: str, identifiant: str | None = None) -> None:
    """Règles communes à l'activation d'un compte et au changement de mot
    de passe — écrites une seule fois, sinon les deux chemins finiraient
    par diverger et l'un des deux serait le maillon faible."""
    if not nouveau or nouveau != confirmation:
        raise ValidationError("Les deux mots de passe ne correspondent pas.")
    if len(nouveau) < LONGUEUR_MIN_MOT_DE_PASSE:
        raise ValidationError(
            f"Le mot de passe doit contenir au moins {LONGUEUR_MIN_MOT_DE_PASSE} caractères."
        )
    # Un mot de passe égal à l'identifiant est la première chose qu'essaie
    # quiconque connaît la convention de nommage des comptes
    # (`scolarite.<sigle>`, FR-ADMIN-02) — c'est-à-dire tout le monde, elle
    # est publique.
    if identifiant and nouveau.strip().casefold() == identifiant.strip().casefold():
        raise ValidationError("Le mot de passe ne peut pas être identique à l'identifiant du compte.")


def changer_mot_de_passe(
    utilisateur_id: str, actuel: str, nouveau: str, confirmation: str, response
) -> dict:
    """[V8.3] FR-AUTH-07 — un Gestionnaire change son propre mot de passe.

    Jusqu'ici le seul moyen de définir un mot de passe était l'activation
    (FR-AUTH-03), qui ne fonctionne qu'UNE fois et seulement sur un compte
    jamais activé. Conséquence à l'usage : le mot de passe posé au
    provisionnement restait en place indéfiniment, et il était connu de
    quiconque avait vu le script d'amorçage. Un compte dont on ne peut pas
    changer le secret n'est pas vraiment un compte personnel.

    ## Trois garde-fous

    1. **Le mot de passe actuel est exigé**, même si l'utilisateur est déjà
       authentifié : un poste laissé ouvert dans un couloir suffirait
       sinon à s'emparer du compte pour de bon. C'est la session qui dit
       QUI change, jamais la requête — `utilisateur_id` vient du cookie.
    2. **Le nouveau doit différer de l'actuel.** Un « changement » qui n'en
       est pas un laisserait croire à une rotation effectuée.
    3. **Toutes les sessions sont fermées**, y compris celles d'autres
       appareils, puis une seule est réémise pour le navigateur courant —
       voir `session_service.revoke_toutes`.
    """
    try:
        utilisateur = Utilisateur.objects.get(id=utilisateur_id)
    except Utilisateur.DoesNotExist:
        raise NotFound("Compte introuvable.")

    if not utilisateur.mot_de_passe_hash:
        raise ValidationError(
            "Ce compte n'a pas encore de mot de passe. Passez par la page d'activation."
        )

    try:
        _hasher.verify(utilisateur.mot_de_passe_hash, actuel or "")
    except VerifyMismatchError:
        # Message distinct de celui du formulaire de connexion : ici
        # l'identité est déjà établie par la session, il n'y a donc rien à
        # divulguer en nommant le champ fautif — et le taire ferait chercher
        # l'erreur dans le mauvais champ.
        raise ValidationError("Mot de passe actuel incorrect.")

    _valider_mot_de_passe(nouveau, confirmation, utilisateur.identifiant)

    if nouveau == actuel:
        raise ValidationError("Le nouveau mot de passe doit être différent de l'actuel.")

    utilisateur.mot_de_passe_hash = _hasher.hash(nouveau)
    utilisateur.save(update_fields=["mot_de_passe_hash"])

    session_service.revoke_toutes(utilisateur.id)
    session_service.issue(utilisateur.id, response)
    return {"ok": True}


def _tracer_echec(identifiant: str, motif: str, adresse: str | None) -> None:
    logger.warning(
        "Connexion refusée — identifiant=%r motif=%s origine=%s", identifiant, motif, adresse or "inconnue"
    )


def login(identifiant: str, mot_de_passe: str, response, adresse: str | None = None) -> dict:
    """"Identifiant inconnu" et "mot de passe incorrect" restent le même
    message générique — un attaquant ne doit pas pouvoir distinguer les
    deux rien qu'en essayant de se connecter. "Compte pas encore activé"
    reçoit un message explicite et distinct (choix délibéré)."""
    try:
        utilisateur = Utilisateur.objects.get(identifiant=identifiant)
    except Utilisateur.DoesNotExist:
        _tracer_echec(identifiant, "identifiant inconnu", adresse)
        raise IdentifiantOuMotDePasseIncorrect()

    if not utilisateur.mot_de_passe_hash:
        _tracer_echec(identifiant, "compte non activé", adresse)
        raise CompteNonActive()

    try:
        _hasher.verify(utilisateur.mot_de_passe_hash, mot_de_passe)
    except VerifyMismatchError:
        _tracer_echec(identifiant, "mot de passe incorrect", adresse)
        raise IdentifiantOuMotDePasseIncorrect()

    session_service.issue(utilisateur.id, response)
    return {"role": utilisateur.role}


def activate(identifiant: str, nouveau_mot_de_passe: str, confirmation_mot_de_passe: str, response) -> dict:
    # [V8.3] Même politique qu'au changement de mot de passe : une règle
    # appliquée à un seul des deux chemins ne protège rien, il suffirait de
    # passer par l'autre.
    _valider_mot_de_passe(nouveau_mot_de_passe, confirmation_mot_de_passe, identifiant)

    try:
        utilisateur = Utilisateur.objects.get(identifiant=identifiant)
    except Utilisateur.DoesNotExist:
        raise NotFound("Identifiant inconnu. Ce compte doit d'abord être créé par la scolarité de votre UFR.")

    # FR-AUTH-03 : l'activation ne définit un mot de passe qu'UNE SEULE
    # fois, pour un compte pré-provisionné sans mot de passe — sinon
    # quiconque connaît un identifiant pourrait écraser silencieusement le
    # mot de passe d'un compte déjà actif (prise de compte pure et simple).
    if utilisateur.mot_de_passe_hash:
        raise ValidationError(
            "Ce compte est déjà activé. Connectez-vous normalement, ou contactez la scolarité si vous avez oublié votre mot de passe."
        )

    utilisateur.mot_de_passe_hash = _hasher.hash(nouveau_mot_de_passe)
    utilisateur.save(update_fields=["mot_de_passe_hash"])

    session_service.issue(utilisateur.id, response)
    return {"role": utilisateur.role}


def logout(raw_token: str | None, response) -> None:
    session_service.revoke(raw_token, response)
