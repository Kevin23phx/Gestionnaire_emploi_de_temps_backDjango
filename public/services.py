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

from rest_framework.exceptions import NotFound, ValidationError

from core.models import Ufr
from core.time_utils import minutes_to_hhmm
from planning.models import Creneau
from referentiel.models import Groupe

JOURS_ORDRE = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]
JOURS_INDEX = {jour: i for i, jour in enumerate(JOURS_ORDRE)}


# ---------------------------------------------------------------------------
# Cascade de sélection (FR-PUB-02)
# ---------------------------------------------------------------------------
# Chaque étage ne propose que des valeurs qui mènent réellement quelque part :
# elles sont dérivées des groupes existants, jamais d'une liste écrite en dur.
# C'est ce qui garantit qu'un visiteur ne peut pas construire une combinaison
# vide en suivant l'interface — ERR-07 ne couvre alors que le cas d'un
# programme réellement dépourvu de créneau.


def list_ufrs() -> list[dict]:
    return [
        # [V3.2] "sigleAffiche" porte la règle de préfixe ("UFR/SH" mais
        # "IBAM") : c'est ce que le visiteur lit au premier étage de la
        # cascade, l'écran où le vocabulaire compte le plus.
        {"id": u.id, "nom": u.nom, "sigle": u.sigle, "type": u.type, "sigleAffiche": u.sigle_affiche}
        for u in Ufr.objects.filter(groupes__isnull=False).distinct().order_by("nom")
    ]


def list_filieres(ufr_id: str) -> list[str]:
    return sorted(
        Groupe.objects.filter(ufr_id=ufr_id).values_list("filiere", flat=True).distinct()
    )


def list_niveaux(ufr_id: str, filiere: str) -> list[str]:
    return sorted(
        Groupe.objects.filter(ufr_id=ufr_id, filiere=filiere).values_list("niveau", flat=True).distinct()
    )


def list_groupes(ufr_id: str, filiere: str, niveau: str) -> list[dict]:
    """Dernier étage de la cascade. Le nombre de créneaux accompagne chaque
    groupe pour que le visiteur distingue, AVANT de cliquer, un programme
    rempli d'un programme encore vide (ERR-07)."""
    from django.db.models import Count

    groupes = (
        Groupe.objects.filter(ufr_id=ufr_id, filiere=filiere, niveau=niveau)
        .annotate(nb_creneaux=Count("creneaux"))
        .order_by("nom")
    )
    return [
        {
            "id": g.id,
            "nom": g.nom,
            "filiere": g.filiere,
            "niveau": g.niveau,
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


def _projeter_creneau(creneau: Creneau, date: datetime.date) -> dict:
    """LA liste blanche. Tout ce qui sort de la surface publique passe ici.

    Ne contient que ce que FR-PUB-03 énumère : UE, enseignant, salle,
    horaire, statut, motif. Pas d'effectif, pas d'identifiant de groupe
    d'étudiant, rien qui puisse remonter jusqu'à une personne inscrite.
    """
    annulation = next((sa for sa in creneau.seances_annulees.all() if sa.date == date), None)

    if annulation is not None:
        # INV-15 : la séance reste dans le programme, signalée. La faire
        # disparaître serait le plus sûr moyen que l'étudiant se déplace
        # quand même.
        statut, motif = "annule_seance", annulation.motif
    elif creneau.statut == "annule":
        statut, motif = "annule", creneau.motif
    else:
        statut, motif = creneau.statut, creneau.motif

    return {
        "id": creneau.id,
        "date": date.isoformat(),
        "jour": creneau.jour,
        "heureDebut": minutes_to_hhmm(creneau.heure_debut_minutes),
        "heureFin": minutes_to_hhmm(creneau.heure_fin_minutes),
        "ue": {"code": creneau.ue.code, "intitule": creneau.ue.intitule, "niveau": creneau.ue.niveau},
        "enseignant": f"{creneau.enseignant.prenom} {creneau.enseignant.nom}".strip(),
        "salle": {"nom": creneau.salle.nom, "batiment": creneau.salle.batiment},
        "statut": statut,
        "motif": motif,
    }


def programme_semaine(groupe_id: str, semaine: str | None) -> dict:
    groupe = get_groupe_public(groupe_id)

    if semaine:
        try:
            lundi = lundi_de(datetime.date.fromisoformat(semaine))
        except ValueError:
            raise ValidationError("Semaine invalide (format attendu : AAAA-MM-JJ).")
    else:
        lundi = _semaine_par_defaut(groupe.ufr)

    creneaux = (
        Creneau.objects.filter(groupe_id=groupe_id)
        .select_related("ue", "enseignant", "salle")
        .prefetch_related("seances_annulees")
        .order_by("heure_debut_minutes")
    )

    seances = [_projeter_creneau(c, lundi + datetime.timedelta(days=JOURS_INDEX[c.jour])) for c in creneaux]
    seances.sort(key=lambda s: (s["date"], s["heureDebut"]))

    ufr = groupe.ufr
    return {
        "groupe": {
            "id": groupe.id,
            "nom": groupe.nom,
            "filiere": groupe.filiere,
            "niveau": groupe.niveau,
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
            "periodeDebut": ufr.periode_debut.isoformat() if ufr.periode_debut else None,
            "periodeFin": ufr.periode_fin.isoformat() if ufr.periode_fin else None,
            "periodeLibelle": ufr.periode_libelle,
            "horsPeriode": bool(
                ufr.periode_definie and not (ufr.periode_debut <= lundi + datetime.timedelta(days=5) and lundi <= ufr.periode_fin)
            ),
        },
        "seances": seances,
    }


def _semaine_par_defaut(ufr: Ufr) -> datetime.date:
    """La semaine courante — sauf si l'on est hors période académique, auquel
    cas on ouvre sur la première semaine de la période plutôt que sur une
    grille vide qui laisserait croire que le programme n'existe pas."""
    aujourdhui = datetime.date.today()
    if ufr.periode_definie:
        if aujourdhui < ufr.periode_debut:
            return lundi_de(ufr.periode_debut)
        if aujourdhui > ufr.periode_fin:
            return lundi_de(ufr.periode_fin)
    return lundi_de(aujourdhui)
