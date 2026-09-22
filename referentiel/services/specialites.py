"""[V8, 2026-09-21] Spécialités ouvertes par un département à un niveau.

Alimente deux écrans qui n'ont pas les mêmes exigences :

- côté Gestionnaire, l'écran de référentiel où les spécialités se déclarent
  (FR-REF-33) et la liste déroulante du formulaire de groupe ;
- côté public, le cinquième étage de la cascade (FR-PUB-02 révisée), qui ne
  s'active que si le couple (département, niveau) choisi en propose.

Le cloisonnement INT-07 passe par `departement__ufr_id` : `Specialite` n'a
pas de FK vers `Ufr`, son établissement se lit par son département (cf.
referentiel/models.py).
"""

import re

from rest_framework.exceptions import NotFound, ValidationError

from core.exceptions_helpers import Conflict
from core.ufr_scope import resolve_ufr_scope, ufr_filter_kwargs
from referentiel.models import Departement, Specialite
from referentiel.services.groupes import NIVEAUX


def _valider_niveau(niveau: str) -> str:
    """Le niveau est la moitié de l'identité d'une spécialité (cf. la
    contrainte d'unicité) : une valeur hors cycle LMD la rendrait
    introuvable par la cascade publique, qui n'interroge jamais que des
    niveaux de `NIVEAUX`. Mieux vaut refuser à l'écriture que laisser une
    ligne inatteignable s'accumuler en base."""
    valeur = (niveau or "").strip()
    if valeur not in NIVEAUX:
        raise ValidationError(f"Niveau invalide : « {valeur} ». Attendu : {', '.join(NIVEAUX)}.")
    return valeur


def list_specialites(
    user,
    ufr_id_pour_admin: str | None = None,
    departement_id: str | None = None,
    niveau: str | None = None,
    recherche: str | None = None,
):
    """Filtrée EN BASE, jamais dans le navigateur — même choix que pour les
    départements : le temps d'attente doit dépendre de ce qu'on cherche, pas
    de la taille du référentiel.

    `unaccent` avant `icontains` (FR-FILT-02) : sans lui, « genie » ne
    trouverait pas « Génie logiciel »."""
    scope = resolve_ufr_scope(user, ufr_id_pour_admin)
    qs = Specialite.objects.filter(**ufr_filter_kwargs(scope, "departement__ufr_id")).select_related(
        "departement"
    )
    if departement_id:
        qs = qs.filter(departement_id=departement_id)
    if niveau and niveau.strip():
        qs = qs.filter(niveau=niveau.strip())
    if recherche and recherche.strip():
        qs = qs.filter(libelle__unaccent__icontains=recherche.strip())
    # Trié par niveau puis libellé : l'écran de référentiel se lit dans
    # l'ordre du cursus (les choix de L2 ensemble, puis ceux de L3), pas
    # dans un ordre alphabétique qui les entremêlerait.
    return qs.order_by("departement__libelle", "niveau", "libelle")


# Séparateurs acceptés dans la zone de saisie : la virgule d'abord, parce
# que c'est ainsi qu'on énumère en français et que c'est ce que le
# Gestionnaire a spontanément tapé ; le point-virgule et le retour à la
# ligne parce qu'une liste vient souvent d'un copier-coller depuis un
# tableur ou un document.
#
# Conséquence assumée : un libellé de spécialité ne peut donc pas contenir
# de virgule. Aucun n'en contient dans le référentiel de l'UJKZ — un nom de
# spécialité est un syntagme court (« Médecine générale », « Sciences du
# cerveau ») — et l'inverse a été constaté à l'usage : laisser passer la
# virgule produit une spécialité fantôme « a, b, c » qui s'affiche telle
# quelle dans la recherche publique, où l'étudiant ne retrouve alors
# aucune des trois.
SEPARATEURS = re.compile(r"[,;\n\r]+")


def decouper_libelles(brut: str | list | None) -> list[str]:
    """Transforme ce que le Gestionnaire a saisi en liste de libellés.

    Accepte aussi bien une chaîne (« Médecine générale, Sciences du
    cerveau ») qu'une liste déjà découpée par le client. Le découpage se
    fait ICI, côté serveur, et pas seulement dans le navigateur : sans quoi
    un appel direct à l'API — ou un client plus ancien — recréerait
    exactement le défaut qu'on corrige.

    Les doublons internes à une même saisie sont écartés (« Chimie, chimie »
    ne crée qu'une entrée), en conservant l'ordre de frappe : la première
    orthographe tapée est celle qui est retenue.
    """
    morceaux = brut if isinstance(brut, list) else SEPARATEURS.split(brut or "")
    vus: set[str] = set()
    libelles: list[str] = []
    for morceau in morceaux:
        libelle = (str(morceau) or "").strip()
        if not libelle or libelle.casefold() in vus:
            continue
        vus.add(libelle.casefold())
        libelles.append(libelle)
    return libelles


