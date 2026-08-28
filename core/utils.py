import uuid


def generate_id() -> str:
    """Identifiant opaque, format libre côté contrat (le frontend ne parse
    jamais un id) — remplace Prisma cuid() sans en reproduire le format."""
    return uuid.uuid4().hex
