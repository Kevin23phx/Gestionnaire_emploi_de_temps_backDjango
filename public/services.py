"""[V3] Projection publique du programme (FR-PUB-01→03, RM-09).

Ce module ne réutilise DÉLIBÉRÉMENT aucun sérialiseur ni aucun DTO de
`planning` ou `referentiel`, alors que la tentation est forte et que le
résultat se ressemble beaucoup aujourd'hui. La raison tient à ce qui se
passera dans six mois : le jour où quelqu'un ajoutera un champ à un
sérialiseur partagé — le nom du délégué de groupe, un effectif nominatif,
n'importe quoi — ce champ partirait sur Internet sans qu'aucune revue ne
l'attrape, parce que rien dans le code n'aurait signalé que ce sérialiseur
a un pied dehors. Ici, la liste des champs publiés est écrite en toutes
lettres, à un seul endroit, et tout ajout est un acte conscient (INV-12,
INT-10, NFR-SEC-03).
"""

import datetime

from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError

from core.models import Ufr
from core.time_utils import minutes_to_hhmm
from planning.models import Creneau
from referentiel.models import Departement, Groupe
from referentiel.services.groupes import NIVEAUX
from referentiel.services.specialites import libelles_pour as specialites_pour

JOURS_ORDRE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]
JOURS_INDEX = {jour: i for i, jour in enumerate(JOURS_ORDRE)}


# ---------------------------------------------------------------------------
# Cascade de sélection (FR-PUB-02)
# ---------------------------------------------------------------------------
# [2026-09] Retour du porteur de projet : la cascade ne se limite PLUS à ce
# qui mène à un programme existant.
#
# Jusqu'ici chaque étage n'exposait que les valeurs tirées des groupes déjà
# créés. C'était défendable sur le papier (« on ne peut pas s'engager dans un
# chemin vide »), mais à l'écran cela donnait ceci : un étudiant de L2 qui
# vient chercher son emploi du temps ne voit même pas « L2 » dans la liste
# tant que la scolarité ne l'a pas saisi. Il ne peut pas distinguer « ce
# parcours n'existe pas » de « ce parcours n'est pas encore publié », et
# l'interface ressemble à une liste trouée.
#
# Les étages proposent donc désormais le RÉFÉRENTIEL (les établissements,
# les départements officiels, les niveaux du LMD, les années académiques
# courantes), et c'est le dernier étage qui répond en toutes lettres quand la
# combinaison choisie n'a pas encore de programme — cf. ERR-07, qui ne
# couvrait jusque-là que le programme vide et couvre maintenant aussi la
# combinaison sans groupe.


def _annees_courantes(reference: datetime.date | None = None) -> list[str]:
    """Les trois années académiques utiles : la précédente, la courante, la
    suivante. Calculées et non écrites en dur, exactement comme côté
    gestionnaire (web/src/lib/referentiel-options.ts) — une liste figée
    deviendrait fausse en silence à la rentrée. L'année universitaire bascule
    en août."""
    reference = reference or datetime.date.today()
    depart = reference.year if reference.month >= 8 else reference.year - 1
    return [f"{depart + d}-{depart + d + 1}" for d in (-1, 0, 1)]


def list_annees() -> list[str]:
    """[2026-09] Les années courantes, plus toute année déjà portée par un
    groupe (une promotion archivée reste consultable). Triées la plus récente
    en premier : c'est celle qu'un visiteur cherche le plus souvent."""
    saisies = set(Groupe.objects.values_list("annee_academique", flat=True).distinct())
    return sorted(saisies | set(_annees_courantes()), reverse=True)


def list_ufrs(annee_academique: str | None = None) -> list[dict]:
    """[2026-09] Tous les établissements, y compris ceux dont aucun programme
    n'est encore publié. `annee_academique` n'est plus un filtre : une UFR ne
    cesse pas d'exister l'année où sa scolarité n'a rien saisi."""
    # Tri sur le SIGLE AFFICHÉ, pas sur le nom complet : c'est le sigle que
    # le visiteur lit dans la liste. Trié sur le nom, elle paraissait en
    # désordre (ISSDH avant IPERMIC). `sigle_affiche` étant une propriété
    # Python, le tri ne peut pas se faire en SQL — 12 lignes, sans enjeu.
    ufrs = sorted(Ufr.objects.all(), key=lambda u: u.sigle_affiche)
    return [
        # [V3.2] "sigleAffiche" porte la règle de préfixe ("UFR/SH" mais
        # "IBAM") : c'est ce que le visiteur lit au premier étage de la
        # cascade, l'écran où le vocabulaire compte le plus.
        {"id": u.id, "nom": u.nom, "sigle": u.sigle, "type": u.type, "sigleAffiche": u.sigle_affiche}
        for u in ufrs
    ]


