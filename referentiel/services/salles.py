from django.db.models import Q

from core.exceptions_helpers import Conflict
from core.ufr_scope import resolve_ufr_scope
from referentiel.models import Salle, StructureGestionnaire


def list_salles(user, ufr_id_pour_admin: str | None = None):
    """Une salle DEP (commune/louée) n'a pas d'ufr_id — elle reste visible
    de tout le monde (jamais exclue par le filtre UFR), au même titre
    qu'une salle mutualisée l'est déjà en pratique."""
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    qs = Salle.objects.order_by("nom")
    if scope.toutes:
        return qs
    return qs.filter(Q(ufr_id__in=scope.ufr_ids) | Q(structure_gestionnaire=StructureGestionnaire.DEP))


def create_salle(nom: str, batiment: str, capacite: int, type_usage: str, createur) -> Salle:
    """FR-REF-02/03 : un Gestionnaire crée toujours une salle "UFR" pour sa
    propre UFR (ufr_id forcé) ; l'Admin ne gère aucune UFR (FR-ADMIN-04)
    mais reste responsable des salles DEP tant qu'aucun référent DEP n'est
    désigné — il ne peut donc créer QUE des salles DEP."""
    nom_trim = nom.strip()
    if Salle.objects.filter(nom__iexact=nom_trim).exists():
        raise Conflict("Une salle porte déjà ce nom.")

    est_dep = createur.role == "admin"
    return Salle.objects.create(
        nom=nom_trim,
        batiment=batiment.strip(),
        capacite=capacite,
        type_usage=type_usage,
        structure_gestionnaire=StructureGestionnaire.DEP if est_dep else StructureGestionnaire.UFR,
        ufr_id=None if est_dep else createur.ufr_id,
    )
