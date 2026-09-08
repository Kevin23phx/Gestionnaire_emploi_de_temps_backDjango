"""[V3] Génération du flux iCalendar d'un groupe (FR-PUB-05/06/07, INV-13/15).

Un abonnement iCalendar n'est pas un export : le fournisseur d'agenda du
visiteur revient lire cette URL de lui-même, indéfiniment. Trois détails
décident si le mécanisme rend vraiment le service promis, et aucun des trois
n'est cosmétique :

1. `UID` stable + `SEQUENCE` croissant. Google Agenda et Outlook comparent
   ces deux valeurs pour décider si un événement déjà importé doit être
   remplacé. Un UID qui change crée un doublon ; un SEQUENCE qui stagne fait
   ignorer purement et simplement la mise à jour. L'abonnement semblerait
   fonctionner tout en ne transmettant jamais la seule information qui
   compte — l'annulation.
2. Une séance annulée est **réécrite**, jamais retirée (INV-15). Le réflexe
   serait un `EXDATE`, qui la ferait proprement disparaître de l'agenda :
   c'est exactement ce qu'il ne faut pas, car l'étudiant se déplacerait
   quand même, sans rien avoir remarqué. On émet à la place une occurrence
   de remplacement (`RECURRENCE-ID`) intitulée « ANNULÉ ».
3. Une alarme (`VALARM`) sur les séances annulées et modifiées. C'est elle
   qui transforme l'agenda d'un affichage passif en une alerte : le
   téléphone sonne à l'heure où l'étudiant serait parti.

Reste une limite que le code ne peut pas contourner et qu'il ne faut pas
masquer : la fréquence de relecture appartient au fournisseur d'agenda.
`REFRESH-INTERVAL` est respecté par Apple et Outlook, largement ignoré par
Google, qui relit selon son propre rythme (plusieurs heures). D'où
FR-NOTIF-05, et d'où l'alerte Web Push comme canal immédiat.
"""

import datetime

from core.time_utils import minutes_to_hhmm  # noqa: F401  (lisibilité des logs de debug)
from planning.models import Creneau
from public.services import JOURS_INDEX, get_groupe_public

PRODID = "-//UJKZ//Campus Manager//FR"
TZID = "Africa/Ouagadougou"

# Le Burkina Faso est à UTC+0 toute l'année, sans heure d'été. La VTIMEZONE
# est tout de même déclarée plutôt que d'émettre des heures flottantes : une
# heure flottante se déplace avec le fuseau du terminal, et un étudiant dont
# le téléphone est resté sur un autre fuseau verrait tout son emploi du temps
# décalé sans comprendre pourquoi.
VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    f"TZID:{TZID}",
    "BEGIN:STANDARD",
    "DTSTART:19700101T000000",
    "TZOFFSETFROM:+0000",
    "TZOFFSETTO:+0000",
    "TZNAME:GMT",
    "END:STANDARD",
    "END:VTIMEZONE",
]

DUREE_FANTOME = datetime.timedelta(days=7)


