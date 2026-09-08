"""[V3.1] 2026-09-07 — l'effectif devient une colonne saisie, et le
référentiel nominatif des étudiants est supprimé.

Décision du porteur de projet : tenir à jour la liste nominative des
inscrits de chaque groupe (import Excel, INE, affectations, promotions)
représentait un travail considérable pour une seule valeur réellement
consommée par le système — le NOMBRE d'étudiants, comparé à la capacité
d'une salle (RM-02). Le Gestionnaire saisit désormais ce nombre directement.

L'ordre des opérations compte : la colonne est d'abord créée, puis
**alimentée depuis le comptage existant**, et seulement ensuite la table
`etudiant` est supprimée. Sans cette reprise, tous les groupes déjà en base
repartiraient à 0 et la détection de conflit de capacité cesserait
silencieusement de signaler quoi que ce soit — un défaut invisible, qui ne
se manifesterait que le jour où deux cents étudiants se présenteraient
devant une salle de soixante places.

Irréversible en pratique : la migration inverse recréerait une table
`etudiant` vide, sans restaurer une seule ligne.
"""

from django.db import migrations, models


def reprendre_effectifs(apps, schema_editor):
    Groupe = apps.get_model("referentiel", "Groupe")
    Etudiant = apps.get_model("referentiel", "Etudiant")

    reprises = 0
    for groupe in Groupe.objects.all():
        effectif = Etudiant.objects.filter(groupe_id=groupe.id).count()
        if effectif:
            Groupe.objects.filter(id=groupe.id).update(effectif=effectif)
            reprises += 1
    print(f"  [V3.1] Effectif repris depuis le comptage pour {reprises} groupe(s).")


class Migration(migrations.Migration):

    dependencies = [
        ("referentiel", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="groupe",
            name="effectif",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(reprendre_effectifs, migrations.RunPython.noop),
        migrations.RemoveIndex(model_name="etudiant", name="etudiant_groupe__aa8355_idx"),
        migrations.RemoveIndex(model_name="etudiant", name="etudiant_ufr_id_54790e_idx"),
        migrations.RemoveIndex(model_name="etudiant", name="etudiant_ufr_id_8c1ee6_idx"),
        migrations.RemoveIndex(model_name="etudiant", name="etudiant_ufr_id_a27187_idx"),
        migrations.DeleteModel(name="Etudiant"),
    ]
