from django.conf import settings
from django.utils import timezone

from accounts.models import Session
from accounts.session_utils import generate_session_token, hash_session_token


def _cookie_kwargs() -> dict:
    return dict(
        httponly=True,
        samesite="Lax",
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


def revoke(raw_token: str | None, response) -> None:
    if raw_token:
        Session.objects.filter(token_hash=hash_session_token(raw_token)).delete()
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
