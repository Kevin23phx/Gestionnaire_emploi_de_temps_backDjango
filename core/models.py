from django.db import models


class Ufr(models.Model):
    """Les 5 UFR réelles de l'UJKZ (SH, SDS, SVT, SEA, LAC).

    "sigle" alimente l'identifiant du compte Gestionnaire
    (scolarite.<sigle>, en minuscules) — voir ufr/services.py.
    """

    id = models.CharField(primary_key=True, max_length=64)
    nom = models.CharField(max_length=255)
    sigle = models.CharField(max_length=32, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ufr"
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom
