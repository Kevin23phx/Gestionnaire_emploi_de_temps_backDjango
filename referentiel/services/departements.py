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


def list_departements(user, ufr_id_pour_admin: str | None = None):
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    return Departement.objects.filter(**ufr_filter_kwargs(scope)).order_by("libelle")


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