def list_departements(ufr_id: str, annee_academique: str | None = None) -> list[str]:
    """[2026-09] Les départements OFFICIELS de l'établissement (FR-REF-20),
    plus ceux que portent ses groupes — un groupe antérieur au référentiel
    des départements ne doit pas disparaître de la cascade parce que son
    libellé n'y figure pas encore."""
    officiels = Departement.objects.filter(ufr_id=ufr_id).values_list("libelle", flat=True)
    portes = Groupe.objects.filter(ufr_id=ufr_id).values_list("departement", flat=True).distinct()
    return sorted({d for d in [*officiels, *portes] if d})


def list_niveaux(ufr_id: str, departement: str, annee_academique: str | None = None) -> list[str]:
    """[2026-09] Les niveaux du LMD — liste close, la même pour toutes les
    UFR (elle vient de referentiel.services.groupes, source de vérité) — plus
    tout niveau déjà porté par un groupe de ce département."""
    portes = (
        Groupe.objects.filter(ufr_id=ufr_id, departement=departement)
        .values_list("niveau", flat=True)
        .distinct()
    )
    return sorted({n for n in [*NIVEAUX, *portes] if n})


def list_specialites(ufr_id: str, departement: str, niveau: str) -> list[str]:
    """[V8] Cinquième étage de la cascade — et le seul qui puisse être VIDE
    sans que ce soit une anomalie.

    C'est tout le sens de la réforme : en L1, une licence de portail (MPCI)
    est un tronc commun, il n'y a rien à choisir ; en L2, la même cohorte se
    répartit entre Mathématiques, Physique, Chimie et Informatique. Une
    liste vide signifie donc « ce niveau ne propose aucun choix », pas
    « rien n'est encore saisi » — d'où l'étage désactivé plutôt que
    masqué côté visiteur, qui rend la règle lisible au lieu de faire
    apparaître et disparaître un champ.

    Les spécialités PORTÉES par les groupes existants complètent le
    référentiel, comme pour les départements et les niveaux (voir plus
    haut) : un groupe saisi avant l'ouverture de sa spécialité — ou dont la
    spécialité a depuis été refermée — ne doit pas devenir introuvable
    parce que le référentiel ne la contient plus.
    """
    officielles = specialites_pour(ufr_id, departement, niveau)
    groupes = Groupe.objects.filter(ufr_id=ufr_id, departement=departement, niveau=niveau)
    portees_par_groupes = groupes.exclude(specialite="").values_list("specialite", flat=True).distinct()
    # [V8.1] Et celles portées par les CRÉNEAUX de ces groupes : c'est
    # désormais le cas normal (un groupe unique, des créneaux affectés), et
    # sans cette union un programme entier resterait introuvable dès que sa
    # spécialité aurait été refermée au référentiel.
    portees_par_creneaux = (
        Creneau.objects.filter(groupe__in=groupes).exclude(specialite="").values_list("specialite", flat=True).distinct()
    )
    return sorted({s for s in [*officielles, *portees_par_groupes, *portees_par_creneaux] if s})


def list_groupes(
    ufr_id: str,
    departement: str,
    niveau: str,
    annee_academique: str | None = None,
    specialite: str | None = None,
) -> list[dict]:
    """Dernier étage de la cascade. Le nombre de créneaux accompagne chaque
    groupe pour que le visiteur distingue, AVANT de cliquer, un programme
    rempli d'un programme encore vide (ERR-07)."""
    from django.db.models import Count

    groupes = Groupe.objects.filter(ufr_id=ufr_id, departement=departement, niveau=niveau)
    if annee_academique:
        groupes = groupes.filter(annee_academique=annee_academique)
    # [V8] Filtre appliqué seulement si une spécialité est demandée. Ne pas
    # en demander veut dire « tous les groupes de ce niveau » (cas d'un
    # niveau sans spécialité, ou d'un favori enregistré avant la réforme),
    # et surtout PAS « ceux dont la spécialité est vide » — ce qui
    # masquerait tous les groupes spécialisés au visiteur qui n'a pas
    # touché au champ.
    #
    # [V8.1] Un groupe SANS spécialité est retenu lui aussi, et c'est
    # désormais le cas principal : depuis que l'affectation se fait au
    # créneau, la scolarité tient UN groupe « L2 Médecine » dont certains
    # cours sont communs et d'autres propres à chaque spécialité. Ne garder
    # que les groupes portant le libellé exact ne renverrait plus rien du
    # tout dans ce modèle. Les deux façons de faire cohabitent donc : un
    # groupe dédié à une spécialité (V8) et un groupe unique à créneaux
    # affectés (V8.1) répondent tous deux à la même recherche.
    if specialite and specialite.strip():
        groupes = groupes.filter(Q(specialite="") | Q(specialite__iexact=specialite.strip()))
    groupes = groupes.annotate(nb_creneaux=Count("creneaux")).order_by("nom")
    return [
        {
            "id": g.id,
            "nom": g.nom,
            "departement": g.departement,
            "niveau": g.niveau,
            "specialite": g.specialite,
            "anneeAcademique": g.annee_academique,
            "nbCreneaux": g.nb_creneaux,
        }
        for g in groupes
    ]


