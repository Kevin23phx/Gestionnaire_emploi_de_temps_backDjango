"""[2026-09] Détache tous les cours de leurs départements.

Décision du porteur de projet : un cours n'est plus rattaché à un
département (le département qui suit un cours se lit sur le GROUPE du
créneau, FR-EDT-01). L'interface ne montre plus ce rattachement ni ne permet
de le saisir — mais les liens créés avant cette décision restent en base.

Cette commande les efface. Elle n'est PAS lancée automatiquement, et surtout
pas par le seed : effacer des données saisies à la main sans que personne ne
l'ait demandé est exactement ce qu'on s'interdit ici. Elle affiche par
défaut ce qu'elle ferait ; il faut `--confirmer` pour qu'elle écrive.

    python manage.py detacher_cours_departements            # simulation
    python manage.py detacher_cours_departements --confirmer  # exécution
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from referentiel.models import UniteEnseignement


class Command(BaseCommand):
    help = "Efface le rattachement des cours aux départements (simulation par défaut)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirmer",
            action="store_true",
            help="Écrit réellement en base. Sans ce drapeau, la commande se contente de compter.",
        )

    def handle(self, *args, **options):
        rattaches = [ue for ue in UniteEnseignement.objects.prefetch_related("departements") if ue.departements.exists()]
        liens = sum(ue.departements.count() for ue in rattaches)

        if not rattaches:
            self.stdout.write(self.style.SUCCESS("Aucun cours n'est rattaché à un département — rien à faire."))
            return

        self.stdout.write(f"{len(rattaches)} cours rattachés, {liens} liens au total :")
        for ue in rattaches:
            libelles = ", ".join(d.libelle for d in ue.departements.all())
            self.stdout.write(f"  - {ue.intitule} ({ue.code or 'sans code'}) → {libelles}")

        if not options["confirmer"]:
            self.stdout.write(
                self.style.WARNING("\nSimulation : rien n'a été modifié. Relancez avec --confirmer pour effacer.")
            )
            return

        with transaction.atomic():
            for ue in rattaches:
                ue.departements.clear()
        self.stdout.write(self.style.SUCCESS(f"\n{liens} liens effacés."))
