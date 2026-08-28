from django.test import Client, TestCase

from accounts.models import Role, Utilisateur
from referentiel.models import Etudiant
from tests.base import creer_compte, creer_etudiant, creer_groupe, login, post_json


class ReferentielEtudiantsTests(TestCase):
    def setUp(self):
        self.groupe_a = creer_groupe("Groupe A")
        self.groupe_b = creer_groupe("Groupe B")
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")

    def test_importe_un_lot_valide_rattache_a_un_groupe(self):
        res = post_json(
            self.client_sco,
            "/api/etudiants",
            {
                "groupeId": self.groupe_a.id,
                "etudiants": [
                    {"ine": "20230101", "nom": "Zongo", "prenom": "Issa", "anneeAcademique": "2023-2024"},
                    {"ine": "20230102", "nom": "Compaoré", "prenom": "Fatoumata", "anneeAcademique": "2023-2024"},
                ],
            },
        )
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(len(data["etudiants"]), 2)
        self.assertEqual(data["doublons"], [])
        self.assertEqual(data["invalides"], [])
        self.assertTrue(all(e["groupeId"] == self.groupe_a.id for e in data["etudiants"]))

    def test_import_cree_un_compte_de_connexion_non_active(self):
        res = post_json(self.client_sco, "/api/etudiants", {"etudiants": [{"ine": "20991234", "nom": "Nouveau", "prenom": "Étudiant", "anneeAcademique": "2025-2026"}]})
        etudiant_id = res.json()["etudiants"][0]["id"]
        compte = Utilisateur.objects.get(identifiant="20991234")
        self.assertIsNone(compte.mot_de_passe_hash)
        self.assertEqual(compte.role, Role.ETUDIANT)
        self.assertEqual(compte.etudiant_id, etudiant_id)

    def test_ligne_invalide_sans_annee_academique_rejetee_sans_bloquer_le_lot(self):
        res = post_json(
            self.client_sco,
            "/api/etudiants",
            {
                "etudiants": [
                    {"ine": "20230103", "nom": "Manque", "prenom": "Année"},
                    {"ine": "20230104", "nom": "Ouattara", "prenom": "Boureima", "anneeAcademique": "2023-2024"},
                ]
            },
        )
        data = res.json()
        self.assertEqual(len(data["etudiants"]), 1)
        self.assertEqual(data["etudiants"][0]["ine"], "20230104")
        self.assertIn("20230103", data["invalides"])

    def test_doublon_ine_deja_present_ne_cree_pas_de_second_etudiant(self):
        creer_etudiant("99999999", "Existant", "DejaLa")
        res = post_json(self.client_sco, "/api/etudiants", {"etudiants": [{"ine": "99999999", "nom": "Tentative", "prenom": "Doublon", "anneeAcademique": "2025-2026"}]})
        data = res.json()
        self.assertEqual(data["etudiants"], [])
        self.assertEqual(data["doublons"], ["99999999"])
        self.assertEqual(Etudiant.objects.filter(ine="99999999").count(), 1)

    def test_affecter_deplace_vers_un_groupe_et_synchronise_le_niveau(self):
        """FR-REF-15 : la promotion synchronise niveau/filiere sur le groupe
        de destination."""
        etu = creer_etudiant("88888888", "Mobile", "Étudiant", groupe=self.groupe_a, niveau="L2", filiere="Ancienne")
        self.groupe_b.niveau = "L3"
        self.groupe_b.filiere = "Nouvelle"
        self.groupe_b.save()

        res = post_json(self.client_sco, "/api/etudiants/affecter", {"etudiantIds": [etu.id], "groupeId": self.groupe_b.id})
        self.assertEqual(res.status_code, 201)

        etu.refresh_from_db()
        self.assertEqual(etu.groupe_id, self.groupe_b.id)
        self.assertEqual(etu.niveau, "L3")
        self.assertEqual(etu.filiere, "Nouvelle")

    def test_affecter_avec_groupe_id_null_retire_du_groupe(self):
        etu = creer_etudiant("66666666", "Retiré", "Étudiant", groupe=self.groupe_a)
        res = post_json(self.client_sco, "/api/etudiants/affecter", {"etudiantIds": [etu.id], "groupeId": None})
        self.assertEqual(res.status_code, 201)
        etu.refresh_from_db()
        self.assertIsNone(etu.groupe_id)

    def test_affecter_vers_groupe_inexistant_404(self):
        etu = creer_etudiant("55555555", "Test", "404")
        res = post_json(self.client_sco, "/api/etudiants/affecter", {"etudiantIds": [etu.id], "groupeId": "inexistant"})
        self.assertEqual(res.status_code, 404)

    def test_filtre_par_annee_academique_et_filiere(self):
        creer_etudiant("F-0001", "Un", "Deux", annee_academique="2020-2021", filiere="Mathématiques")
        creer_etudiant("F-0002", "Trois", "Quatre", annee_academique="2021-2022", filiere="Physique")

        res = self.client_sco.get("/api/etudiants?anneeAcademique=2020-2021")
        self.assertEqual([e["ine"] for e in res.json()["etudiants"]], ["F-0001"])

        res2 = self.client_sco.get("/api/etudiants?filiere=physique")  # insensible à la casse
        self.assertEqual([e["ine"] for e in res2.json()["etudiants"]], ["F-0002"])
