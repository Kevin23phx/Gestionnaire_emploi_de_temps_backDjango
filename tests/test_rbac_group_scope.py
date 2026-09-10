from django.test import Client, TestCase

from accounts.models import Role
from planning.models import Creneau
from tests.base import (
    jour,
    creer_compte,
    creer_enseignant,
    creer_groupe,
    creer_salle,
    creer_ue,
    creer_ufr,
    login,
)


class PerimetreLectureTests(TestCase):
    """[V3] INT-06 est levée : tout programme est public (FR-PUB-01), il n'y
    a plus de cloisonnement en lecture par groupe ni par enseignant — ces
    rôles n'existent plus.

    Ce qui reste, et que ces tests vérifient, c'est le cloisonnement qui n'a
    jamais concerné la consultation : INT-07, le périmètre d'un Gestionnaire
    sur la GESTION de son UFR. Lever la barrière pour le public ne devait
    rien lever ici — c'est précisément ce qu'on s'assure de n'avoir pas
    cassé en la retirant ailleurs.
    """

    def setUp(self):
        creer_ufr("ufr-b", "UFR B", "b")
        self.ue = creer_ue("Algorithmique Avancée")
        self.salle = creer_salle("Amphi A", 1000)
        self.groupe_a = creer_groupe("Groupe A")
        self.groupe_b = creer_groupe("Groupe B")
        self.groupe_autre_ufr = creer_groupe("Groupe UFR-B", ufr_id="ufr-b")
        self.ens_a = creer_enseignant("Kaboré", "Ismaël")
        self.ens_b = creer_enseignant("Traoré", "Moussa")

        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        creer_compte("scolarite.b", "Gestionnaire", "B", Role.SCOLARITE, ufr_id="ufr-b")

        Creneau.objects.create(ue=self.ue, enseignant=self.ens_a, groupe=self.groupe_a, salle=self.salle, date=jour("lundi"), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)
        Creneau.objects.create(ue=self.ue, enseignant=self.ens_b, groupe=self.groupe_b, salle=self.salle, date=jour("mardi"), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)

        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")
        self.client_sco_b = Client()
        login(self.client_sco_b, "scolarite.b")

    def test_scolarite_voit_toute_son_ufr_par_defaut(self):
        res = self.client_sco.get("/api/creneaux")
        self.assertEqual(len(res.json()["creneaux"]), 2)

    def test_scolarite_peut_filtrer_par_groupe(self):
        res = self.client_sco.get(f"/api/creneaux?groupeId={self.groupe_b.id}")
        self.assertEqual(len(res.json()["creneaux"]), 1)

    def test_gestionnaire_d_une_autre_ufr_ne_voit_rien_de_celle_ci(self):
        """INT-07, inchangée par la V3."""
        res = self.client_sco_b.get("/api/creneaux")
        self.assertEqual(res.json()["creneaux"], [])

    def test_gestionnaire_qui_demande_explicitement_un_groupe_hors_ufr_n_obtient_rien(self):
        res = self.client_sco_b.get(f"/api/creneaux?groupeId={self.groupe_a.id}")
        self.assertEqual(res.json()["creneaux"], [])

    def test_recherche_serveur_sur_les_creneaux(self):
        """FR-FILT-01/06 : le filtrage se fait côté serveur, jamais en
        renvoyant tous les créneaux au navigateur."""
        res = self.client_sco.get("/api/creneaux?recherche=algorithmique")
        self.assertEqual(len(res.json()["creneaux"]), 2)
        res_vide = self.client_sco.get("/api/creneaux?recherche=zzz")
        self.assertEqual(res_vide.json()["creneaux"], [])

    def test_recherche_insensible_aux_accents(self):
        """FR-FILT-02 : « kabore », tapé sans accent, doit trouver « Kaboré ».

        Le test interroge délibérément SANS accent : avec l'accent il
        passerait avec un simple `icontains` et ne prouverait rien.
        """
        res = self.client_sco.get("/api/creneaux?recherche=kabore")
        self.assertEqual(len(res.json()["creneaux"]), 1)
        res_ue = self.client_sco.get("/api/creneaux?recherche=avancee")
        self.assertEqual(len(res_ue.json()["creneaux"]), 2)

    def test_aucune_ecriture_de_creneau_sans_authentification(self):
        """INV-05 élargi : ce n'est plus « un Étudiant » qu'on empêche
        d'écrire, c'est n'importe quel appelant anonyme."""
        res = Client().post("/api/creneaux", data='{"creneaux": []}', content_type="application/json")
        self.assertEqual(res.status_code, 401)
