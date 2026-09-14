"""[V6] 2026-09-14 — unicité du nom de groupe scopée par année académique.

Découvert en expliquant le mécanisme de passage de niveau (FR-REF-29) : la
contrainte précédente interdisait pour toujours de réutiliser un nom de
groupe une fois pris, alors qu'un nom de cohorte ("L1 Médecine - Groupe A")
est censé se répéter chaque année pour la nouvelle promotion — le groupe de
l'année précédente restant volontairement en base comme historique
(jamais supprimé), il aurait bloqué le nom en permanence.
"""

import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_v4_supprimer_periode_academique'),
        ('referentiel', '0006_v6_groupe_promu_de'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='groupe',
            name='groupe_nom_lower_unique',
        ),
        migrations.AddConstraint(
            model_name='groupe',
            constraint=models.UniqueConstraint(django.db.models.functions.text.Lower('nom'), models.F('annee_academique'), name='groupe_nom_lower_annee_unique'),
        ),
    ]
