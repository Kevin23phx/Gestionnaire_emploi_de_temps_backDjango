from dataclasses import dataclass, field


@dataclass
class AuthenticatedUser:
    """Ce que CookieSessionAuthentication attache à chaque requête, re-lu
    depuis la base à chaque appel (jamais mis en cache dans le cookie) —
    garantit INV-03 et une cohérence immédiate si un étudiant change de
    groupe en cours de session (INT-06).

    "ufr_id" : périmètre du compte lui-même (non-null SSI role="scolarite",
    INV-10). "enseignant_ufr_ids" : calculé une fois ici à partir
    d'EnseignantUfr (FR-REF-06) pour éviter à chaque vue de refaire la
    jointure — voir core/ufr_scope.py pour la résolution du périmètre à
    partir de ces deux champs.
    """

    id: str
    identifiant: str
    nom: str
    prenom: str
    role: str
    ufr_id: str | None
    enseignant_ufr_ids: list[str] = field(default_factory=list)
    etudiant: object | None = None
    enseignant: object | None = None

    is_authenticated: bool = True
    is_anonymous: bool = False
