from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from core.exceptions_helpers import Conflict
from core.ufr_scope import resolve_ufr_scope, ufr_filter_kwargs
from referentiel.models import Groupe

# [V6] Niveau atteint l'année suivante — cycle LMD, listé aussi côté front
# (web/src/lib/referentiel-options.ts). L3 et M2 n'ont pas d'entrée : fin de
# cycle (diplôme), il n'y a pas de "L4" à créer — cohérent avec la
# littérature (un jury de fin de cycle statue sur le diplôme, pas sur un
# passage).
NIVEAU_SUIVANT = {"L1": "L2", "L2": "L3", "M1": "M2"}

# Les niveaux du cycle LMD — liste close, identique pour toutes les UFR
# (pendant de NIVEAUX dans web/src/lib/referentiel-options.ts). Source de
# vérité pour la cascade publique, qui les propose tous que la scolarité ait
# saisi un programme ou non (cf. public/services.py).
NIVEAUX = ["L1", "L2", "L3", "M1", "M2"]

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
    return Groupe.objects.filter(**ufr_filter_kwargs(scope)).select_related("groupe_suivant").order_by("nom")


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


def create_groupe(
    nom: str,
    departement: str,
    niveau: str,
    annee_academique: str,
    effectif,
    ufr_id: str,
    specialite: str | None = None,
) -> Groupe:
    """[V8] `specialite` est facultative et le restera : tous les niveaux
    n'en proposent pas (une L1 de portail est un tronc commun), et la rendre
    obligatoire bloquerait la création de ces groupes-là. Elle n'est pas
    vérifiée contre le référentiel des spécialités ici : le Gestionnaire la
    choisit dans une liste déroulante alimentée par ce référentiel, et un
    groupe créé avant l'ouverture d'une spécialité doit pouvoir garder la
    sienne — même raisonnement que pour `departement`, qui n'est pas non
    plus une FK."""
    nom_trim = nom.strip()
    annee_trim = annee_academique.strip()
    # [V6] Scopée par année : "L1 Médecine - Groupe A" doit pouvoir exister
    # à la fois comme historique d'une ancienne promotion et comme nom de
    # la nouvelle promotion de L1 qui arrive l'année suivante — seule une
    # répétition DANS LA MÊME année est un vrai doublon.
    if Groupe.objects.filter(nom__iexact=nom_trim, annee_academique=annee_trim).exists():
        raise Conflict("Un groupe porte déjà ce nom pour cette année académique.")
    return Groupe.objects.create(
        nom=nom_trim,
        departement=departement.strip(),
        niveau=niveau.strip(),
        specialite=(specialite or "").strip(),
        annee_academique=annee_trim,
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
        # [V6] Scopée par année (même raison que create_groupe) : l'année
        # cible est celle fournie dans CETTE requête si elle en change une,
        # sinon celle déjà portée par le groupe.
        annee_verif = (donnees.get("anneeAcademique") or "").strip() or groupe.annee_academique
        if Groupe.objects.filter(nom__iexact=nom_trim, annee_academique=annee_verif).exclude(id=groupe_id).exists():
            raise Conflict("Un groupe porte déjà ce nom pour cette année académique.")
        groupe.nom = nom_trim
        champs.append("nom")
    # [V8] "specialite" est dans la liste : un groupe peut avoir été créé
    # avant que sa spécialité n'existe au référentiel, ou s'être trompé de
    # choix — c'est le seul moyen de le corriger sans recréer le groupe (et
    # donc sans perdre son programme).
    for champ, cle in (
        ("departement", "departement"),
        ("niveau", "niveau"),
        ("specialite", "specialite"),
        ("annee_academique", "anneeAcademique"),
    ):
        if cle in donnees:
            setattr(groupe, champ, (donnees[cle] or "").strip())
            champs.append(champ)
    if "effectif" in donnees:
        groupe.effectif = _valider_effectif(donnees["effectif"])
        champs.append("effectif")

    if champs:
        groupe.save(update_fields=champs)
    return groupe


def _annee_suivante(annee_academique: str) -> str:
    try:
        debut, fin = annee_academique.split("-")
        return f"{int(debut) + 1}-{int(fin) + 1}"
    except (ValueError, AttributeError):
        raise ValidationError(f"Année académique source invalide : « {annee_academique} ».")


def promouvoir_groupes(items: list[dict], annee_cible: str, user) -> list[Groupe]:
    """[V6] Passage à l'année supérieure. FR-REF-12 le décrivait depuis la V2
    ("une promotion se fait en créant un nouveau Groupe, jamais en modifiant
    celui-ci sur place") sans qu'aucun mécanisme ne l'assiste : le
    Gestionnaire ressaisissait le groupe de zéro chaque rentrée.

    Reste une décision humaine, jamais automatique : comme un jury de fin
    d'année (cf. recherche menée en 2026-09-14 sur les pratiques réelles de
    passage de niveau universitaire), le Système propose le niveau suivant
    et préremplit l'effectif avec la valeur actuelle, mais c'est au
    Gestionnaire de la corriger — l'effectif diminue naturellement d'une
    année sur l'autre (abandons, redoublements) et rien ne permet au
    Système de connaître le nouveau chiffre à sa place (même limite déjà
    posée par FR-REF-19 : c'est une saisie, pas un calcul).

    Tout-ou-rien (transaction) : une campagne de passage est une décision
    unique portant sur plusieurs groupes, pas une suite d'opérations
    indépendantes — un groupe invalide au milieu du lot ne doit pas laisser
    les précédents à moitié appliqués.
    """
    if not items:
        raise ValidationError("Aucun groupe sélectionné.")

    with transaction.atomic():
        crees = []
        for item in items:
            groupe = get_groupe(item.get("id", ""))

            if user.role == "scolarite" and groupe.ufr_id != user.ufr_id:
                raise Conflict("Ce groupe appartient à une autre UFR.")

            niveau_cible = NIVEAU_SUIVANT.get(groupe.niveau)
            if niveau_cible is None:
                raise ValidationError(f"« {groupe.nom} » est en fin de cycle ({groupe.niveau}) : pas de passage possible.")

            if _annee_suivante(groupe.annee_academique) != annee_cible:
                raise ValidationError(
                    f"« {groupe.nom} » ({groupe.annee_academique}) n'est pas éligible pour un passage vers {annee_cible}."
                )

            if Groupe.objects.filter(promu_de_id=groupe.id).exists():
                raise Conflict(f"« {groupe.nom} » a déjà été promu.")

            # Pas de repli sur groupe.nom : ce nom est déjà pris par le
            # groupe source lui-même (contrainte d'unicité), donc la
            # création échouerait systématiquement. Le nom du groupe cible
            # est donc obligatoire ici — au front, le champ est pré-rempli
            # (niveau substitué dans le nom) mais reste modifiable.
            nom = (item.get("nom") or "").strip()
            if not nom:
                raise ValidationError(f"Le nom du groupe issu de « {groupe.nom} » est obligatoire.")
            # [V6] Scopée par année cible : rien n'empêche de reprendre pour
            # 2026-2027 un nom déjà utilisé par un groupe DEVENU historique
            # d'une autre année (ex. la promotion de L1 précédente).
            if Groupe.objects.filter(nom__iexact=nom, annee_academique=annee_cible).exists():
                raise Conflict(f"Un groupe porte déjà le nom « {nom} » pour l'année {annee_cible}.")

            crees.append(
                Groupe.objects.create(
                    nom=nom,
                    departement=groupe.departement,
                    niveau=niveau_cible,
                    # [V8] Reprise de la spécialité du groupe source, mais
                    # MODIFIABLE par le Gestionnaire dans la même requête —
                    # et c'est tout l'intérêt : le passage d'année est
                    # précisément le moment où une cohorte de portail se
                    # scinde (une L1 MPCI sans spécialité devient plusieurs
                    # L2 Maths / Physique / Chimie / Informatique). Reporter
                    # la valeur source sans permettre de la changer aurait
                    # rendu le mécanisme inutilisable pour ce cas, qui est
                    # justement celui qui a motivé la réforme.
                    specialite=(item.get("specialite") or groupe.specialite or "").strip(),
                    annee_academique=annee_cible,
                    effectif=_valider_effectif(item.get("effectif", groupe.effectif)),
                    ufr_id=groupe.ufr_id,
                    promu_de=groupe,
                )
            )
        return crees
