# [V8.1] Découpe les spécialités saisies en bloc (2026-09-21).
#
# ## Ce que cette migration répare
#
# Avant le correctif du même jour, la zone de saisie de l'écran Spécialités
# enregistrait TOUT ce qu'on y tapait comme un seul libellé. Un Gestionnaire
# qui énumérait naturellement « medecine generale, science du cerveau,
# sicence des membres » — c'est-à-dire la façon dont on énumère en
# français — obtenait UNE spécialité portant la phrase entière.
#
# Le symptôme n'était pas cosmétique : cette phrase devenait l'unique choix
# de la liste déroulante, côté Gestionnaire comme côté étudiant. Aucune des
# trois spécialités réelles n'était sélectionnable, et un étudiant en
# « science du cerveau » ne pouvait pas trouver son programme.
#
# Le code ne peut plus produire cette forme (referentiel/services/
# specialites.py découpe désormais côté serveur), mais les lignes déjà
# enregistrées, elles, restent telles quelles — d'où cette migration.
#
# ## Pourquoi une migration et pas une correction manuelle en base
#
# Parce que le défaut n'est pas propre à un poste : toute installation ayant
# tourné avec la version précédente porte les mêmes lignes. Une correction
# tapée dans un terminal aurait réparé une base et laissé les autres, sans
# trace de ce qui a été fait ni de pourquoi.
#
# ## Ce qu'elle ne touche pas
#
# `Groupe.specialite` et `Creneau.specialite` sont des chaînes dénormalisées
# (INV-21) : elles gardent le libellé qu'elles portaient au moment de leur
# saisie, et cette migration ne les réécrit PAS. Si l'une d'elles contenait
# la phrase entière, on ne saurait de toute façon pas laquelle des trois
# spécialités le Gestionnaire voulait désigner — deviner reviendrait à
# inventer une donnée. La cascade publique reste par ailleurs capable de
# retrouver un tel programme, puisqu'elle propose aussi les spécialités
# effectivement portées (public/services.py).
#
# Irréversible par nature : une fois les trois entrées créées, rien ne dit
# lesquelles provenaient d'une même saisie, ni dans quel ordre. Le retour
# arrière est donc un noop assumé plutôt qu'une reconstruction approximative.
import re

from django.db import migrations

SEPARATEURS = re.compile(r"[,;\n\r]+")


def decouper(apps, schema_editor):
    Specialite = apps.get_model("referentiel", "Specialite")

    for specialite in list(Specialite.objects.all()):
        morceaux = [m.strip() for m in SEPARATEURS.split(specialite.libelle)]
        morceaux = [m for m in morceaux if m]
        if len(morceaux) <= 1:
            continue

        # Le premier morceau REMPLACE le libellé de la ligne existante au
        # lieu d'être recréé : la ligne garde ainsi son identifiant et sa
        # date de création. Une suppression suivie de trois créations aurait
        # marché aussi, mais aurait effacé l'historique d'une déclaration
        # que le Gestionnaire a bel et bien faite.
        premier, *suivants = morceaux
        specialite.libelle = premier
        specialite.save(update_fields=["libelle"])

        for libelle in suivants:
            # Un morceau qui existe déjà comme spécialité à part entière est
            # ignoré : la contrainte d'unicité (département, niveau, libellé
            # en minuscules) ferait échouer toute la migration, et donc
            # bloquerait la mise à jour pour une donnée déjà correcte.
            existe = Specialite.objects.filter(
                departement_id=specialite.departement_id,
                niveau=specialite.niveau,
                libelle__iexact=libelle,
            ).exists()
            if existe:
                continue
            Specialite.objects.create(
                departement_id=specialite.departement_id,
                niveau=specialite.niveau,
                libelle=libelle,
            )


class Migration(migrations.Migration):
    dependencies = [("referentiel", "0010_v8_specialites")]

    operations = [
        migrations.RunPython(decouper, migrations.RunPython.noop),
    ]
