from core.exceptions_helpers import Conflict
from referentiel.models import Salle


def list_salles():
    """[2026-09] Référentiel unique, université entière (exception ciblée à
    INT-07, cf. 03_Contrat_Invariants_Campus_Manager.md [V7]) : plus de
    filtrage par UFR — un Gestionnaire dont les salles sont toutes occupées
    doit pouvoir en trouver une ailleurs."""
    return Salle.objects.order_by("nom")


def create_salle(nom: str, capacite: int, type_usage: str) -> Salle:
    """N'importe quel Gestionnaire ou l'Admin peut créer une salle, sans
    rattachement à une UFR — seule l'unicité du nom est garantie."""
    nom_trim = nom.strip()
    if Salle.objects.filter(nom__iexact=nom_trim).exists():
        raise Conflict("Une salle porte déjà ce nom.")

    return Salle.objects.create(nom=nom_trim, capacite=capacite, type_usage=type_usage)
