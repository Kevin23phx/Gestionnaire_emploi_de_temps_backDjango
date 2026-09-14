"""[V6] 2026-09-14 — passage de niveau annuel (FR-REF-12, jamais implémenté
jusqu'ici : le champ existait dans le docstring du modèle depuis la V2 mais
aucun mécanisme ne créait le groupe de l'année suivante).

Ajout pur (`AddField` nullable) — aucune donnée existante n'est touchée.
`promu_de` relie un groupe à celui dont il descend l'année précédente
(OneToOne : un groupe n'est promu qu'une fois).
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('referentiel', '0005_v5_filiere_vers_departement'),
    ]

    operations = [
        migrations.AddField(
            model_name='groupe',
            name='promu_de',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='groupe_suivant', to='referentiel.groupe'),
        ),
    ]
