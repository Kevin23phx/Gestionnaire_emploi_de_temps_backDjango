from django.conf import settings
from django.utils import timezone

from accounts.models import Session
from accounts.session_utils import generate_session_token, hash_session_token


def _cookie_kwargs() -> dict:
    return dict(
        httponly=True,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        secure=settings.SESSION_COOKIE_SECURE,
        path="/",
        max_age=int(settings.SESSION_TTL.total_seconds()),
    )


def issue(utilisateur_id: str, response) -> None:
    raw_token = generate_session_token()
    Session.objects.create(
        utilisateur_id=utilisateur_id,
        token_hash=hash_session_token(raw_token),
        expires_at=timezone.now() + settings.SESSION_TTL,
    )
    response.set_cookie(settings.SESSION_COOKIE_NAME, raw_token, **_cookie_kwargs())


def revoke_toutes(utilisateur_id: str) -> int:
    """[V8.3] Supprime TOUTES les sessions d'un compte.

    Appelée au changement de mot de passe. Sans elle, changer son mot de
    passe ne fermerait aucune des sessions déjà ouvertes : quelqu'un qui
    serait resté connecté sur un poste de la scolarité — ou qui aurait
    obtenu le cookie — y resterait, et le geste qui sert précisément à
    reprendre la main sur son compte n'aurait aucun effet là où ça compte.

    L'appelant réémet ensuite une session pour le navigateur courant, pour
    que le Gestionnaire ne soit pas déconnecté de l'écran où il vient de
    changer son mot de passe.
    """
    supprimees, _ = Session.objects.filter(utilisateur_id=utilisateur_id).delete()
    return supprimees


def revoke(raw_token: str | None, response) -> None:
    if raw_token:
        Session.objects.filter(token_hash=hash_session_token(raw_token)).delete()
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
