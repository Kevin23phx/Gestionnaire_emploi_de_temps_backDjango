from rest_framework.exceptions import NotFound, ValidationError

from core.exceptions_helpers import Conflict
from core.ufr_scope import resolve_ufr_scope, ufr_filter_kwargs
from referentiel.models import Groupe

# [V3.1] "effectif" est une colonne saisie par le Gestionnaire, plus un
# COUNT(Etudiant) : le référentiel nominatif des étudiants a été supprimé
# (voir referentiel/models.py). Le moteur de conflits lit donc directement
# cette valeur pour la comparer à la capacité d'une salle (RM-02).
#
# INT-07 (V2) : un Gestionnaire ne voit/crée jamais de groupe hors de sa
# propre UFR ; un Admin voit tout (lecture seule, FR-ADMIN-03), ou une seule
# UFR choisie (FR-ADMIN-06).


def list_groupes(user, ufr_id_pour_admin: str | None = None):
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    return Groupe.objects.filter(**ufr_filter_kwargs(scope)).order_by("nom")


def get_groupe(groupe_id: str) -> Groupe:
    try:
        return Groupe.objects.get(id=groupe_id)
    except Groupe.DoesNotExist:
        raise NotFound("Groupe introuvable.")


def _valider_effectif(effectif) -> int:
    """Un effectif négatif ou non numérique désactiverait silencieusement la
    détection de conflit de capacité, qui est la seule chose que cette
    valeur sert à alimenter."""
    try:
        valeur = int(effectif)
    except (TypeError, ValueError):
        raise ValidationError("L'effectif doit être un nombre entier.")
    if valeur < 0:
        raise ValidationError("L'effectif ne peut pas être négatif.")
    return valeur


def create_groupe(nom: str, departement: str, niveau: str, annee_academique: str, effectif, ufr_id: str) -> Groupe:
    nom_trim = nom.strip()
    if Groupe.objects.filter(nom__iexact=nom_trim).exists():
        raise Conflict("Un groupe porte déjà ce nom.")
    return Groupe.objects.create(
        nom=nom_trim,
        departement=departement.strip(),
        niveau=niveau.strip(),
        annee_academique=annee_academique.strip(),
        effectif=_valider_effectif(effectif),
        ufr_id=ufr_id,
    )


def update_groupe(groupe_id: str, donnees: dict, user) -> Groupe:
    """[V3.1] L'effectif d'un groupe bouge en cours d'année (abandons,
    inscriptions tardives) : il doit rester modifiable, sans quoi la
    détection de conflit de capacité travaillerait sur une valeur périmée."""
    groupe = get_groupe(groupe_id)

    # INT-07 : jamais un groupe d'une autre UFR.
    if user.role == "scolarite" and groupe.ufr_id != user.ufr_id:
        raise Conflict("Ce groupe appartient à une autre UFR.")

    champs = []
    if "nom" in donnees:
        nom_trim = (donnees["nom"] or "").strip()
        if not nom_trim:
            raise ValidationError("Le nom est obligatoire.")
        if Groupe.objects.filter(nom__iexact=nom_trim).exclude(id=groupe_id).exists():
            raise Conflict("Un groupe porte déjà ce nom.")
        groupe.nom = nom_trim
        champs.append("nom")
    for champ, cle in (("departement", "departement"), ("niveau", "niveau"), ("annee_academique", "anneeAcademique")):
        if cle in donnees:
            setattr(groupe, champ, (donnees[cle] or "").strip())
            champs.append(champ)
    if "effectif" in donnees:
        groupe.effectif = _valider_effectif(donnees["effectif"])
        champs.append("effectif")

    if champs:
        groupe.save(update_fields=champs)
    return groupe
