from django.db import transaction
from django.db.models import Q
from rest_framework.exceptions import NotFound

from accounts.models import Enseignant, EnseignantUfr
from core.exceptions_helpers import Conflict


def list_enseignants(recherche: str | None = None):
    """Volontairement pas scopé par UFR (répertoire global) : un
    Gestionnaire doit pouvoir retrouver un enseignant déjà affecté à une
    AUTRE UFR pour l'affecter aussi à la sienne (FR-REF-06) plutôt que d'en
    recréer un doublon.

    [V3] FR-FILT-04 : la recherche existe précisément pour ce cas — vérifier
    qu'un enseignant est déjà connu AVANT d'en créer un doublon, sans
    quitter le formulaire de créneau."""
    qs = Enseignant.objects.prefetch_related("ufrs").order_by("nom")
    if recherche:
        # FR-FILT-02 : « kabore » doit trouver « Kaboré ».
        qs = qs.filter(Q(nom__unaccent__icontains=recherche) | Q(prenom__unaccent__icontains=recherche))
    return qs


@transaction.atomic
def create_enseignant(nom: str, prenom: str, ufr_id: str) -> Enseignant:
    """[V3] FR-REF-04 révisée : enregistre une FICHE d'enseignant, plus un
    compte. FR-REF-05 (activation du compte enseignant) est retirée avec le
    rôle correspondant — il n'y a plus rien à activer.

    Le doublon se contrôle désormais sur le nom, plus sur un identifiant de
    connexion qui n'existe plus. Volontairement non bloquant en cas
    d'homonymie exacte : deux enseignants peuvent réellement porter le même
    nom, et refuser la création obligerait le Gestionnaire à renoncer en
    pleine saisie de créneau — exactement le genre de blocage que FR-REF-06
    a fait retirer de l'affectation Enseignant↔UFR.
    """
    enseignant = Enseignant.objects.create(nom=nom.strip(), prenom=prenom.strip())
    EnseignantUfr.objects.create(enseignant=enseignant, ufr_id=ufr_id)
    return enseignant


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
