from django.test import Client, TestCase

from accounts.models import Role, Utilisateur
from tests.base import creer_compte, login, post_json


class AccountsProvisioningTests(TestCase):
    def setUp(self):
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        creer_compte("20230145", "Ouédraogo", "Aïcha", Role.ETUDIANT)
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")
        self.client_etu = Client()
        login(self.client_etu, "20230145")

    def test_role_autre_que_scolarite_ne_peut_pas_creer_un_enseignant(self):
        res = post_json(self.client_etu, "/api/enseignants", {"nom": "Kaboré", "prenom": "Ismaël", "identifiant": "kabore.enseignant"})
        self.assertEqual(res.status_code, 403)

    def test_cree_enseignant_et_utilisateur_puis_activation_fonctionne(self):
        res = post_json(self.client_sco, "/api/enseignants", {"nom": "Kaboré", "prenom": "Ismaël", "identifiant": "kabore.enseignant"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["identifiant"], "kabore.enseignant")

        compte = Utilisateur.objects.get(identifiant="kabore.enseignant")
        self.assertIsNone(compte.mot_de_passe_hash)
        self.assertIsNotNone(compte.enseignant_id)
        self.assertEqual(compte.role, Role.ENSEIGNANT)

        res_activate = post_json(self.client_sco, "/api/auth/activate", {"identifiant": "kabore.enseignant", "nouveauMotDePasse": "x", "confirmationMotDePasse": "x"})
        self.assertEqual(res_activate.status_code, 200)

    def test_identifiant_deja_utilise_409(self):
        res = post_json(self.client_sco, "/api/enseignants", {"nom": "Doublon", "prenom": "Test", "identifiant": "20230145"})
        self.assertEqual(res.status_code, 409)

    def test_liste_lisible_par_tous_les_roles_authentifies(self):
        self.assertEqual(self.client_etu.get("/api/enseignants").status_code, 200)
        self.assertEqual(self.client_sco.get("/api/enseignants").status_code, 200)
