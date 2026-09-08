"""[V3] FR-FILT-02 — recherche insensible aux accents.

`icontains` de PostgreSQL est insensible à la CASSE, pas aux ACCENTS :
« reseaux » ne trouve pas « Réseaux ». Ce n'est pas un détail de confort au
Burkina Faso, où la saisie se fait souvent depuis un clavier de téléphone
sans accents — un Gestionnaire qui tape « kabore » doit trouver « Kaboré »,
sans quoi il conclut que la fiche n'existe pas et en crée un doublon.

L'extension `unaccent` demande les droits superutilisateur : elle est donc
créée par la migration, qui tourne sous MIGRATE_DATABASE_URL, et non par le
rôle applicatif restreint (voir README).
"""

from django.contrib.postgres.operations import UnaccentExtension
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_v3_periode_academique_et_apps_retirees"),
    ]

    operations = [
        UnaccentExtension(),
    ]
