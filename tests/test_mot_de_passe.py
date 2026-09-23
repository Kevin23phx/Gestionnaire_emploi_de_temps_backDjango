"""[V8.3, 2026-09-23] Changement de mot de passe par son titulaire.

Défaut signalé par le porteur de projet : le mot de passe posé au
provisionnement restait en place indéfiniment — « codé en dur », connu de
quiconque avait vu le script d'amorçage, et impossible à changer. Un compte
dont on ne peut pas changer le secret n'est pas un compte personnel.

Ce que ces tests protègent, par ordre d'importance :

1. **Le mot de passe actuel est exigé**, même authentifié. Sans cette
   vérification, un poste laissé ouvert dans un couloir suffirait à
   s'emparer d'un compte pour de bon.
2. **On ne change que le SIEN.** L'utilisateur vient du cookie, jamais du
   corps de la requête.
3. **Les autres sessions tombent.** Changer son mot de passe sans fermer
   les sessions ouvertes ailleurs ne reprend la main sur rien.
"""

import json

from django.test import Client, TestCase

from accounts.models import Role, Session, Utilisateur
from tests.base import creer_compte, login, post_json, ufr_par_defaut


class ChangementMotDePasseTests(TestCase):
    def setUp(self):
        self.ufr = ufr_par_defaut()
        creer_compte("scolarite.test", "Ouedraogo", "Awa", Role.SCOLARITE, ufr_id=self.ufr)
        self.client = Client()
        login(self.client, "scolarite.test")

    def _changer(self, actuel="password", nouveau="nouveau-mot-de-passe", confirmation=None, client=None):
        return post_json(
            client or self.client,
            "/api/auth/mot-de-passe",
            {
                "motDePasseActuel": actuel,
                "nouveauMotDePasse": nouveau,
                "confirmationMotDePasse": confirmation if confirmation is not None else nouveau,
            },
        )

    # --- 1. Le chemin nominal ------------------------------------------

    def test_le_nouveau_mot_de_passe_devient_le_bon(self):
        self.assertEqual(self._changer().status_code, 200)
        self.assertEqual(login(Client(), "scolarite.test", "nouveau-mot-de-passe").status_code, 200)

    def test_l_ancien_mot_de_passe_ne_fonctionne_plus(self):
        self._changer()
        self.assertEqual(login(Client(), "scolarite.test", "password").status_code, 401)

    def test_l_utilisateur_reste_connecte_apres_le_changement(self):
        """Il vient de changer son mot de passe sur cet écran : le
        déconnecter ici lui ferait croire à un échec."""
        self._changer()
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)

    # --- 2. Les garde-fous ---------------------------------------------

    def test_le_mot_de_passe_actuel_est_exige_meme_authentifie(self):
        reponse = self._changer(actuel="pas-le-bon")
        self.assertEqual(reponse.status_code, 400)
        # Et rien n'a changé.
        self.assertEqual(login(Client(), "scolarite.test", "password").status_code, 200)

    def test_un_appel_anonyme_est_refuse(self):
        self.assertEqual(self._changer(client=Client()).status_code, 401)

    def test_les_deux_saisies_doivent_correspondre(self):
        self.assertEqual(self._changer(nouveau="abcdefgh", confirmation="abcdefgi").status_code, 400)

    def test_un_mot_de_passe_trop_court_est_refuse(self):
        self.assertEqual(self._changer(nouveau="court12").status_code, 400)

    def test_le_nouveau_doit_differer_de_l_actuel(self):
        """Un « changement » qui n'en est pas un laisserait croire à une
        rotation effectuée."""
        self.assertEqual(self._changer(nouveau="password").status_code, 400)

    def test_le_mot_de_passe_ne_peut_pas_etre_l_identifiant(self):
        """`scolarite.<sigle>` est une convention publique (FR-ADMIN-02) :
        c'est la première chose qu'essaierait quiconque la connaît."""
        self.assertEqual(self._changer(nouveau="scolarite.test").status_code, 400)

    # --- 3. Périmètre et sessions ---------------------------------------

    def test_on_ne_peut_changer_que_son_propre_mot_de_passe(self):
        """Le corps de la requête ne désigne personne : même en tentant d'y
        glisser un autre compte, c'est la session qui décide."""
        creer_compte("scolarite.autre", "Kabore", "Paul", Role.SCOLARITE, ufr_id=self.ufr)
        reponse = post_json(
            self.client,
            "/api/auth/mot-de-passe",
            {
                "identifiant": "scolarite.autre",
                "utilisateurId": Utilisateur.objects.get(identifiant="scolarite.autre").id,
                "motDePasseActuel": "password",
                "nouveauMotDePasse": "nouveau-mot-de-passe",
                "confirmationMotDePasse": "nouveau-mot-de-passe",
            },
        )
        self.assertEqual(reponse.status_code, 200)
        # C'est bien le compte connecté qui a changé, pas celui nommé.
        self.assertEqual(login(Client(), "scolarite.autre", "password").status_code, 200)
        self.assertEqual(login(Client(), "scolarite.test", "nouveau-mot-de-passe").status_code, 200)

    def test_les_sessions_ouvertes_ailleurs_sont_fermees(self):
        """Le geste sert à reprendre la main sur son compte : laisser vivre
        une session ouverte sur un autre poste le viderait de son sens."""
        autre_appareil = Client()
        login(autre_appareil, "scolarite.test")
        self.assertEqual(autre_appareil.get("/api/auth/me").status_code, 200)

        self._changer()

        self.assertEqual(autre_appareil.get("/api/auth/me").status_code, 401)

    def test_une_seule_session_subsiste_apres_le_changement(self):
        login(Client(), "scolarite.test")
        login(Client(), "scolarite.test")
        utilisateur = Utilisateur.objects.get(identifiant="scolarite.test")
        self.assertGreater(Session.objects.filter(utilisateur=utilisateur).count(), 1)

        self._changer()
        self.assertEqual(Session.objects.filter(utilisateur=utilisateur).count(), 1)

    def test_l_admin_peut_aussi_changer_le_sien(self):
        creer_compte("admin.test", "Admin", "Root", Role.ADMIN)
        client_admin = Client()
        login(client_admin, "admin.test")
        self.assertEqual(self._changer(client=client_admin).status_code, 200)


class PolitiqueMotDePasseActivationTests(TestCase):
    """[V8.3] La même politique s'applique à l'activation : une règle
    appliquée à un seul des deux chemins ne protège rien, il suffirait de
    passer par l'autre."""

    def setUp(self):
        creer_compte("scolarite.neuf", "Sawadogo", "Marie", Role.SCOLARITE, active=False, ufr_id=ufr_par_defaut())
        self.client = Client()

    def _activer(self, mot_de_passe: str):
        return post_json(
            self.client,
            "/api/auth/activate",
            {
                "identifiant": "scolarite.neuf",
                "nouveauMotDePasse": mot_de_passe,
                "confirmationMotDePasse": mot_de_passe,
            },
        )

    def test_activation_refuse_un_mot_de_passe_trop_court(self):
        self.assertEqual(self._activer("court12").status_code, 400)

    def test_activation_refuse_un_mot_de_passe_egal_a_l_identifiant(self):
        self.assertEqual(self._activer("scolarite.neuf").status_code, 400)

    def test_activation_accepte_un_mot_de_passe_conforme(self):
        self.assertEqual(self._activer("un-mot-de-passe").status_code, 200)
