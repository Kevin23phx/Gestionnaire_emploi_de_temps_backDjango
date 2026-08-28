from django.db.models import Count
from rest_framework.exceptions import NotFound

from core.exceptions_helpers import Conflict
from core.ufr_scope import resolve_ufr_scope, ufr_filter_kwargs
from referentiel.models import Groupe

# "effectif" n'est jamais une colonne : toujours calculé (COUNT(Etudiant)),
# pour que PlanningModule et le moteur de conflits utilisent toujours la
# même valeur "vivante".
#
# INT-07 (V2) : un Gestionnaire ne voit/crée jamais de groupe hors de sa
# propre UFR ; un Enseignant ne voit que les UFR auxquelles il est affecté ;
# un Admin voit tout (lecture seule, FR-ADMIN-03), ou une seule UFR choisie
# (FR-ADMIN-06).


def list_groupes(user, ufr_id_pour_admin: str | None = None):
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    qs = Groupe.objects.annotate(effectif=Count("etudiants")).order_by("nom")
    return qs.filter(**ufr_filter_kwargs(scope))


def get_groupe(groupe_id: str) -> Groupe:
    try:
        return Groupe.objects.annotate(effectif=Count("etudiants")).get(id=groupe_id)
    except Groupe.DoesNotExist:
        raise NotFound("Groupe introuvable.")


def create_groupe(nom: str, filiere: str, niveau: str, annee_academique: str, ufr_id: str) -> Groupe:
    nom_trim = nom.strip()
    if Groupe.objects.filter(nom__iexact=nom_trim).exists():
        raise Conflict("Un groupe porte déjà ce nom.")
    groupe = Groupe.objects.create(
        nom=nom_trim, filiere=filiere.strip(), niveau=niveau.strip(), annee_academique=annee_academique.strip(), ufr_id=ufr_id
    )
    groupe.effectif = 0
    return groupe
