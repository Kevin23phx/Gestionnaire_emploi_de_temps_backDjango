"""[V3] 2026-09-07 — retrait des colonnes et des rôles devenus sans objet.

Suite de la migration 0002, qui a supprimé les lignes ; voir son en-tête
pour la raison de la scission. Une fois `utilisateur.etudiant_id` et
`utilisateur.enseignant_id` disparues, un compte ne peut plus être la
doublure d'une fiche de référentiel : INT-02 (« aucun compte hors création
par l'Admin ») devient vérifiable d'un coup d'œil, `ufr/services.py` étant
le seul endroit du code qui crée encore un Utilisateur.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_v3_supprimer_comptes_etudiant_enseignant"),
    ]

    operations = [
        migrations.RemoveField(model_name="utilisateur", name="enseignant"),
        migrations.RemoveField(model_name="utilisateur", name="etudiant"),
        migrations.AlterField(
            model_name="utilisateur",
            name="role",
            field=models.CharField(
                choices=[("scolarite", "Scolarite"), ("admin", "Admin")], max_length=32
            ),
        ),
    ]
