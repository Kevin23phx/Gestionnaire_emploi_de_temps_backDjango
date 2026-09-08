import datetime

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from audit.models import AuditEntry
from core.ufr_scope import resolve_ufr_scope


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


def list_entries(
    user,
    ufr_id_pour_admin: str | None = None,
    recherche: str | None = None,
    depuis: str | None = None,
    jusqua: str | None = None,
    auteur: str | None = None,
    limite: int = 200,
):
    """INT-07 (V2) : un Gestionnaire ne voit que l'audit des créneaux de sa
    propre UFR (via le groupe du créneau) — les entrées sans creneau_id
    (ex. création d'une UFR/d'un compte Gestionnaire) sont des événements de
    supervision, jamais montrés à un Gestionnaire. L'Admin voit tout
    (FR-ADMIN-03).

    [V3] FR-AUD-04 : filtres et plafond. Un journal append-only croît
    indéfiniment par construction (INV-04 interdit d'en supprimer une
    ligne) : au bout d'un semestre, le renvoyer en entier rendrait
    FR-AUD-02 inutilisable et l'écran illisible. Le plafond par défaut n'est
    donc pas une optimisation, c'est ce qui garde l'écran fonctionnel — et
    il s'applique APRÈS les filtres, pour que chercher une entrée précise
    reste possible quelle que soit la taille du journal.
    """
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    qs = AuditEntry.objects.all()
    if not scope.toutes:
        qs = qs.filter(creneau__isnull=False, creneau__groupe__ufr_id__in=scope.ufr_ids)

    if recherche:
        qs = qs.filter(Q(action__unaccent__icontains=recherche) | Q(motif__unaccent__icontains=recherche))
    if auteur:
        qs = qs.filter(auteur__unaccent__icontains=auteur)
    if depuis:
        qs = qs.filter(date_heure__date__gte=_date(depuis, "depuis"))
    if jusqua:
        qs = qs.filter(date_heure__date__lte=_date(jusqua, "jusqua"))

    return qs.order_by("-date_heure")[: max(1, min(limite, 1000))]


def _date(valeur: str, champ: str):
    try:
        return datetime.date.fromisoformat(valeur)
    except (TypeError, ValueError):
        raise ValidationError(f"Paramètre '{champ}' invalide (format attendu : AAAA-MM-JJ).")
