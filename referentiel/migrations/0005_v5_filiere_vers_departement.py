"""[V5] 2026-09-11 — "filière" renommée "département" partout.

`Groupe.filiere` était une chaîne libre censée reprendre le `libelle` d'un
`Departement` officiel (introduit en V3.2), mais portait un nom différent :
le vocabulaire divergeait entre le référentiel officiel ("département") et
le champ qui est censé y puiser sa valeur ("filière"). Renommage pur, sans
transformation de données — `RenameField` se traduit en un simple
`ALTER TABLE ... RENAME COLUMN` côté PostgreSQL.
"""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("referentiel", "0004_uniteenseignement_departements"),
    ]

    operations = [
        migrations.RenameField(
            model_name="groupe",
            old_name="filiere",
            new_name="departement",
        ),
    ]
