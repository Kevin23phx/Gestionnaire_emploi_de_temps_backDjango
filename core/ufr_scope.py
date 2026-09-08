"""V2 multi-UFR (INT-07) : résout le périmètre UFR effectif d'un utilisateur
authentifié, une seule fois, pour que chaque service applique exactement la
même règle plutôt que de réinventer sa propre lecture de user.role.

- admin : "toutes" (None) — supervision transverse (FR-ADMIN-03), sauf
  ufr_id_pour_admin fourni (FR-ADMIN-06, drill-down sur une UFR précise).
- scolarite : sa seule UFR (INV-10 garantit qu'elle existe toujours).

[V3] Les branches "etudiant" et "enseignant" ont disparu avec les rôles
correspondants (INV-03 : deux rôles). La consultation publique ne passe
jamais par ici : elle n'a pas d'utilisateur à qui résoudre un périmètre,
et sa propre restriction — ne rien exposer de nominatif (INV-12) — est
d'une autre nature qu'un filtre par UFR.
"""

from dataclasses import dataclass


@dataclass
class UfrScope:
    toutes: bool
    ufr_ids: list[str]


def resolve_ufr_scope(user, ufr_id_pour_admin: str | None = None) -> UfrScope:
    if user.role == "admin":
        if ufr_id_pour_admin:
            return UfrScope(toutes=False, ufr_ids=[ufr_id_pour_admin])
        return UfrScope(toutes=True, ufr_ids=[])
    if user.role == "scolarite":
        return UfrScope(toutes=False, ufr_ids=[user.ufr_id] if user.ufr_id else [])
    return UfrScope(toutes=False, ufr_ids=[])


def ufr_filter_kwargs(scope: UfrScope, field: str = "ufr_id") -> dict:
    """Clause de filtre QuerySet correspondante pour un modèle dont le champ
    UFR s'appelle directement `field` (Groupe, UniteEnseignement,
    Salle, Utilisateur). Pour un modèle qui n'a pas ce champ directement
    (Creneau, AuditEntry...), construire la clause via la
    relation appropriée au point d'appel plutôt que d'essayer de
    généraliser ici."""
    if scope.toutes:
        return {}
    return {f"{field}__in": scope.ufr_ids}
