from core.ufr_scope import resolve_ufr_scope
from audit.models import AuditEntry


def record(auteur: str, action: str, motif: str | None = None, creneau_id: str | None = None) -> AuditEntry:
    return AuditEntry.objects.create(
        auteur=auteur.strip(),
        action=action.strip(),
        motif=(motif or "").strip() or "—",
        creneau_id=creneau_id,
    )


def record_batch(entries: list[dict]) -> list[AuditEntry]:
    objets = [
        AuditEntry(
            auteur=e["auteur"].strip(),
            action=e["action"].strip(),
            motif=(e.get("motif") or "").strip() or "—",
            creneau_id=e.get("creneau_id"),
        )
        for e in entries
    ]
    return AuditEntry.objects.bulk_create(objets)


def list_entries(user, ufr_id_pour_admin: str | None = None):
    """INT-07 (V2) : un Gestionnaire ne voit que l'audit des créneaux de sa
    propre UFR (via le groupe du créneau) — les entrées sans creneau_id
    (ex. création d'une UFR/d'un compte Gestionnaire) sont des événements de
    supervision, jamais montrés à un Gestionnaire. L'Admin voit tout
    (FR-ADMIN-03)."""
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    qs = AuditEntry.objects.all()
    if not scope.toutes:
        qs = qs.filter(creneau__isnull=False, creneau__groupe__ufr_id__in=scope.ufr_ids)
    return qs.order_by("-date_heure")
