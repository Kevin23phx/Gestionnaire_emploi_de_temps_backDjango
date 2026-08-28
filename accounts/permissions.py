from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import BasePermission


class IsAuthenticatedCM(BasePermission):
    """Permission par défaut (settings.REST_FRAMEWORK) : toute route est
    protégée sauf celles qui déclarent explicitement AllowAny (login,
    activate, health) — équivalent du guard global NestJS dont @Public()
    est l'unique échappatoire."""

    def has_permission(self, request, view) -> bool:
        if not getattr(request.user, "is_authenticated", False):
            raise NotAuthenticated("Non connecté.")
        return True


def require_roles(*roles: str):
    """Équivalent de @Roles(...) + RolesGuard — lit uniquement
    request.user.role (posé par CookieSessionAuthentication, jamais par
    params/body/headers). Usage : permission_classes = [require_roles("scolarite", "admin")]"""

    class RequireRoles(BasePermission):
        def has_permission(self, request, view) -> bool:
            if not getattr(request.user, "is_authenticated", False):
                raise NotAuthenticated("Non connecté.")
            if request.user.role not in roles:
                raise PermissionDenied("Accès refusé pour ce rôle.")
            return True

    return RequireRoles
