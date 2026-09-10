"""[V4] 2026-09-09 — les dates de période académique disparaissent.

Elles n'existaient que pour borner la récurrence hebdomadaire des créneaux :
sans fin déclarée, un cours se serait répété indéfiniment dans l'agenda des
étudiants abonnés. La récurrence ayant disparu (planning.0004), elles n'ont
plus rien à borner.

C'est aussi une réponse à un constat d'usage : ces dates « varient souvent »
et personne ne pouvait les tenir à jour de façon fiable pour 12
établissements. Une donnée que le système exige mais que personne ne peut
garantir est pire qu'une donnée absente — elle donne une fausse assurance.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_ufr_type'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='ufr',
            name='ufr_periode_academique_coherente',
        ),
        migrations.RemoveField(
            model_name='ufr',
            name='periode_debut',
        ),
        migrations.RemoveField(
            model_name='ufr',
            name='periode_fin',
        ),
        migrations.RemoveField(
            model_name='ufr',
            name='periode_libelle',
        ),
    ]
