"""[V3] 2026-09-07 — abonnements Web Push anonymes (FR-PUB-08)."""

import core.utils
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('referentiel', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='AbonnementAlerte',
            fields=[
                ('id', models.CharField(default=core.utils.generate_id, editable=False, max_length=64, primary_key=True, serialize=False)),
                ('endpoint', models.TextField()),
                ('cle_p256dh', models.CharField(max_length=255)),
                ('cle_auth', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('groupe', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='abonnements_alerte', to='referentiel.groupe')),
            ],
            options={
                'db_table': 'abonnement_alerte',
                'indexes': [models.Index(fields=['groupe'], name='abonnement__groupe__79736c_idx')],
                'constraints': [models.UniqueConstraint(fields=('groupe', 'endpoint'), name='abonnement_alerte_unique')],
            },
        ),
    ]
