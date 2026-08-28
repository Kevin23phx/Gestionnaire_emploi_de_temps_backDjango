from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import BaseAuthentication

from accounts.authenticated_user import AuthenticatedUser
from accounts.models import Session
from accounts.session_utils import hash_session_token


class CookieSessionAuthentication(BaseAuthentication):
    """Équivalent de SessionAuthGuard (NestJS) : lit le cookie cm_session,
    vérifie la session en base (jamais un JWT auto-suffisant), attache
    l'utilisateur re-lu à chaque requête. Retourne None (pas d'exception) si
    aucun cookie/session valide — IsAuthenticatedCM décide alors du 401,
    exactement comme @Public() est la seule échappatoire côté NestJS."""

    def authenticate_header(self, request):
        # Sans ceci, DRF rétrograde silencieusement NotAuthenticated (401)
        # en 403 dès qu'aucun schéma d'authentification à en-tête n'est
        # déclaré (APIView.handle_exception) — la valeur elle-même n'est
        # jamais interprétée côté client, seule sa présence compte ici.
        return "Cookie"

    def authenticate(self, request):
        raw_token = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        if not raw_token:
            return None

        token_hash = hash_session_token(raw_token)
        try:
            session = (
                Session.objects.select_related("utilisateur", "utilisateur__etudiant", "utilisateur__enseignant")
                .get(token_hash=token_hash)
            )
        except Session.DoesNotExist:
            return None

        if session.expires_at < timezone.now():
            return None

        utilisateur = session.utilisateur
        enseignant_ufr_ids = []
        if utilisateur.enseignant_id:
            enseignant_ufr_ids = list(
                utilisateur.enseignant.ufrs.values_list("ufr_id", flat=True)
            )

        user = AuthenticatedUser(
            id=utilisateur.id,
            identifiant=utilisateur.identifiant,
            nom=utilisateur.nom,
            prenom=utilisateur.prenom,
            role=utilisateur.role,
            ufr_id=utilisateur.ufr_id,
            enseignant_ufr_ids=enseignant_ufr_ids,
            etudiant=utilisateur.etudiant,
            enseignant=utilisateur.enseignant,
        )
        return (user, None)
