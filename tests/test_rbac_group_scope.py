from django.test import Client, TestCase

from accounts.models import Role
from planning.models import Creneau
from tests.base import creer_compte, creer_enseignant, creer_etudiant, creer_groupe, creer_salle, creer_ue, login


class RbacGroupScopeTests(TestCase):
    """INT-06 : un étudiant ne voit jamais que son propre groupe, un
    enseignant que son propre planning — même en le demandant explicitement."""

    def setUp(self):
        self.ue = creer_ue("Algorithmique Avancée")
        self.salle = creer_salle("Amphi A", 1000)
        self.groupe_a = creer_groupe("Groupe A")
        self.groupe_b = creer_groupe("Groupe B")
        self.ens_a = creer_enseignant("Kaboré", "Ismaël")
        self.ens_b = creer_enseignant("Traoré", "Moussa")

        etudiant_a = creer_etudiant("20230145", "Ouédraogo", "Aïcha", groupe=self.groupe_a)
        creer_compte("etu.a", "Ouédraogo", "Aïcha", Role.ETUDIANT, etudiant=etudiant_a)
        creer_compte("ens.a", "Kaboré", "Ismaël", Role.ENSEIGNANT, enseignant=self.ens_a)
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)

        Creneau.objects.create(ue=self.ue, enseignant=self.ens_a, groupe=self.groupe_a, salle=self.salle, jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)
        Creneau.objects.create(ue=self.ue, enseignant=self.ens_b, groupe=self.groupe_b, salle=self.salle, jour="mardi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)

        self.client_etu = Client()
        login(self.client_etu, "etu.a")
        self.client_ens = Client()
        login(self.client_ens, "ens.a")
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")

    def test_etudiant_ne_voit_que_son_groupe(self):
        res = self.client_etu.get("/api/creneaux")
        self.assertEqual(len(res.json()["creneaux"]), 1)
        self.assertEqual(res.json()["creneaux"][0]["groupe"]["id"], self.groupe_a.id)

    def test_etudiant_qui_demande_un_autre_groupe_reste_cantonne_au_sien(self):
        res = self.client_etu.get(f"/api/creneaux?groupeId={self.groupe_b.id}")
        self.assertEqual(len(res.json()["creneaux"]), 1)
        self.assertEqual(res.json()["creneaux"][0]["groupe"]["id"], self.groupe_a.id)

    def test_enseignant_ne_voit_que_son_propre_planning(self):
        res = self.client_ens.get(f"/api/creneaux?enseignantId={self.ens_b.id}")
        self.assertEqual(len(res.json()["creneaux"]), 1)
        self.assertEqual(res.json()["creneaux"][0]["enseignant"]["id"], self.ens_a.id)

    def test_scolarite_voit_toute_son_ufr_par_defaut(self):
        res = self.client_sco.get("/api/creneaux")
        self.assertEqual(len(res.json()["creneaux"]), 2)

    def test_scolarite_peut_filtrer_par_groupe(self):
        res = self.client_sco.get(f"/api/creneaux?groupeId={self.groupe_b.id}")
        self.assertEqual(len(res.json()["creneaux"]), 1)

    def test_etudiant_ne_peut_pas_creer_de_creneau(self):
        res = self.client_etu.post("/api/creneaux", data="{\"creneaux\": []}", content_type="application/json")
        self.assertEqual(res.status_code, 403)
