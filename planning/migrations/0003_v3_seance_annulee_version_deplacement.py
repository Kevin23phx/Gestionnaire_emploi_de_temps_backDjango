"""[V3] 2026-09-07 — annulation d'une séance à une date précise
(FR-EDT-07/INV-14), compteur de révision alimentant SEQUENCE dans le flux
calendrier (INV-13/FR-PUB-06), et mémoire du dernier déplacement d'horaire
(FR-PUB-07, événement "fantôme")."""

import core.utils
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('planning', '0002_creneau_exclude_constraint'),
    ]

    operations = [
        migrations.AddField(
            model_name='creneau',
            name='ancien_heure_debut_minutes',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='creneau',
            name='ancien_heure_fin_minutes',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='creneau',
            name='ancien_jour',
            field=models.CharField(blank=True, choices=[('lundi', 'Lundi'), ('mardi', 'Mardi'), ('mercredi', 'Mercredi'), ('jeudi', 'Jeudi'), ('vendredi', 'Vendredi'), ('samedi', 'Samedi')], max_length=16, null=True),
        ),
        migrations.AddField(
            model_name='creneau',
            name='deplace_le',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='creneau',
            name='version',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.CreateModel(
            name='SeanceAnnulee',
            fields=[
                ('id', models.CharField(default=core.utils.generate_id, editable=False, max_length=64, primary_key=True, serialize=False)),
                ('date', models.DateField()),
                ('motif', models.TextField()),
                ('annule_par', models.CharField(max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('creneau', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='seances_annulees', to='planning.creneau')),
            ],
            options={
                'db_table': 'seance_annulee',
                'indexes': [models.Index(fields=['creneau', 'date'], name='seance_annu_creneau_82c16a_idx')],
                'constraints': [models.UniqueConstraint(fields=('creneau', 'date'), name='seance_annulee_unique'), models.CheckConstraint(condition=models.Q(('motif', ''), _negated=True), name='seance_annulee_motif_requis')],
            },
        ),
    ]