# ---------------------------------------------------------------------------
# Programme d'une semaine (FR-PUB-03 / FR-EDT-09)
# ---------------------------------------------------------------------------


def lundi_de(date: datetime.date) -> datetime.date:
    return date - datetime.timedelta(days=date.weekday())


def get_groupe_public(groupe_id: str) -> Groupe:
    try:
        return Groupe.objects.select_related("ufr").get(id=groupe_id)
    except Groupe.DoesNotExist:
        # ERR-08 : le favori d'un visiteur pointe vers un groupe supprimé.
        raise NotFound("Ce programme n'existe plus. Refaites une recherche.")


def _projeter_creneau(creneau: Creneau) -> dict:
    """LA liste blanche. Tout ce qui sort de la surface publique passe ici.

    Ne contient que ce que FR-PUB-03 énumère : UE, enseignant, salle,
    horaire, statut, motif. Pas d'effectif, pas d'identifiant de groupe
    d'étudiant, rien qui puisse remonter jusqu'à une personne inscrite.
    """
    # [V4] Plus de distinction « séance annulée » / « cours annulé » : un
    # créneau EST une séance datée, l'annuler n'annule que celle-là.
    # INV-15 tient toujours : elle reste dans le programme, signalée, plutôt
    # que de disparaître — la faire disparaître serait le plus sûr moyen que
    # l'étudiant se déplace quand même.
    return {
        "id": creneau.id,
        "date": creneau.date.isoformat(),
        "jour": creneau.jour,
        "heureDebut": minutes_to_hhmm(creneau.heure_debut_minutes),
        "heureFin": minutes_to_hhmm(creneau.heure_fin_minutes),
        "ue": {"code": creneau.ue.code, "intitule": creneau.ue.intitule},
        "enseignant": f"{creneau.enseignant.prenom} {creneau.enseignant.nom}".strip(),
        "salle": {"nom": creneau.salle.nom},
        "statut": creneau.statut,
        "motif": creneau.motif,
        # [V8.1] Vide = cours commun à toute la promotion. Publiée pour que
        # l'étudiant distingue, sur sa propre feuille, un cours de tronc
        # commun d'un cours de sa spécialité — et pour qu'un visiteur qui
        # consulte le programme complet du groupe sache à qui chaque séance
        # s'adresse.
        "specialite": creneau.specialite,
    }


def filtre_specialite(specialite: str | None):
    """[V8.1] Clause de filtre commune au programme web et au flux
    calendrier — nom public (sans underscore) parce qu'elle est partagée
    entre les deux modules, et qu'une règle dupliquée finirait par
    diverger : un étudiant verrait alors deux emplois du temps différents
    selon qu'il consulte le site ou son agenda.

    Le programme d'une spécialité = les cours qui lui sont
    affectés **plus les cours communs**, jamais les seconds sans les
    premiers.

    C'est la règle centrale du mécanisme d'affectation : un étudiant de L2
    Médecine spécialité Informatique suit l'anatomie (commune à toute la
    promotion) ET l'algorithmique (propre à sa spécialité). Ne lui montrer
    que les cours portant son libellé lui cacherait la moitié de sa semaine
    — et il se présenterait aux examens d'un cours qu'il n'a jamais vu à
    son emploi du temps.

    Aucune spécialité demandée = aucun filtre, donc le programme COMPLET du
    groupe, toutes spécialités confondues. C'est la lecture juste pour un
    niveau de tronc commun (il n'y a rien d'autre), et pour un gestionnaire
    ou un visiteur qui veut voir l'ensemble. Chaque séance porte son
    libellé, l'affichage reste donc lisible.
    """
    valeur = (specialite or "").strip()
    if not valeur:
        return None
    return Q(specialite="") | Q(specialite__iexact=valeur)


