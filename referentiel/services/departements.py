"""[V3.2] Départements (« filières ») officiels d'un établissement.

Alimente la liste déroulante « Filière » du formulaire de groupe
(FR-REF-20/21). La liste vient désormais du référentiel officiel de l'UJKZ
et non plus des groupes déjà créés : une valeur ne peut donc plus être
« inventée » par une faute de frappe.
"""

from rest_framework.exceptions import ValidationError

from core.exceptions_helpers import Conflict
from core.ufr_scope import resolve_ufr_scope, ufr_filter_kwargs
from referentiel.models import Departement


def list_departements(user, ufr_id_pour_admin: str | None = None, recherche: str | None = None):
    """[2026-09] `recherche` filtre EN BASE, pas dans le navigateur.

    Le filtrage se faisait côté client sur la liste complète : la requête
    partait chercher tous les départements de l'établissement quel que soit
    le terme saisi, et l'écran n'en gardait qu'une poignée. Le temps
    d'attente ne dépendait donc pas de ce qu'on cherchait mais de la taille
    du référentiel — l'inverse de ce qu'un filtre est censé faire.

    `unaccent` avant `icontains`, comme partout ailleurs (FR-FILT-02) : sans
    lui, « genie » ne trouverait pas « Génie logiciel ».
    """
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    qs = Departement.objects.filter(**ufr_filter_kwargs(scope))
    if recherche and recherche.strip():
        qs = qs.filter(libelle__unaccent__icontains=recherche.strip())
    return qs.order_by("libelle")


def create_departement(libelle: str, ufr_id: str) -> Departement:
    """FR-REF-21 : ouvrir un département que le référentiel officiel ne
    connaît pas encore.

    Sans cette porte, un Gestionnaire dont la filière vient d'être créée
    serait bloqué jusqu'à ce qu'un développeur mette le seed à jour. Avec
    elle, le nouveau libellé rejoint la liste et sera proposé aux créations
    suivantes — la liste s'enrichit au lieu de se dégrader, ce qui est
    exactement l'inverse du comportement de l'ancienne saisie libre.
    """
    libelle_trim = (libelle or "").strip()
    if not libelle_trim:
        raise ValidationError("Le libellé du département est obligatoire.")
    if Departement.objects.filter(ufr_id=ufr_id, libelle__iexact=libelle_trim).exists():
        raise Conflict("Ce département existe déjà pour votre établissement.")
    return Departement.objects.create(libelle=libelle_trim, ufr_id=ufr_id)
