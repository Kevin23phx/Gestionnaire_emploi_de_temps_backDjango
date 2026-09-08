from django.test import Client, TestCase

from accounts.models import Enseignant, EnseignantUfr, Role, Utilisateur
from tests.base import creer_compte, login, post_json


class EnseignantReferentielTests(TestCase):
    """[V3] FR-REF-04 révisée : enregistrer un enseignant crée une FICHE de
    référentiel, plus un compte de connexion. FR-REF-05 (activation du
    compte enseignant) est retirée avec le rôle correspondant."""

    def setUp(self):
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        creer_compte("scolarite.general", "Zerbo", "Idrissa", Role.ADMIN)
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")
        self.client_admin = Client()
        login(self.client_admin, "scolarite.general")

    def test_cree_une_fiche_enseignant_sans_aucun_compte(self):
        avant = Utilisateur.objects.count()
        res = post_json(self.client_sco, "/api/enseignants", {"nom": "Kaboré", "prenom": "Ismaël"})
        self.assertEqual(res.status_code, 201)

        enseignant = Enseignant.objects.get(nom="Kaboré")
        self.assertEqual(res.json()["enseignant"]["id"], enseignant.id)
        # INT-02 : la seule création de compte du système passe par `ufr`.
        self.assertEqual(Utilisateur.objects.count(), avant)

    def test_rattache_automatiquement_l_enseignant_a_l_ufr_du_gestionnaire(self):
        """FR-REF-06 : la trace de l'intervention est enregistrée, jamais
        demandée au Gestionnaire."""
        post_json(self.client_sco, "/api/enseignants", {"nom": "Traoré", "prenom": "Moussa"})
        enseignant = Enseignant.objects.get(nom="Traoré")
        self.assertTrue(EnseignantUfr.objects.filter(enseignant=enseignant, ufr_id="ufr-test").exists())

    def test_un_admin_ne_cree_pas_de_fiche_enseignant(self):
        """INV-11 : l'Admin n'écrit jamais dans le référentiel d'une UFR."""
        res = post_json(self.client_admin, "/api/enseignants", {"nom": "Kaboré", "prenom": "Ismaël"})
        self.assertEqual(res.status_code, 403)

    def test_un_appel_anonyme_ne_lit_pas_le_repertoire_des_enseignants(self):
        """INT-10 : le répertoire des enseignants n'est pas sur la surface
        publique — seul le nom porté par un créneau y apparaît."""
        self.assertEqual(Client().get("/api/enseignants").status_code, 401)

    def test_recherche_par_nom(self):
        """FR-FILT-04 : vérifier qu'un enseignant existe déjà, sans quitter
        le formulaire de créneau, plutôt que d'en créer un doublon."""
        post_json(self.client_sco, "/api/enseignants", {"nom": "Sawadogo", "prenom": "Fatimata"})
        post_json(self.client_sco, "/api/enseignants", {"nom": "Kaboré", "prenom": "Ismaël"})

        res = self.client_sco.get("/api/enseignants?recherche=sawa")
        self.assertEqual(len(res.json()["enseignants"]), 1)
        self.assertEqual(res.json()["enseignants"][0]["nom"], "Sawadogo")
