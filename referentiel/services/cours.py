from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from core.exceptions_helpers import Conflict
from core.ufr_scope import resolve_ufr_scope, ufr_filter_kwargs
from referentiel.models import Departement, UniteEnseignement


def list_cours(user, ufr_id_pour_admin: str | None = None):
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    # prefetch : sans lui, afficher les départements de N cours produirait
    # N requêtes supplémentaires, sur l'écran justement destiné à parcourir
    # un référentiel volumineux.
    qs = UniteEnseignement.objects.prefetch_related("departements").order_by("intitule")
    return qs.filter(**ufr_filter_kwargs(scope))


def _departements_de_l_etablissement(departement_ids: list[str] | None, ufr_id: str) -> list[Departement]:
    """INT-07 : un cours ne peut être rattaché qu'aux départements de SON
    établissement. Les identifiants viennent du client ; les valider ici est
    le seul moyen d'empêcher qu'un gestionnaire rattache son cours à un
    département de l'UFR voisine, volontairement ou par copie d'un id."""
    if not departement_ids:
        return []
    trouves = list(Departement.objects.filter(id__in=departement_ids, ufr_id=ufr_id))
    if len(trouves) != len(set(departement_ids)):
        raise ValidationError("Un des départements sélectionnés n'appartient pas à votre établissement.")
    return trouves


@transaction.atomic
def create_cours(
    intitule: str, code: str | None, niveau: str, ufr_id: str, departement_ids: list[str] | None = None
) -> UniteEnseignement:
    intitule_trim = intitule.strip()
    if UniteEnseignement.objects.filter(intitule__iexact=intitule_trim).exists():
        raise Conflict("Un cours porte déjà cet intitulé.")

    departements = _departements_de_l_etablissement(departement_ids, ufr_id)

    # "—" par défaut si aucun code n'est fourni.
    cours = UniteEnseignement.objects.create(
        intitule=intitule_trim, code=(code or "").strip() or "—", niveau=niveau.strip(), ufr_id=ufr_id
    )
    cours.departements.set(departements)
    return cours


@transaction.atomic
def update_cours(cours_id: str, donnees: dict, user) -> UniteEnseignement:
    """[V3.3] Sert d'abord à rattacher un cours à ses départements.

    Indispensable et pas seulement confortable : les cours créés avant cette
    version n'ont aucun département, et sans route de modification il
    faudrait les supprimer et les ressaisir un par un — ce que le référentiel
    ne permet même pas, un cours étant protégé par les créneaux qui le
    référencent.
    """
    try:
        cours = UniteEnseignement.objects.get(id=cours_id)
    except UniteEnseignement.DoesNotExist:
        raise NotFound("Cours introuvable.")

    if user.role == "scolarite" and cours.ufr_id != user.ufr_id:
        raise Conflict("Ce cours appartient à un autre établissement.")

    champs = []
    if "intitule" in donnees:
        intitule_trim = (donnees["intitule"] or "").strip()
        if not intitule_trim:
            raise ValidationError("L'intitulé est obligatoire.")
        if UniteEnseignement.objects.filter(intitule__iexact=intitule_trim).exclude(id=cours_id).exists():
            raise Conflict("Un cours porte déjà cet intitulé.")
        cours.intitule = intitule_trim
        champs.append("intitule")
    if "code" in donnees:
        cours.code = (donnees["code"] or "").strip() or "—"
        champs.append("code")
    if "niveau" in donnees:
        cours.niveau = (donnees["niveau"] or "").strip()
        champs.append("niveau")
    if champs:
        cours.save(update_fields=champs)

    if "departementIds" in donnees:
        cours.departements.set(_departements_de_l_etablissement(donnees["departementIds"], cours.ufr_id))

    return cours