def create_specialites(brut: str | list | None, departement_id: str, niveau: str, user) -> dict:
    """FR-REF-33 : ouvrir une ou PLUSIEURS spécialités d'un seul geste.

    Une seule à la fois était la version initiale, et c'était une erreur
    d'ergonomie : une L2 de portail s'ouvre à trois ou quatre spécialités
    d'un coup, et le Gestionnaire les énumère naturellement en une phrase.
    Il n'y a aucune raison de lui faire répéter le choix du département et
    du niveau à chaque entrée.

    ## Pourquoi un compte rendu plutôt qu'un tout-ou-rien

    Un doublon au milieu du lot n'annule pas le reste. Refuser les trois
    parce que l'une existait déjà obligerait le Gestionnaire à retirer
    lui-même celle qui bloque avant de resoumettre — un travail que le
    Système peut faire à sa place, puisqu'il sait exactement laquelle.
    (C'est l'inverse du passage d'année, `promouvoir_groupes`, qui est
    tout-ou-rien : une campagne de promotion est une décision UNIQUE
    portant sur plusieurs groupes, alors qu'ouvrir des spécialités est une
    suite de déclarations indépendantes.)

    Renvoie les créées et les ignorées, pour que l'écran puisse le dire.
    """
    libelles = decouper_libelles(brut)
    if not libelles:
        raise ValidationError("Le libellé de la spécialité est obligatoire.")

    niveau_valide = _valider_niveau(niveau)
    departement = _departement_du_perimetre(departement_id, user)

    creees: list[Specialite] = []
    doublons: list[str] = []
    for libelle in libelles:
        if Specialite.objects.filter(
            departement_id=departement.id, niveau=niveau_valide, libelle__iexact=libelle
        ).exists():
            doublons.append(libelle)
            continue
        creees.append(
            Specialite.objects.create(libelle=libelle, departement=departement, niveau=niveau_valide)
        )

    if not creees:
        # Rien n'a pu être créé : c'est un échec, pas un succès vide — la
        # vue le traduit en 409 pour que l'écran affiche un message au lieu
        # d'un ajout silencieusement sans effet.
        raise Conflict(
            f"{'Ces spécialités existent déjà' if len(doublons) > 1 else 'Cette spécialité existe déjà'} "
            f"en {niveau_valide} pour ce département : {', '.join(f'« {d} »' for d in doublons)}."
        )

    return {"creees": creees, "doublons": doublons}


def _departement_du_perimetre(departement_id: str, user) -> Departement:
    """Le département vérifié contre le périmètre de l'utilisateur.

    Sans ce contrôle, un `departementId` d'une autre UFR posté à la main
    créerait une spécialité hors périmètre — le seul endroit de cette
    réforme où INT-07 pourrait se contourner, puisque l'UFR n'est pas dans
    la requête mais déduite du département fourni.
    """
    scope = resolve_ufr_scope(user)
    try:
        return Departement.objects.filter(**ufr_filter_kwargs(scope)).get(id=departement_id)
    except Departement.DoesNotExist:
        # Même message qu'un identifiant inexistant : dire « ce département
        # appartient à une autre UFR » confirmerait son existence à qui
        # tâtonne (INT-07 vaut aussi pour ce que les erreurs racontent).
        raise NotFound("Département introuvable.")


def create_specialite(libelle: str, departement_id: str, niveau: str, user) -> Specialite:
    """FR-REF-33 : c'est le Gestionnaire qui ouvre une spécialité, sur SON
    établissement.

    Le département est vérifié contre le périmètre de l'utilisateur plutôt
    que pris tel quel : sans ce contrôle, un `departementId` d'une autre UFR
    posté à la main créerait une spécialité hors périmètre — le seul endroit
    de cette réforme où INT-07 pourrait se contourner, puisque l'UFR n'est
    pas dans la requête mais déduite du département fourni.
    """
    return create_specialites(libelle, departement_id, niveau, user)["creees"][0]


def supprimer_specialite(specialite_id: str, user) -> None:
    """FR-REF-35 : refermer une spécialité ouverte par erreur.

    Contrairement aux départements, la suppression est offerte ici : une
    spécialité est déclarée au fil de l'eau par le Gestionnaire (le
    référentiel officiel de l'UJKZ n'en contient aucune), donc une faute de
    saisie est bien plus probable — et elle serait visible par tous les
    étudiants dans la cascade publique.

    Sans effet sur les groupes existants : `Groupe.specialite` est une
    chaîne dénormalisée (cf. referentiel/models.py). Un programme déjà
    publié garde donc la spécialité sous laquelle il l'a été, ce qui est
    exactement le comportement voulu — supprimer une entrée de référentiel
    ne doit pas réécrire l'historique.
    """
    scope = resolve_ufr_scope(user)
    try:
        specialite = Specialite.objects.filter(
            **ufr_filter_kwargs(scope, "departement__ufr_id")
        ).get(id=specialite_id)
    except Specialite.DoesNotExist:
        raise NotFound("Spécialité introuvable.")
    specialite.delete()


def libelles_pour(ufr_id: str, departement_libelle: str, niveau: str) -> list[str]:
    """Les spécialités proposées au public pour un couple (département,
    niveau) — appelée par la cascade publique.

    Le département arrive ici sous forme de LIBELLÉ et non d'identifiant :
    c'est ce que la cascade publique manipule de bout en bout, parce que
    `Groupe.departement` est lui-même un libellé dénormalisé. Chercher par
    `libelle__iexact` plutôt que par id est donc la jointure correcte ici,
    pas un raccourci.
    """
    return list(
        Specialite.objects.filter(
            departement__ufr_id=ufr_id,
            departement__libelle__iexact=(departement_libelle or "").strip(),
            niveau=(niveau or "").strip(),
        )
        .order_by("libelle")
        .values_list("libelle", flat=True)
    )
