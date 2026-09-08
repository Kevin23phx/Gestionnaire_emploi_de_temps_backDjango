"""[V3] 2026-09-07 — période académique par UFR (FR-REF-16/17) et
suppression des tables des deux applications retirées.

Les tables `demande_enseignant` et `notification_item` sont supprimées ici,
dans `core`, et non par une migration de leur propre application : ces
applications n'existent plus du tout (répertoires supprimés), Django n'a
donc plus aucun moyen d'exécuter une migration qui leur appartiendrait. Sur
une base neuve les tables ne seront jamais créées, et ce DROP ne fera rien ;
sur la base de développement existante, il fait le ménage.

L'ordre compte : `notification_item` référence `utilisateur` en PROTECT.
Tant que ses lignes existent, la suppression des comptes Étudiant/Enseignant
(migration accounts/0002, qui dépend de celle-ci) échouerait.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                "DROP TABLE IF EXISTS demande_enseignant CASCADE;",
                "DROP TABLE IF EXISTS notification_item CASCADE;",
                # Sans quoi Django croirait ces applications toujours
                # migrées et se plaindrait de migrations orphelines.
                "DELETE FROM django_migrations WHERE app IN ('demandes', 'notifications');",
            ],
            # Irréversible et assumé : recréer ces tables vides ne
            # restaurerait pas les données, et rien dans le code V3 ne sait
            # plus les lire.
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AddField(
            model_name='ufr',
            name='periode_debut',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='ufr',
            name='periode_fin',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='ufr',
            name='periode_libelle',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddConstraint(
            model_name='ufr',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('periode_debut__isnull', True), ('periode_fin__isnull', True)), models.Q(('periode_debut__isnull', False), ('periode_fin__isnull', False), ('periode_fin__gt', models.F('periode_debut'))), _connector='OR'), name='ufr_periode_academique_coherente'),
        ),
    ]
