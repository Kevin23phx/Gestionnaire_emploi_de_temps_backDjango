from dataclasses import dataclass


@dataclass
class AuthenticatedUser:
    """Ce que CookieSessionAuthentication attache à chaque requête, re-lu
    depuis la base à chaque appel (jamais mis en cache dans le cookie) —
    garantit INV-03 et une cohérence immédiate si le périmètre du compte
    change en cours de session.

    "ufr_id" : périmètre du compte lui-même (non-null SSI role="scolarite",
    INV-10) — voir core/ufr_scope.py pour la résolution du périmètre.

    [V3] Les champs "etudiant", "enseignant" et "enseignant_ufr_ids" ont
    disparu avec les rôles correspondants : un compte n'est plus jamais
    l'ombre d'une fiche de référentiel.
    """

    id: str
    identifiant: str
    nom: str
    prenom: str
    role: str
    ufr_id: str | None

    is_authenticated: bool = True
    is_anonymous: bool = False
