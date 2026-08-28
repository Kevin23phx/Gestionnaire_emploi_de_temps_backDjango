"""V2 multi-UFR (INT-07) : résout le périmètre UFR effectif d'un utilisateur
authentifié, une seule fois, pour que chaque service applique exactement la
même règle plutôt que de réinventer sa propre lecture de user.role.

- admin : "toutes" (None) — supervision transverse (FR-ADMIN-03), sauf
  ufr_id_pour_admin fourni (FR-ADMIN-06, drill-down sur une UFR précise).
- scolarite : sa seule UFR (INV-10 garantit qu'elle existe toujours).
- etudiant : l'UFR de son Etudiant, si déjà rattaché à un compte.
- enseignant : l'ensemble de ses UFR affectées (FR-REF-06), possiblement
  vide (aucune affectation = ne voit rien, jamais "toutes" par défaut).
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
    if user.role == "etudiant":
        ufr_id = user.etudiant.ufr_id if user.etudiant else None
        return UfrScope(toutes=False, ufr_ids=[ufr_id] if ufr_id else [])
    if user.role == "enseignant":
        return UfrScope(toutes=False, ufr_ids=list(user.enseignant_ufr_ids))
    return UfrScope(toutes=False, ufr_ids=[])


def ufr_filter_kwargs(scope: UfrScope, field: str = "ufr_id") -> dict:
    """Clause de filtre QuerySet correspondante pour un modèle dont le champ
    UFR s'appelle directement `field` (Etudiant, Groupe, UniteEnseignement,
    Salle, Utilisateur). Pour un modèle qui n'a pas ce champ directement
    (Creneau, DemandeEnseignant, AuditEntry...), construire la clause via la
    relation appropriée au point d'appel plutôt que d'essayer de
    généraliser ici."""
    if scope.toutes:
        return {}
    return {f"{field}__in": scope.ufr_ids}
