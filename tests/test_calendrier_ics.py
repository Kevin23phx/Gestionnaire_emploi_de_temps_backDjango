"""[V3] Le flux iCalendar (FR-PUB-05/06/07, INV-13/15).

Ce sont les tests d'un mécanisme qu'on ne peut pas observer en local : une
fois l'URL donnée au visiteur, c'est Google ou Apple qui la relit, et un
détail de format faux ne produit aucune erreur visible — l'abonnement a
simplement l'air de fonctionner sans jamais transmettre les changements.
D'où le niveau de détail assumé ci-dessous.
"""

import datetime

from django.test import Client, TestCase

from planning.models import Creneau, SeanceAnnulee
from tests.base import (
    creer_enseignant,
    creer_groupe,
    creer_salle,
    creer_ue,
    prochain,
)


def evenements(ics: str) -> list[str]:
    return ics.split("BEGIN:VEVENT")[1:]


class CalendrierIcsTests(TestCase):
    def setUp(self):
        self.ue = creer_ue("Bases de Données", code="INFO302")
        self.salle = creer_salle("Salle 402")
        self.groupe = creer_groupe("L3 INFO - Groupe A")
        self.enseignant = creer_enseignant("Traoré", "Moussa")
        self.creneau = Creneau.objects.create(
            ue=self.ue, enseignant=self.enseignant, groupe=self.groupe, salle=self.salle,
            jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60,
        )
        self.anonyme = Client()

    def _ics(self) -> str:
        res = self.anonyme.get(f"/api/public/calendrier/{self.groupe.id}.ics")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/calendar", res["Content-Type"])
        return res.content.decode("utf-8")

    def test_le_flux_est_lisible_sans_authentification(self):
        ics = self._ics()
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR"))
        self.assertTrue(ics.rstrip().endswith("END:VCALENDAR"))

    def test_lignes_terminees_en_crlf_et_pliees_a_75_octets(self):
        """RFC 5545 §3.1 : certains agendas rejettent en bloc un fichier en
        LF simple ou une ligne trop longue."""
        ics = self._ics()
        self.assertIn("\r\n", ics)
        for ligne in ics.split("\r\n"):
            self.assertLessEqual(len(ligne.encode("utf-8")), 75, ligne)

    def test_uid_stable_et_sequence_qui_monte_a_chaque_ecriture(self):
        """INV-13/FR-PUB-06 : sans SEQUENCE croissant, Google et Outlook
        ignorent la mise à jour — l'abonné ne verrait jamais l'annulation."""
        self.assertIn(f"UID:{self.creneau.id}@campus-manager.ujkz", self._ics())
        self.assertIn("SEQUENCE:1", self._ics())

        Creneau.objects.filter(id=self.creneau.id).update(version=2)
        self.assertIn("SEQUENCE:2", self._ics())

    def test_l_uid_ne_change_jamais_quand_le_programme_change(self):
        """INV-13 : un visiteur abonné une fois ne doit jamais avoir à se
        réabonner. Un UID qui bougerait créerait un doublon dans son agenda
        au lieu de mettre à jour l'événement."""
        avant = self._ics()
        Creneau.objects.filter(id=self.creneau.id).update(salle=self.salle, heure_fin_minutes=11 * 60, version=3)
        apres = self._ics()
        self.assertIn(f"UID:{self.creneau.id}@campus-manager.ujkz", avant)
        self.assertIn(f"UID:{self.creneau.id}@campus-manager.ujkz", apres)

    def test_la_recurrence_s_arrete_a_la_fin_de_la_periode_academique(self):
        """FR-REF-16 : sans borne, le cours se répéterait indéfiniment dans
        l'agenda du visiteur, pour toujours."""
        ics = self._ics()
        fin = (datetime.date.today() + datetime.timedelta(days=120)).strftime("%Y%m%d")
        self.assertIn(f"RRULE:FREQ=WEEKLY;UNTIL={fin}T235900", ics)

    def test_une_seance_annulee_est_reecrite_et_non_retiree(self):
        """INV-15 / FR-PUB-07 : le réflexe serait un EXDATE, qui la ferait
        disparaître proprement de l'agenda — et l'étudiant se déplacerait
        quand même, sans avoir rien remarqué."""
        date = prochain("lundi")
        SeanceAnnulee.objects.create(creneau=self.creneau, date=date, motif="Absence", annule_par="Test")
        ics = self._ics()

        self.assertNotIn("EXDATE", ics)
        self.assertIn("RECURRENCE-ID", ics)
        self.assertIn("SUMMARY:ANNULÉ — Bases de Données", ics)
        self.assertIn("Absence", ics)
        # Jamais CANCELLED sur l'occurrence : la plupart des agendas
        # masquent un événement annulé, ce qui reviendrait à l'effacer.
        occurrence = [e for e in evenements(ics) if "RECURRENCE-ID" in e][0]
        self.assertIn("STATUS:CONFIRMED", occurrence)

    def test_une_seance_annulee_porte_une_alarme(self):
        """C'est elle qui fait sonner le téléphone — sans quoi l'agenda reste
        un affichage passif que l'étudiant doit penser à consulter."""
        date = prochain("lundi")
        SeanceAnnulee.objects.create(creneau=self.creneau, date=date, motif="Absence", annule_par="Test")
        occurrence = [e for e in evenements(self._ics()) if "RECURRENCE-ID" in e][0]
        self.assertIn("BEGIN:VALARM", occurrence)
        self.assertIn("TRIGGER:-PT2H", occurrence)

    def test_un_cours_deplace_laisse_un_fantome_a_l_ancien_horaire(self):
        """FR-PUB-07 : un déplacement est le changement le plus dangereux —
        l'événement bouge et personne ne remarque rien."""
        from django.utils import timezone

        Creneau.objects.filter(id=self.creneau.id).update(
            jour="jeudi", ancien_jour="lundi",
            ancien_heure_debut_minutes=8 * 60, ancien_heure_fin_minutes=10 * 60,
            deplace_le=timezone.now(),
        )
        ics = self._ics()
        self.assertIn(f"UID:{self.creneau.id}-deplace@campus-manager.ujkz", ics)
        self.assertIn("SUMMARY:DÉPLACÉ — Bases de Données", ics)
        self.assertIn("jeudi", ics)

    def test_le_fantome_disparait_au_bout_d_une_semaine(self):
        """Au-delà, l'habitude est prise et le fantôme devient du bruit."""
        from django.utils import timezone

        Creneau.objects.filter(id=self.creneau.id).update(
            jour="jeudi", ancien_jour="lundi",
            ancien_heure_debut_minutes=8 * 60, ancien_heure_fin_minutes=10 * 60,
            deplace_le=timezone.now() - datetime.timedelta(days=10),
        )
        self.assertNotIn("-deplace@campus-manager.ujkz", self._ics())

    def test_les_separateurs_sont_echappes_dans_les_motifs(self):
        """RFC 5545 §3.3.11 : une virgule non échappée couperait l'événement
        en deux, sans le moindre message d'erreur."""
        date = prochain("lundi")
        SeanceAnnulee.objects.create(
            creneau=self.creneau, date=date, motif="Absence, maladie; certificat fourni", annule_par="Test"
        )
        ics = self._ics().replace("\r\n ", "")  # dépliage des lignes
        self.assertIn(r"Absence\, maladie\; certificat fourni", ics)
