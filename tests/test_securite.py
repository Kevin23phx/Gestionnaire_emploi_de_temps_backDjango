"""[V8.8, 2026-09-23] Durcissement OWASP — ce que les mesures garantissent.

Un réglage de sécurité qui n'est pas testé est un réglage qu'on croit
actif. Ces tests vérifient les mesures là où elles se voient : la réponse
HTTP, pas la valeur d'un réglage.
"""

import json

from django.core.cache import cache
from django.test import Client, TestCase
from rest_framework.throttling import SimpleRateThrottle

from accounts.models import Role
from tests.base import creer_compte, login, post_json, ufr_par_defaut


# La suite tourne avec des quotas volontairement énormes (.env.test) pour
# ne pas se brider elle-même — elle enchaîne des dizaines de connexions
# depuis la même adresse. Ces tests-ci restaurent des valeurs réalistes :
# ils ne prouveraient rien sinon.
#
# Et ils le font en remplaçant `THROTTLE_RATES` sur la classe, PAS avec
# `override_settings`. C'est un piège de DRF qui coûte du temps :
# `SimpleRateThrottle.THROTTLE_RATES` est un attribut de CLASSE, évalué à
# l'import du module. Le dictionnaire est donc déjà capturé quand un test
# modifie `settings.REST_FRAMEWORK`, et l'override ne produit aucun effet —
# les tests passaient au vert sans rien vérifier lors du premier essai.
LIMITES_REALISTES = {
    "connexion_ip": "10/min",
    "connexion_compte": "5/min",
    "activation": "5/min",
    "mot_de_passe": "5/min",
}


class ForceBruteTests(TestCase):
    """OWASP A07. Les identifiants sont publics et devinables
    (`scolarite.<sigle>`, FR-ADMIN-02) et le parc tient en douze comptes :
    sans limite de tentatives, un automate casse un mot de passe de huit
    caractères en quelques heures."""

    def setUp(self):
        # Le comptage vit dans le cache : le vider entre les tests, sinon
        # l'un épuise le quota de l'autre et on teste le vide.
        cache.clear()
        self._quotas_initiaux = SimpleRateThrottle.THROTTLE_RATES
        SimpleRateThrottle.THROTTLE_RATES = LIMITES_REALISTES
        creer_compte("scolarite.test", "Ouedraogo", "Awa", Role.SCOLARITE, ufr_id=ufr_par_defaut())

    def tearDown(self):
        SimpleRateThrottle.THROTTLE_RATES = self._quotas_initiaux
        cache.clear()

    def _essai(self, client, identifiant="scolarite.test", mot_de_passe="mauvais"):
        return client.post(
            "/api/auth/login",
            data=json.dumps({"identifiant": identifiant, "motDePasse": mot_de_passe}),
            content_type="application/json",
        )

    def test_les_tentatives_repetees_finissent_par_etre_refusees(self):
        client = Client()
        codes = [self._essai(client).status_code for _ in range(12)]
        self.assertIn(429, codes, f"aucun 429 sur 12 tentatives : {codes}")

    def test_changer_d_adresse_ne_suffit_pas_a_contourner(self):
        """LE test de l'attaque distribuée : chaque essai vient d'une IP
        différente, ce qui met en défaut la seule limite par adresse. C'est
        la limite PAR COMPTE VISÉ qui doit prendre le relais."""
        codes = []
        for i in range(12):
            client = Client(REMOTE_ADDR=f"203.0.113.{i}")
            codes.append(self._essai(client).status_code)
        self.assertIn(429, codes, f"aucun 429 en changeant d'IP à chaque essai : {codes}")

    def test_alterner_la_casse_de_l_identifiant_ne_double_pas_le_quota(self):
        """La base traite « Scolarite.TEST » et « scolarite.test » comme un
        seul compte : le compteur doit faire de même."""
        codes = []
        for i in range(12):
            client = Client(REMOTE_ADDR=f"198.51.100.{i}")
            variante = "scolarite.test" if i % 2 else "Scolarite.TEST"
            codes.append(self._essai(client, identifiant=variante).status_code)
        self.assertIn(429, codes, f"la casse a permis de contourner : {codes}")

    def test_une_connexion_legitime_passe_avant_la_limite(self):
        """Une mesure qui empêche de travailler serait désactivée le
        lendemain : la première tentative honnête doit aboutir."""
        self.assertEqual(login(Client(), "scolarite.test").status_code, 200)


class EnTetesSecuriteTests(TestCase):
    """OWASP A05. Ces en-têtes ne servent à rien s'ils ne sont pas SERVIS —
    or `SecurityMiddleware` manquait, et aucun réglage `SECURE_*` n'avait
    donc d'effet."""

    def setUp(self):
        cache.clear()

    def test_le_type_declare_ne_peut_pas_etre_devine(self):
        reponse = Client().get("/api/public/ufrs")
        self.assertEqual(reponse.headers.get("X-Content-Type-Options"), "nosniff")

    def test_l_api_ne_peut_pas_etre_encadree(self):
        reponse = Client().get("/api/public/ufrs")
        self.assertEqual(reponse.headers.get("X-Frame-Options"), "DENY")

    def test_l_adresse_complete_ne_fuite_pas_vers_un_tiers(self):
        reponse = Client().get("/api/public/ufrs")
        self.assertEqual(reponse.headers.get("Referrer-Policy"), "same-origin")


class CloisonnementRestantTests(TestCase):
    """OWASP A01. Vérifie que le durcissement n'a rien desserré : une route
    protégée reste fermée, et un rôle ne gagne rien."""

    def setUp(self):
        cache.clear()
        creer_compte("scolarite.test", "Ouedraogo", "Awa", Role.SCOLARITE, ufr_id=ufr_par_defaut())

    def test_les_routes_authentifiees_restent_fermees_aux_anonymes(self):
        anonyme = Client()
        for route in ["/api/groupes", "/api/creneaux", "/api/audit", "/api/specialites", "/api/ufrs"]:
            self.assertEqual(anonyme.get(route).status_code, 401, route)

    def test_un_gestionnaire_ne_change_pas_le_mot_de_passe_d_un_autre(self):
        creer_compte("scolarite.autre", "Kabore", "Paul", Role.SCOLARITE, ufr_id=ufr_par_defaut())
        client = Client()
        login(client, "scolarite.test")
        post_json(
            client,
            "/api/auth/mot-de-passe",
            {
                "identifiant": "scolarite.autre",
                "motDePasseActuel": "password",
                "nouveauMotDePasse": "un-nouveau-mot-de-passe",
                "confirmationMotDePasse": "un-nouveau-mot-de-passe",
            },
        )
        # L'autre compte est intact : la session décide, pas le corps.
        self.assertEqual(login(Client(), "scolarite.autre", "password").status_code, 200)
