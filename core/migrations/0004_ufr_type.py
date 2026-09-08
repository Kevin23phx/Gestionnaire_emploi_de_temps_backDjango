"""[V3.2] 2026-09-07 — un établissement n'est pas forcément une UFR.

Le référentiel officiel transmis par l'UJKZ recense 12 établissements :
5 UFR, 6 instituts (IBAM, ISSP, IFOAD, ISSDH, IGEDD, IPERMIC) et 1 école
doctorale (EDICC). La V2 avait délibérément restreint le périmètre aux
5 UFR ; cette restriction est levée.

Le défaut "ufr" est le bon pour les lignes existantes : ce sont exactement
les 5 UFR seedées jusqu'ici.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_v3_unaccent'),
    ]

    operations = [
        migrations.AddField(
            model_name='ufr',
            name='type',
            field=models.CharField(choices=[('ufr', 'UFR'), ('institut', 'Institut'), ('ecole_doctorale', 'École doctorale')], default='ufr', max_length=20),
        ),
    ]
