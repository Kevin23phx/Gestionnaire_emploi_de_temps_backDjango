from django.db import models

from accounts.models import Utilisateur
from core.utils import generate_id
from planning.models import Creneau


class TypeNotification(models.TextChoices):
    MODIFIE = "modifie"
    ANNULE = "annule"
    INFO = "info"


class NotificationItem(models.Model):
    """Une notification par utilisateur concerné, créée dans la même
    transaction que l'écriture du créneau (INV-06) — "critique" gouverne
    seul l'envoi SMS (INT-04)."""

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    utilisateur = models.ForeignKey(Utilisateur, related_name="notifications", on_delete=models.PROTECT)
    type = models.CharField(max_length=16, choices=TypeNotification.choices)
    titre = models.CharField(max_length=255)
    description = models.TextField()
    date_heure = models.DateTimeField(auto_now_add=True)
    lue = models.BooleanField(default=False)
    critique = models.BooleanField(default=False)

    creneau = models.ForeignKey(Creneau, related_name="notifications", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        db_table = "notification_item"
        indexes = [models.Index(fields=["utilisateur", "lue"])]
