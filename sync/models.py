from django.db import models

from accounts.models import Utilisateur
from core.utils import generate_id


class SyncQueueEntry(models.Model):
    """Volontairement minimal : prouve le point d'ancrage "Sync -> DB", sans
    logique de rejeu. Le mode hors-ligne réel (cache local + file d'attente)
    est une responsabilité du Service Worker côté PWA."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    utilisateur = models.ForeignKey(Utilisateur, related_name="sync_entries", on_delete=models.PROTECT)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "sync_queue_entry"