def programme_semaine(groupe_id: str, semaine: str | None, specialite: str | None = None) -> dict:
    groupe = get_groupe_public(groupe_id)

    if semaine:
        try:
            lundi = lundi_de(datetime.date.fromisoformat(semaine))
        except ValueError:
            raise ValidationError("Semaine invalide (format attendu : AAAA-MM-JJ).")
    else:
        # La spécialité est transmise : pour un étudiant d'Informatique, la
        # « prochaine semaine publiée » est celle où SON programme a des
        # cours, pas celle où la Chimie en a.
        lundi = _semaine_par_defaut(groupe_id, specialite)

    # [V4] Filtré sur la semaine demandée. Le programme est publié semaine
    # par semaine : une semaine sans créneau est une semaine sans cours, pas
    # une erreur.
    samedi = lundi + datetime.timedelta(days=5)
    creneaux = Creneau.objects.filter(groupe_id=groupe_id, date__gte=lundi, date__lte=samedi)
    filtre = filtre_specialite(specialite)
    if filtre is not None:
        creneaux = creneaux.filter(filtre)
    creneaux = creneaux.select_related("ue", "enseignant", "salle").order_by("date", "heure_debut_minutes")
    seances = [_projeter_creneau(c) for c in creneaux]

    ufr = groupe.ufr
    return {
        "groupe": {
            "id": groupe.id,
            "nom": groupe.nom,
            "departement": groupe.departement,
            "niveau": groupe.niveau,
            # [V8] Spécialité portée par le GROUPE lui-même (cas d'une
            # promotion dédiée). Souvent vide depuis la V8.1, où la
            # scolarité tient un groupe unique et affecte les créneaux.
            "specialite": groupe.specialite,
            # [V8.1] Spécialité effectivement CONSULTÉE — celle que le
            # visiteur a choisie dans la cascade. C'est elle qui titre la
            # feuille (« L2 Médecine — Informatique ») ; sans elle, deux
            # programmes différents du même groupe s'afficheraient sous un
            # en-tête identique.
            "specialiteConsultee": (specialite or "").strip() or groupe.specialite,
            "anneeAcademique": groupe.annee_academique,
            "ufr": {
                "id": ufr.id,
                "nom": ufr.nom,
                "sigle": ufr.sigle,
                "type": ufr.type,
                "sigleAffiche": ufr.sigle_affiche,
            },
        },
        "semaine": {
            "lundi": lundi.isoformat(),
            "samedi": (lundi + datetime.timedelta(days=5)).isoformat(),
            # Les bornes de navigation viennent de la période académique de
            # l'UFR (FR-REF-16) : on ne laisse pas le visiteur feuilleter
            # indéfiniment des semaines où rien n'a jamais été programmé.
            # [V4] Aucune borne : les dates de semestre ont disparu avec la
            # récurrence. Le visiteur navigue librement ; une semaine sans
            # programme le dit simplement.
            "publie": bool(seances),
        },
        "seances": seances,
    }


def _semaine_par_defaut(groupe_id: str, specialite: str | None = None) -> datetime.date:
    """[V4] La semaine courante si elle a un programme ; sinon la prochaine
    semaine publiée.

    À l'UJKZ le programme sort en fin de semaine pour la suivante : un
    étudiant qui consulte le samedi doit tomber sur ce qui vient d'être
    publié, pas sur une grille vide qui lui laisserait croire qu'il n'y a
    rien. À défaut de semaine à venir, on retombe sur la dernière publiée
    plutôt que sur du vide."""
    aujourdhui = datetime.date.today()
    semaine = lundi_de(aujourdhui)

    base = Creneau.objects.filter(groupe_id=groupe_id)
    filtre = filtre_specialite(specialite)
    if filtre is not None:
        base = base.filter(filtre)

    if base.filter(date__gte=semaine, date__lte=semaine + datetime.timedelta(days=5)).exists():
        return semaine

    prochaine = base.filter(date__gt=aujourdhui).order_by("date").first()
    if prochaine:
        return lundi_de(prochaine.date)
    derniere = base.order_by("-date").first()
    return lundi_de(derniere.date) if derniere else semaine
