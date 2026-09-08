"""[V3.2] 2026-09-07 — référentiel officiel des départements (« filières »).

53 départements répartis sur les 12 établissements. Remplace la déduction
des filières à partir des groupes déjà créés, qui ne pouvait donner qu'un
référentiel de qualité décroissante : chaque faute de frappe y devenait une
filière de plus dans la recherche publique (FR-PUB-02).
"""

import core.utils
import django.db.models.deletion
import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_ufr_type'),
        ('referentiel', '0002_v31_effectif_saisi_suppression_etudiants'),
    ]

    operations = [
        migrations.CreateModel(
            name='Departement',
            fields=[
                ('id', models.CharField(default=core.utils.generate_id, editable=False, max_length=64, primary_key=True, serialize=False)),
                ('libelle', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('ufr', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='departements', to='core.ufr')),
            ],
            options={
                'db_table': 'departement',
                'ordering': ['libelle'],
                'indexes': [models.Index(fields=['ufr'], name='departement_ufr_id_b2f4fc_idx')],
                'constraints': [models.UniqueConstraint(django.db.models.functions.text.Lower('libelle'), models.F('ufr'), name='departement_libelle_ufr_unique')],
            },
        ),
    ]
