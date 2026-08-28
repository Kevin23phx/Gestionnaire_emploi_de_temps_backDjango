from django.db import transaction
from rest_framework.exceptions import NotFound

from accounts.models import Enseignant, EnseignantUfr, Role, Utilisateur
from core.exceptions_helpers import Conflict


def list_enseignants():
    """Volontairement pas scopé par UFR (répertoire global) : un
    Gestionnaire doit pouvoir retrouver un enseignant déjà affecté à une
    AUTRE UFR pour l'affecter aussi à la sienne (FR-REF-06) plutôt que d'en
    recréer un doublon."""
    return Enseignant.objects.prefetch_related("ufrs").order_by("nom")


@transaction.atomic
def create_enseignant(nom: str, prenom: str, identifiant: str, ufr_id: str) -> dict:
    if Utilisateur.objects.filter(identifiant=identifiant).exists():
        raise Conflict("Cet identifiant est déjà utilisé par un autre compte.")

    enseignant = Enseignant.objects.create(nom=nom, prenom=prenom)
    EnseignantUfr.objects.create(enseignant=enseignant, ufr_id=ufr_id)
    # mot_de_passe_hash absent : le compte reste "non activé" jusqu'à ce que
    # l'enseignant l'active lui-même (FR-AUTH-03/04) — la Scolarité ne
    # saisit jamais de mot de passe pour un tiers.
    Utilisateur.objects.create(
        identifiant=identifiant,
        nom=nom,
        prenom=prenom,
        role=Role.ENSEIGNANT,
        enseignant=enseignant,
    )
    return {"enseignant": enseignant, "identifiant": identifiant}


def affecter_ufr(enseignant_id: str, ufr_id: str) -> EnseignantUfr:
    """FR-REF-06 : rattache un enseignant DÉJÀ existant à une UFR
    supplémentaire — permet à "un enseignant d'intervenir dans plusieurs
    UFR" sans jamais dupliquer sa fiche Enseignant."""
    from core.models import Ufr

    if not Enseignant.objects.filter(id=enseignant_id).exists():
        raise NotFound("Enseignant introuvable.")
    if not Ufr.objects.filter(id=ufr_id).exists():
        raise NotFound("UFR introuvable.")
    if EnseignantUfr.objects.filter(enseignant_id=enseignant_id, ufr_id=ufr_id).exists():
        raise Conflict("Cet enseignant est déjà affecté à cette UFR.")

    return EnseignantUfr.objects.create(enseignant_id=enseignant_id, ufr_id=ufr_id)
