from django.db import models

from core.utils import generate_id
from planning.models import Creneau


class AuditEntry(models.Model):
    """Append-only — aucune route PATCH/DELETE n'existe pour ce modèle
    (audit/views.py), et le rôle applicatif Postgres n'a pas les droits
    UPDATE/DELETE dessus (voir la migration de privilèges) — deux lignes de
    défense indépendantes (INV-04/INT-05)."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    auteur = models.CharField(max_length=255)
    utilisateur_id = models.CharField(max_length=64, null=True, blank=True)
    date_heure = models.DateTimeField(auto_now_add=True)
    action = models.CharField(max_length=512)
    motif = models.TextField()

    creneau = models.ForeignKey(Creneau, related_name="audit_entries", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "audit_entry"
        indexes = [models.Index(fields=["date_heure"])]
