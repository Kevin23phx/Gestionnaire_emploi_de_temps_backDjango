"""[V3] 2026-09-07 — suppression des COMPTES Étudiant et Enseignant (lignes).

Séparée du retrait des colonnes (migration 0003) : Postgres refuse un
ALTER TABLE sur une table dont la transaction courante porte encore des
« pending trigger events », c'est-à-dire les contraintes de clé étrangère
différées produites par les DELETE qui précèdent. Une migration = une
transaction : en scindant, l'ALTER de 0003 s'exécute sur une table au repos.

Ce qui est supprimé ici : des COMPTES (lignes `utilisateur` de rôle
"etudiant"/"enseignant", et leurs sessions par cascade). Ce qui n'est PAS
touché, et ne doit surtout pas l'être : les ENTITÉS `etudiant` et
`enseignant` du référentiel. Un créneau porte toujours un enseignant
(INV-01), et l'effectif d'un groupe reste le nombre d'étudiants qui y sont
rattachés (RM-02) — supprimer ces lignes-là viderait le référentiel et
désactiverait la détection de conflit de capacité.
"""

from django.db import migrations


def supprimer_comptes_consultation(apps, schema_editor):
    Utilisateur = apps.get_model("accounts", "Utilisateur")
    supprimes, detail = Utilisateur.objects.filter(role__in=["etudiant", "enseignant"]).delete()
    print(f"  [V3] {supprimes} ligne(s) supprimée(s) : {detail}")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        # notification_item référence utilisateur en PROTECT : ses lignes
        # doivent avoir disparu avant qu'on supprime le moindre compte.
        ("core", "0002_v3_periode_academique_et_apps_retirees"),
    ]

    operations = [
        migrations.RunPython(supprimer_comptes_consultation, migrations.RunPython.noop),
    ]
