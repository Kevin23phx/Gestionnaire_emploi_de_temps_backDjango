from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from rest_framework.exceptions import APIException, NotFound, ValidationError

from accounts import session_service
from accounts.models import Utilisateur

_hasher = PasswordHasher()

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


def login(identifiant: str, mot_de_passe: str, response) -> dict:
    """"Identifiant inconnu" et "mot de passe incorrect" restent le même
    message générique — un attaquant ne doit pas pouvoir distinguer les
    deux rien qu'en essayant de se connecter. "Compte pas encore activé"
    reçoit un message explicite et distinct (choix délibéré)."""
    try:
        utilisateur = Utilisateur.objects.get(identifiant=identifiant)
    except Utilisateur.DoesNotExist:
        raise IdentifiantOuMotDePasseIncorrect()

    if not utilisateur.mot_de_passe_hash:
        raise CompteNonActive()

    try:
        _hasher.verify(utilisateur.mot_de_passe_hash, mot_de_passe)
    except VerifyMismatchError:
        raise IdentifiantOuMotDePasseIncorrect()

    session_service.issue(utilisateur.id, response)
    return {"role": utilisateur.role}


def activate(identifiant: str, nouveau_mot_de_passe: str, confirmation_mot_de_passe: str, response) -> dict:
    if not nouveau_mot_de_passe or nouveau_mot_de_passe != confirmation_mot_de_passe:
        raise ValidationError("Les deux mots de passe ne correspondent pas.")

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
