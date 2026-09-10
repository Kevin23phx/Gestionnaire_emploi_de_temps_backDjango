"""[V3.3] 2026-09-07 — un cours est rattaché à un ou plusieurs départements.

Relation multiple et non simple : un cours mutualisé (tronc commun, UE
d'anglais, statistique de base) est dispensé à plusieurs départements à la
fois. Avec un rattachement unique il faudrait recréer la même fiche autant
de fois qu'il y a de départements concernés — donc maintenir N cours pour
une seule réalité, et ne jamais pouvoir répondre à « quels départements
suivent ce cours ? ».

Champ facultatif : les cours existants restent sans département tant que le
Gestionnaire ne les a pas rattachés (PATCH /api/cours/<id>). L'interface le
signale plutôt que de le laisser passer inaperçu.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referentiel', '0003_departement'),
    ]

    operations = [
        migrations.AddField(
            model_name='uniteenseignement',
            name='departements',
            field=models.ManyToManyField(blank=True, related_name='cours', to='referentiel.departement'),
        ),
    ]
