from django.test import Client, TestCase

from accounts.models import Role
from tests.base import creer_compte, creer_etudiant, login, post_json


class AuthTests(TestCase):
    def setUp(self):
        self.etudiant = creer_etudiant("20230145", "Ouédraogo", "Aïcha")
        self.compte = creer_compte("20230145", "Ouédraogo", "Aïcha", Role.ETUDIANT, etudiant=self.etudiant)
        self.client = Client()

    def test_login_identifiant_inconnu(self):
        res = login(self.client, "inexistant", "password")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["erreur"], "Identifiant ou mot de passe incorrect.")

    def test_login_mot_de_passe_incorrect(self):
        res = login(self.client, "20230145", "mauvais")
        self.assertEqual(res.status_code, 401)

    def test_login_reussi_pose_le_cookie_et_retourne_le_role(self):
        res = login(self.client, "20230145", "password")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"role": "etudiant"})
        self.assertIn("cm_session", res.cookies)

    def test_me_sans_session_renvoie_401(self):
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["erreur"], "Non connecté.")

    def test_me_avec_session_valide(self):
        login(self.client, "20230145", "password")
        res = self.client.get("/api/auth/me")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"nom": "Ouédraogo", "prenom": "Aïcha", "role": "etudiant", "ufrId": None})

    def test_logout_revoque_la_session(self):
        login(self.client, "20230145", "password")
        res = self.client.post("/api/auth/logout")
        self.assertEqual(res.status_code, 200)
        res_me = self.client.get("/api/auth/me")
        self.assertEqual(res_me.status_code, 401)

    def test_compte_non_active_message_explicite(self):
        creer_compte("nouveau.etudiant", "Nouveau", "Etudiant", Role.ETUDIANT, active=False)
        res = login(self.client, "nouveau.etudiant", "peu importe")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["codeErreur"], "compte_non_active")

    def test_activation_definit_le_mot_de_passe_puis_permet_de_se_connecter(self):
        creer_compte("nouveau.etudiant", "Nouveau", "Etudiant", Role.ETUDIANT, active=False)
        res = post_json(
            self.client,
            "/api/auth/activate",
            {"identifiant": "nouveau.etudiant", "nouveauMotDePasse": "mon-mdp", "confirmationMotDePasse": "mon-mdp"},
        )
        self.assertEqual(res.status_code, 200)

        client2 = Client()
        res2 = login(client2, "nouveau.etudiant", "mon-mdp")
        self.assertEqual(res2.status_code, 200)

    def test_activation_deux_fois_est_refusee(self):
        # Compte déjà activé (self.compte) — FR-AUTH-03 : jamais une seconde fois.
        res = post_json(
            self.client,
            "/api/auth/activate",
            {"identifiant": "20230145", "nouveauMotDePasse": "autre", "confirmationMotDePasse": "autre"},
        )
        self.assertEqual(res.status_code, 400)
