import hashlib
import secrets


def generate_session_token() -> str:
    """La valeur brute devient le cookie cm_session ; seul son hash SHA-256
    est stocké en base (Session.token_hash) — un dump de la base ne suffit
    jamais à réutiliser une session."""
    return secrets.token_hex(32)


def hash_session_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()