def _echapper(texte: str | None) -> str:
    """RFC 5545 §3.3.11 : la virgule et le point-virgule sont des séparateurs
    de valeurs, un motif d'annulation qui en contient couperait l'événement
    en deux sans le moindre message d'erreur."""
    if not texte:
        return ""
    return (
        texte.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _plier(ligne: str) -> list[str]:
    """RFC 5545 §3.1 : 75 OCTETS par ligne, pas 75 caractères — un « é » en
    compte deux, et couper au milieu d'un caractère multi-octets produit un
    fichier que certains agendas refusent en bloc."""
    octets = ligne.encode("utf-8")
    if len(octets) <= 75:
        return [ligne]

    morceaux, courant = [], b""
    for caractere in ligne:
        encode = caractere.encode("utf-8")
        limite = 75 if not morceaux else 74  # les lignes suivantes portent une espace
        if len(courant) + len(encode) > limite:
            morceaux.append(courant.decode("utf-8"))
            courant = b""
        courant += encode
    if courant:
        morceaux.append(courant.decode("utf-8"))
    return [morceaux[0]] + [" " + m for m in morceaux[1:]]


def _horodatage(date: datetime.date, minutes: int) -> str:
    heure, minute = divmod(minutes, 60)
    return f"{date.strftime('%Y%m%d')}T{heure:02d}{minute:02d}00"


def _premiere_occurrence(jour: str, debut_periode: datetime.date) -> datetime.date:
    """Première date, à partir du début de la période, tombant le bon jour."""
    ecart = (JOURS_INDEX[jour] - debut_periode.weekday()) % 7
    return debut_periode + datetime.timedelta(days=ecart)


def _alarme(description: str) -> list[str]:
    return [
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        # Deux heures avant : assez tôt pour qu'un étudiant qui allait
        # partir ne parte pas, assez tard pour qu'il n'ait pas oublié.
        "TRIGGER:-PT2H",
        f"DESCRIPTION:{_echapper(description)}",
        "END:VALARM",
    ]


def _evenement_normal(creneau: Creneau, debut: datetime.date, fin: datetime.date) -> list[str]:
    premiere = _premiere_occurrence(creneau.jour, debut)
    if premiere > fin:
        return []

    annule_partout = creneau.statut == "annule"
    modifie = creneau.statut == "modifie"

    if annule_partout:
        titre = f"ANNULÉ — {creneau.ue.intitule}"
    elif modifie:
        titre = f"MODIFIÉ — {creneau.ue.intitule}"
    else:
        titre = creneau.ue.intitule

    description = [f"Enseignant : {creneau.enseignant.prenom} {creneau.enseignant.nom}".strip()]
    if creneau.motif:
        description.append(f"Motif : {creneau.motif}")
    description.append(f"Groupe : {creneau.groupe.nom}")

    lignes = [
        "BEGIN:VEVENT",
        f"UID:{creneau.id}@campus-manager.ujkz",
        f"SEQUENCE:{creneau.version}",
        f"DTSTAMP:{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID={TZID}:{_horodatage(premiere, creneau.heure_debut_minutes)}",
        f"DTEND;TZID={TZID}:{_horodatage(premiere, creneau.heure_fin_minutes)}",
        f"RRULE:FREQ=WEEKLY;UNTIL={_horodatage(fin, 23 * 60 + 59)}",
        f"SUMMARY:{_echapper(titre)}",
        f"LOCATION:{_echapper(f'{creneau.salle.nom} — {creneau.salle.batiment}')}",
        f"DESCRIPTION:{_echapper(chr(10).join(description))}",
        f"STATUS:{'CANCELLED' if annule_partout else 'CONFIRMED'}",
    ]
    if annule_partout or modifie:
        lignes += _alarme(titre)
    lignes.append("END:VEVENT")
    return lignes


def _occurrences_annulees(creneau: Creneau, debut: datetime.date, fin: datetime.date) -> list[str]:
    """Une occurrence de remplacement par séance annulée (FR-PUB-07).

    `RECURRENCE-ID` désigne l'occurrence d'origine à remplacer : l'agenda
    remplace CETTE date-là et laisse les autres intactes — la traduction
    exacte, côté calendrier, de l'invariant INV-14.
    """
    lignes: list[str] = []
    for seance in creneau.seances_annulees.all():
        if not (debut <= seance.date <= fin):
            continue
        lignes += [
            "BEGIN:VEVENT",
            f"UID:{creneau.id}@campus-manager.ujkz",
            f"RECURRENCE-ID;TZID={TZID}:{_horodatage(seance.date, creneau.heure_debut_minutes)}",
            f"SEQUENCE:{creneau.version}",
            f"DTSTAMP:{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART;TZID={TZID}:{_horodatage(seance.date, creneau.heure_debut_minutes)}",
            f"DTEND;TZID={TZID}:{_horodatage(seance.date, creneau.heure_fin_minutes)}",
            f"SUMMARY:{_echapper(f'ANNULÉ — {creneau.ue.intitule}')}",
            f"LOCATION:{_echapper(f'{creneau.salle.nom} — {creneau.salle.batiment}')}",
            f"DESCRIPTION:{_echapper(f'Séance annulée. Motif : {seance.motif}')}",
            # Volontairement CONFIRMED et non CANCELLED : un événement
            # marqué CANCELLED est masqué par la plupart des agendas, ce qui
            # reviendrait à effacer l'information (INV-15). L'annulation est
            # dite dans le titre, là où l'étudiant la lira.
            "STATUS:CONFIRMED",
            "TRANSP:TRANSPARENT",
        ]
        lignes += _alarme(f"Cours annulé : {creneau.ue.intitule}")
        lignes.append("END:VEVENT")
    return lignes


def _fantome_deplacement(creneau: Creneau, aujourdhui: datetime.date) -> list[str]:
    """L'événement laissé à l'ANCIEN horaire d'un cours déplacé (FR-PUB-07).

    Sans lui, un déplacement est le changement le plus dangereux du système :
    l'événement bouge dans l'agenda, personne ne remarque rien, et l'étudiant
    se présente à l'ancienne heure devant une salle vide. Le fantôme vit une
    semaine — au-delà, l'habitude est prise et il devient du bruit.
    """
    if not creneau.deplace_le or creneau.ancien_jour is None:
        return []

    depuis = creneau.deplace_le.date()
    if aujourdhui - depuis > DUREE_FANTOME:
        return []

    ecart = (JOURS_INDEX[creneau.ancien_jour] - depuis.weekday()) % 7
    date_fantome = depuis + datetime.timedelta(days=ecart)
    if date_fantome - depuis > DUREE_FANTOME:
        return []

    nouveau = f"{creneau.jour} {minutes_to_hhmm(creneau.heure_debut_minutes)}"
    return [
        "BEGIN:VEVENT",
        # UID distinct : c'est un autre événement, pas une révision de
        # celui qui a bougé — les confondre ferait s'annuler l'un l'autre.
        f"UID:{creneau.id}-deplace@campus-manager.ujkz",
        f"SEQUENCE:{creneau.version}",
        f"DTSTAMP:{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        f"DTSTART;TZID={TZID}:{_horodatage(date_fantome, creneau.ancien_heure_debut_minutes)}",
        f"DTEND;TZID={TZID}:{_horodatage(date_fantome, creneau.ancien_heure_fin_minutes)}",
        f"SUMMARY:{_echapper(f'DÉPLACÉ — {creneau.ue.intitule}')}",
        f"LOCATION:{_echapper(f'{creneau.salle.nom} — {creneau.salle.batiment}')}",
        f"DESCRIPTION:{_echapper(f'Ce cours a été déplacé au {nouveau}, salle {creneau.salle.nom}.')}",
        "STATUS:CONFIRMED",
        "TRANSP:TRANSPARENT",
    ] + _alarme(f"Cours déplacé : {creneau.ue.intitule}") + ["END:VEVENT"]


def calendrier_du_groupe(groupe_id: str) -> str:
    groupe = get_groupe_public(groupe_id)
    ufr = groupe.ufr

    # Sans période académique déclarée (FR-REF-16), on ne peut pas borner la
    # récurrence : un cours se répéterait indéfiniment dans l'agenda du
    # visiteur, pour toujours. On prend alors une fenêtre glissante d'un an,
    # ce qui est faux mais fini — et le Gestionnaire est invité à renseigner
    # sa période dans l'interface.
    aujourdhui = datetime.date.today()
    debut = ufr.periode_debut or aujourdhui - datetime.timedelta(days=30)
    fin = ufr.periode_fin or aujourdhui + datetime.timedelta(days=365)

    creneaux = (
        Creneau.objects.filter(groupe_id=groupe_id)
        .select_related("ue", "enseignant", "salle", "groupe")
        .prefetch_related("seances_annulees")
    )

    lignes = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        # Le nom que le visiteur verra dans son agenda pour le restant de
        # l'année : le sigle officiel, pas le code technique en minuscules.
        f"X-WR-CALNAME:{_echapper(f'{groupe.nom} — {ufr.sigle_affiche}')}",
        f"X-WR-TIMEZONE:{TZID}",
        # Respectés par Apple Calendrier et Outlook ; Google applique son
        # propre rythme quoi qu'on écrive ici (cf. en-tête de module).
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
        *VTIMEZONE,
    ]

    for creneau in creneaux:
        lignes += _evenement_normal(creneau, debut, fin)
        lignes += _occurrences_annulees(creneau, debut, fin)
        lignes += _fantome_deplacement(creneau, aujourdhui)

    lignes.append("END:VCALENDAR")

    pliees: list[str] = []
    for ligne in lignes:
        pliees.extend(_plier(ligne))
    # CRLF, imposé par la RFC — certains agendas rejettent un fichier en LF.
    return "\r\n".join(pliees) + "\r\n"
