from core.exceptions_helpers import Conflict
from core.ufr_scope import resolve_ufr_scope, ufr_filter_kwargs
from referentiel.models import UniteEnseignement


def list_cours(user, ufr_id_pour_admin: str | None = None):
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    qs = UniteEnseignement.objects.order_by("intitule")
    return qs.filter(**ufr_filter_kwargs(scope))


def create_cours(intitule: str, code: str | None, niveau: str, ufr_id: str) -> UniteEnseignement:
    intitule_trim = intitule.strip()
    if UniteEnseignement.objects.filter(intitule__iexact=intitule_trim).exists():
        raise Conflict("Un cours porte déjà cet intitulé.")

    # "—" par défaut si aucun code n'est fourni.
    return UniteEnseignement.objects.create(
        intitule=intitule_trim, code=(code or "").strip() or "—", niveau=niveau.strip(), ufr_id=ufr_id
    )
