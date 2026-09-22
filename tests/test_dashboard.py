"""FR-DASH-01 — le tableau de bord gestionnaire.

Aucun test ne le couvrait jusqu'ici, et c'est ce qui a laissé passer deux
défauts introduits par la V4 (créneau daté au lieu d'un gabarit
hebdomadaire) : le calcul des conflits résolus construisait encore un
candidat avec `jour=` — champ disparu —, ce qui faisait planter toute la
route dès qu'un conflit avait été journalisé ; et le taux d'occupation
additionnait toutes les semaines saisies pour les diviser par la capacité
d'une seule. Le front masquant l'échec par des zéros, rien ne se voyait.
"""

import datetime

from django.test import Client, TestCase

from accounts.models import Role
from planning.models import ConflitJournal, Creneau
from tests.base import (
    creer_compte,
    creer_enseignant,
    creer_groupe,
    creer_salle,
    creer_ue,
    jour,
    login,
    ufr_par_defaut,
)


class TableauDeBordTests(TestCase):
    def setUp(self):
        ufr_par_defaut()
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")

        self.salle = creer_salle("Amphi A", 100)
        self.groupe = creer_groupe("L3 INFO - Groupe A", effectif=40)
        self.ue = creer_ue("Réseaux")
        self.enseignant = creer_enseignant("Kaboré", "Ismaël")

    def _creneau(self, date: datetime.date, debut_h: int, fin_h: int, derogation: str | None = None) -> Creneau:
        return Creneau.objects.create(
            ue=self.ue, enseignant=self.enseignant, groupe=self.groupe, salle=self.salle,
            date=date, heure_debut_minutes=debut_h * 60, heure_fin_minutes=fin_h * 60,
            derogation_motif=derogation,
        )

    def test_la_route_repond_meme_quand_un_conflit_a_ete_journalise(self):
        """Le cas qui plantait : une dérogation laisse une trace dans
        ConflitJournal, et le calcul des conflits résolus relit cette trace."""
        # Seule une dérogation permet à deux séances d'occuper la même salle
        # au même moment : la contrainte EXCLUDE (INV-02) ne s'efface que
        # pour un créneau qui porte un motif de dérogation.
        a = self._creneau(jour("lundi"), 8, 10)
        b = self._creneau(jour("lundi"), 8, 10, derogation="Amphi réservé en urgence")
        ConflitJournal.objects.create(
            type="salle", gravite="bloquant", titre="Double réservation", description="—",
            creneau_a=a, creneau_b=b, derogation_motif="Test", detecte_par="Savadogo Rasmata",
        )

        reponse = self.client_sco.get("/api/dashboard/stats")

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.json()["conflitsDetectes"], 1)
        self.assertEqual(reponse.json()["conflitsResolus"], 0)  # les deux séances sont toujours là

    def test_un_conflit_qui_n_existe_plus_compte_comme_resolu(self):
        """Même salle, même heure, mais pas le même lundi : depuis la V4, ce
        n'est plus un conflit (RM-01 révisée)."""
        a = self._creneau(jour("lundi"), 8, 10)
        b = self._creneau(jour("lundi") + datetime.timedelta(days=7), 8, 10)
        ConflitJournal.objects.create(
            type="salle", gravite="bloquant", titre="Double réservation", description="—",
            creneau_a=a, creneau_b=b, detecte_par="Savadogo Rasmata",
        )
        self.assertEqual(self.client_sco.get("/api/dashboard/stats").json()["conflitsResolus"], 1)

    def test_le_taux_d_occupation_ne_porte_que_sur_la_semaine_en_cours(self):
        """Le dénominateur est la capacité d'UNE semaine : le numérateur doit
        donc être les séances de cette même semaine. Additionner toutes les
        semaines publiées faisait croître le taux à chaque publication,
        jusqu'à 100 %."""
        self._creneau(jour("lundi"), 8, 10)  # cette semaine : 2 h
        for semaines in range(1, 30):  # 29 semaines passées, 2 h chacune
            self._creneau(jour("lundi") - datetime.timedelta(weeks=semaines), 8, 10)

        # 1 salle, 6 jours x (11 h d'ouverture - 1 h 30 de pauses) = 57 h ; 2 h / 57 h ≈ 4 %.
        self.assertEqual(self.client_sco.get("/api/dashboard/stats").json()["tauxOccupationSalles"], 4)
