"""[V3] Le flux iCalendar (FR-PUB-05/06/07, INV-13/15).

Ce sont les tests d'un mécanisme qu'on ne peut pas observer en local : une
fois l'URL donnée au visiteur, c'est Google ou Apple qui la relit, et un
détail de format faux ne produit aucune erreur visible — l'abonnement a
simplement l'air de fonctionner sans jamais transmettre les changements.
D'où le niveau de détail assumé ci-dessous.
"""

import datetime

from django.test import Client, TestCase

from planning.models import Creneau
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
            # Une date à venir : le fantôme d'un cours déplacé n'a de sens
            # que tant que quelqu'un peut encore se présenter à l'ancienne
            # case, il disparaît une fois la date passée.
            date=prochain("lundi"), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60,
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

    def test_chaque_seance_est_un_evenement_date_autonome(self):
        """[V4] Ni RRULE, ni RECURRENCE-ID : le programme est publié semaine
        par semaine, chaque séance vaut pour sa date et pour elle seule.

        C'est ce qui a réglé le défaut le plus visible de la V3 — un cours
        répété à l'identique pendant les vacances, parce que le modèle
        supposait un emploi du temps arrêté pour tout le semestre."""
        ics = self._ics()
        self.assertNotIn("RRULE", ics)
        self.assertNotIn("RECURRENCE-ID", ics)
        self.assertIn(f"DTSTART;TZID={{}}:{self.creneau.date.strftime('%Y%m%d')}T080000".format("Africa/Ouagadougou"), ics)

    def test_une_semaine_non_publiee_ne_produit_aucun_evenement(self):
        """Une semaine sans programme est une semaine sans cours — pas une
        grille vide à expliquer, pas un trou à combler."""
        ics = self._ics()
        semaine_suivante = (self.creneau.date + datetime.timedelta(days=7)).strftime("%Y%m%d")
        self.assertNotIn(semaine_suivante, ics)

    def test_une_seance_annulee_reste_dans_le_flux(self):
        """INV-15 : la retirer serait le plus sûr moyen que l'étudiant se
        déplace quand même."""
        Creneau.objects.filter(id=self.creneau.id).update(statut="annule", motif="Absence enseignant")
        ics = self._ics()
        self.assertIn("SUMMARY:ANNULÉ — Bases de Données", ics)
        self.assertIn("Absence enseignant", ics)
        # Jamais CANCELLED : la plupart des agendas masquent un événement
        # annulé, ce qui reviendrait à effacer l'information.
        self.assertIn("STATUS:CONFIRMED", ics)
        self.assertIn("TRANSP:TRANSPARENT", ics)

    def test_une_seance_annulee_porte_une_alarme(self):
        """C'est elle qui fait sonner le téléphone — sans quoi l'agenda reste
        un affichage passif que l'étudiant doit penser à consulter."""
        Creneau.objects.filter(id=self.creneau.id).update(statut="annule", motif="Absence")
        evenement = evenements(self._ics())[0]
        self.assertIn("BEGIN:VALARM", evenement)
        self.assertIn("TRIGGER:-PT2H", evenement)

    def test_un_cours_deplace_laisse_un_fantome_a_l_ancienne_case(self):
        """FR-PUB-07 : un déplacement est le changement le plus dangereux —
        l'événement bouge dans l'agenda et personne ne remarque rien."""
        from django.utils import timezone

        ancienne = self.creneau.date
        Creneau.objects.filter(id=self.creneau.id).update(
            date=ancienne + datetime.timedelta(days=2),
            ancienne_date=ancienne,
            ancien_heure_debut_minutes=8 * 60,
            ancien_heure_fin_minutes=10 * 60,
            deplace_le=timezone.now(),
        )
        ics = self._ics()
        self.assertIn(f"UID:{self.creneau.id}-deplace@campus-manager.ujkz", ics)
        self.assertIn("SUMMARY:DÉPLACÉ — Bases de Données", ics)

    def test_le_fantome_disparait_une_fois_l_ancienne_date_passee(self):
        """Au-delà, il n'avertit plus personne et devient du bruit."""
        from django.utils import timezone

        Creneau.objects.filter(id=self.creneau.id).update(
            ancienne_date=datetime.date.today() - datetime.timedelta(days=3),
            ancien_heure_debut_minutes=8 * 60,
            ancien_heure_fin_minutes=10 * 60,
            deplace_le=timezone.now(),
        )
        self.assertNotIn("-deplace@campus-manager.ujkz", self._ics())

    def test_les_separateurs_sont_echappes_dans_les_motifs(self):
        """RFC 5545 §3.3.11 : une virgule non échappée couperait l'événement
        en deux, sans le moindre message d'erreur."""
        Creneau.objects.filter(id=self.creneau.id).update(
            statut="annule", motif="Absence, maladie; certificat fourni"
        )
        ics = self._ics().replace("\r\n ", "")  # dépliage des lignes
        self.assertIn("Absence" + chr(92) + ", maladie" + chr(92) + "; certificat fourni", ics)
