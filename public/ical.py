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
2. Une séance annulée est **conservée**, jamais retirée (INV-15). Le réflexe
   serait de ne plus l'émettre du tout, ce qui la ferait proprement
   disparaître de l'agenda : c'est exactement ce qu'il ne faut pas, car
   l'étudiant se déplacerait quand même, sans rien avoir remarqué. Elle
   reste donc présente, intitulée « ANNULÉ ».

[V4] Plus aucune récurrence. Le programme de l'UJKZ est publié semaine par
semaine et change d'une semaine à l'autre : chaque séance est un événement
daté, autonome. La `RRULE` a disparu — avec elle, les cours répétés pendant
les vacances et les bornes de semestre impossibles à tenir à jour. Un
abonné reçoit simplement les nouveaux événements à mesure que les semaines
sont publiées, sans jamais avoir à se réabonner (l'adresse ne change pas).
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
from public.services import get_groupe_public

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


def _maintenant() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _horodatage(date: datetime.date, minutes: int) -> str:
    heure, minute = divmod(minutes, 60)
    return f"{date.strftime('%Y%m%d')}T{heure:02d}{minute:02d}00"


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


def _evenement(creneau: Creneau) -> list[str]:
    """Une séance datée = un événement autonome. Ni RRULE, ni RECURRENCE-ID."""
    annule = creneau.statut == "annule"
    modifie = creneau.statut == "modifie"

    if annule:
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
        f"DTSTAMP:{_maintenant()}",
        f"DTSTART;TZID={TZID}:{_horodatage(creneau.date, creneau.heure_debut_minutes)}",
        f"DTEND;TZID={TZID}:{_horodatage(creneau.date, creneau.heure_fin_minutes)}",
        f"SUMMARY:{_echapper(titre)}",
        f"LOCATION:{_echapper(creneau.salle.nom)}",
        f"DESCRIPTION:{_echapper(chr(10).join(description))}",
        # Volontairement CONFIRMED même pour une séance annulée : un
        # événement marqué CANCELLED est masqué par la plupart des agendas,
        # ce qui reviendrait à effacer l'information (INV-15). L'annulation
        # est dite dans le titre, là où l'étudiant la lira.
        "STATUS:CONFIRMED",
    ]
    if annule:
        lignes.append("TRANSP:TRANSPARENT")
    if annule or modifie:
        lignes += _alarme(titre)
    lignes.append("END:VEVENT")
    return lignes


def _fantome_deplacement(creneau: Creneau, aujourdhui: datetime.date) -> list[str]:
    """L'événement laissé à l'ANCIENNE case d'un cours déplacé (FR-PUB-07).

    Sans lui, un déplacement est le changement le plus dangereux du système :
    l'événement bouge dans l'agenda, personne ne remarque rien, et l'étudiant
    se présente à l'ancienne heure devant une salle vide.
    """
    if not creneau.deplace_le or creneau.ancienne_date is None:
        return []
    # Passé l'ancienne date, le fantôme n'avertit plus personne.
    if creneau.ancienne_date < aujourdhui:
        return []

    nouveau = f"{creneau.jour} {creneau.date.isoformat()} à {minutes_to_hhmm(creneau.heure_debut_minutes)}"
    return [
        "BEGIN:VEVENT",
        # UID distinct : c'est un autre événement, pas une révision de celui
        # qui a bougé — les confondre les ferait s'annuler l'un l'autre.
        f"UID:{creneau.id}-deplace@campus-manager.ujkz",
        f"SEQUENCE:{creneau.version}",
        f"DTSTAMP:{_maintenant()}",
        f"DTSTART;TZID={TZID}:{_horodatage(creneau.ancienne_date, creneau.ancien_heure_debut_minutes)}",
        f"DTEND;TZID={TZID}:{_horodatage(creneau.ancienne_date, creneau.ancien_heure_fin_minutes)}",
        f"SUMMARY:{_echapper(f'DÉPLACÉ — {creneau.ue.intitule}')}",
        f"LOCATION:{_echapper(creneau.salle.nom)}",
        f"DESCRIPTION:{_echapper(f'Ce cours a été déplacé au {nouveau}, salle {creneau.salle.nom}.')}",
        "STATUS:CONFIRMED",
        "TRANSP:TRANSPARENT",
    ] + _alarme(f"Cours déplacé : {creneau.ue.intitule}") + ["END:VEVENT"]


def calendrier_du_groupe(groupe_id: str) -> str:
    groupe = get_groupe_public(groupe_id)
    ufr = groupe.ufr

    # [V4] Toutes les séances publiées, à partir d'un mois en arrière.
    # Rien à borner en avant : le programme n'existe que pour les semaines
    # réellement publiées, il ne se projette pas dans le vide. La fenêtre
    # arrière garde l'historique récent visible dans l'agenda — un étudiant
    # qui consulte le lundi doit encore voir la semaine qui s'achève — sans
    # faire grossir le flux indéfiniment au fil des mois.
    aujourdhui = datetime.date.today()
    debut = aujourdhui - datetime.timedelta(days=30)

    creneaux = (
        Creneau.objects.filter(groupe_id=groupe_id, date__gte=debut)
        .select_related("ue", "enseignant", "salle", "groupe")
        .order_by("date", "heure_debut_minutes")
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
        lignes += _evenement(creneau)
        lignes += _fantome_deplacement(creneau, aujourdhui)

    lignes.append("END:VCALENDAR")

    pliees: list[str] = []
    for ligne in lignes:
        pliees.extend(_plier(ligne))
    # CRLF, imposé par la RFC — certains agendas rejettent un fichier en LF.
    return "\r\n".join(pliees) + "\r\n"
