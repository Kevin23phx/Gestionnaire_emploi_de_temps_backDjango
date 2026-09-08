from django.test import Client, TestCase

from accounts.models import EnseignantUfr, Role, Utilisateur
from tests.base import creer_compte, creer_enseignant, creer_groupe, creer_salle, creer_ue, creer_ufr, login, patch_json, post_json

# V2 multi-UFR : INT-07 (un Gestionnaire ne voit/écrit jamais hors de sa
# propre UFR), INT-08 (un Étudiant n'est jamais dans deux UFR à la fois),
# INT-09 (seul l'Admin crée une UFR/un Gestionnaire).


class UfrMultiTenantTests(TestCase):
    def setUp(self):
        creer_ufr("ufr-a", "UFR Test A", "tsa")
        creer_ufr("ufr-b", "UFR Test B", "tsb")

        creer_compte("scolarite.general", "Zerbo", "Idrissa", Role.ADMIN)
        creer_compte("scolarite.tsa", "Gestionnaire", "A", Role.SCOLARITE, ufr_id="ufr-a")
        creer_compte("scolarite.tsb", "Gestionnaire", "B", Role.SCOLARITE, ufr_id="ufr-b")

        self.groupe_a = creer_groupe("Groupe UFR-A", "Informatique", "L3", ufr_id="ufr-a")
        self.groupe_b = creer_groupe("Groupe UFR-B", "Droit", "L2", ufr_id="ufr-b")

        self.client_admin = Client()
        login(self.client_admin, "scolarite.general")
        self.client_a = Client()
        login(self.client_a, "scolarite.tsa")
        self.client_b = Client()
        login(self.client_b, "scolarite.tsb")

    # --- Création d'UFR et de comptes Gestionnaire ---

    def test_gestionnaire_ne_peut_pas_creer_d_ufr(self):
        res = post_json(self.client_a, "/api/ufrs", {"nom": "UFR Pirate", "sigle": "pir"})
        self.assertEqual(res.status_code, 403)

    def test_admin_cree_une_ufr_puis_un_compte_gestionnaire(self):
        res_ufr = post_json(self.client_admin, "/api/ufrs", {"nom": "UFR Sciences Vie et Terre (test)", "sigle": "svtx"})
        self.assertEqual(res_ufr.status_code, 201)
        self.assertEqual(res_ufr.json()["ufr"]["sigle"], "svtx")

        res_gest = post_json(self.client_admin, f"/api/ufrs/{res_ufr.json()['ufr']['id']}/gestionnaire", {"nom": "Kaboré", "prenom": "Fatimata"})
        self.assertEqual(res_gest.status_code, 201)
        self.assertEqual(res_gest.json()["identifiant"], "scolarite.svtx")

        compte = Utilisateur.objects.get(identifiant="scolarite.svtx")
        self.assertEqual(compte.role, Role.SCOLARITE)
        self.assertIsNone(compte.mot_de_passe_hash)
        self.assertEqual(compte.ufr_id, res_ufr.json()["ufr"]["id"])

    def test_refuse_un_second_gestionnaire_pour_une_ufr_qui_en_a_deja_un(self):
        res = post_json(self.client_admin, "/api/ufrs/ufr-a/gestionnaire", {"nom": "Autre", "prenom": "Gestionnaire"})
        self.assertEqual(res.status_code, 409)

    # --- Cloisonnement du référentiel ---

    def test_groupes_ne_renvoie_que_ceux_de_sa_propre_ufr(self):
        res = self.client_a.get("/api/groupes")
        ids = [g["id"] for g in res.json()["groupes"]]
        self.assertIn(self.groupe_a.id, ids)
        self.assertNotIn(self.groupe_b.id, ids)

    def test_admin_voit_toutes_les_ufr(self):
        res = self.client_admin.get("/api/groupes")
        ids = [g["id"] for g in res.json()["groupes"]]
        self.assertIn(self.groupe_a.id, ids)
        self.assertIn(self.groupe_b.id, ids)

    def test_creation_rattache_toujours_a_sa_propre_ufr(self):
        res_groupe = post_json(self.client_a, "/api/groupes", {"nom": "Nouveau Groupe A", "filiere": "Informatique", "niveau": "L1", "anneeAcademique": "2025-2026"})
        self.assertEqual(res_groupe.json()["groupe"]["ufrId"], "ufr-a")

        res_salle = post_json(self.client_a, "/api/salles", {"nom": "Salle Test A", "batiment": "Bât. A", "capacite": 30, "typeUsage": "propre"})
        self.assertEqual(res_salle.json()["salle"]["ufrId"], "ufr-a")
        self.assertEqual(res_salle.json()["salle"]["structureGestionnaire"], "UFR")

        res_cours = post_json(self.client_a, "/api/cours", {"intitule": "Cours Test A", "niveau": "L1"})
        self.assertEqual(res_cours.json()["ue"]["ufrId"], "ufr-a")

    def test_admin_ne_cree_que_des_salles_dep(self):
        res = post_json(self.client_admin, "/api/salles", {"nom": "Amphi Commun DEP", "batiment": "Bât. Central", "capacite": 500, "typeUsage": "commune"})
        self.assertEqual(res.json()["salle"]["structureGestionnaire"], "DEP")
        self.assertIsNone(res.json()["salle"]["ufrId"])

    # --- Groupes (effectif saisi, [V3.1]) ---

    def test_gestionnaire_modifie_l_effectif_de_son_propre_groupe(self):
        """L'effectif bouge en cours d'année : sans cette route, la détection
        de conflit de capacité travaillerait sur la valeur du jour de la
        création (RM-02)."""
        res = patch_json(self.client_a, f"/api/groupes/{self.groupe_a.id}", {"effectif": 120})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["groupe"]["effectif"], 120)

    def test_gestionnaire_ne_modifie_pas_le_groupe_d_une_autre_ufr(self):
        """INT-07."""
        res = patch_json(self.client_b, f"/api/groupes/{self.groupe_a.id}", {"effectif": 999})
        self.assertEqual(res.status_code, 409)
        self.groupe_a.refresh_from_db()
        self.assertNotEqual(self.groupe_a.effectif, 999)

    def test_effectif_negatif_refuse(self):
        """Un effectif négatif désactiverait silencieusement la détection de
        conflit de capacité, seule chose que cette valeur alimente."""
        res = patch_json(self.client_a, f"/api/groupes/{self.groupe_a.id}", {"effectif": -5})
        self.assertEqual(res.status_code, 400)

    def test_effectif_non_numerique_refuse(self):
        res = patch_json(self.client_a, f"/api/groupes/{self.groupe_a.id}", {"effectif": "beaucoup"})
        self.assertEqual(res.status_code, 400)

    def test_un_anonyme_ne_modifie_pas_un_groupe(self):
        from django.test import Client

        res = patch_json(Client(), f"/api/groupes/{self.groupe_a.id}", {"effectif": 1})
        self.assertEqual(res.status_code, 401)

    # --- Planning ---

    def test_rejette_creation_creneau_sur_groupe_d_une_autre_ufr(self):
        ue = creer_ue("Cours UFR-B", "COD-B", "ufr-b")
        salle = creer_salle("Salle UFR-B", 50, ufr_id="ufr-b")
        ens = creer_enseignant("Sawadogo", "Boukary")

        res = post_json(
            self.client_a,
            "/api/creneaux",
            {"creneaux": [{"ueId": ue.id, "enseignantId": ens.id, "groupeId": self.groupe_b.id, "salleId": salle.id, "jour": "lundi", "heureDebut": "08:00", "heureFin": "10:00"}]},
        )
        self.assertEqual(res.status_code, 403)

    def test_enseignant_jamais_bloque_affectation_automatique(self):
        """Retour d'usage 2026-08-27 : tout enseignant capable de dispenser
        le cours doit pouvoir être affecté — l'affectation à l'UFR se fait
        automatiquement, jamais un blocus."""
        ue = creer_ue("Cours UFR-A externe", "COD-EXT", "ufr-a")
        salle = creer_salle("Salle Test Externe", 40, ufr_id="ufr-a")
        ens_externe = creer_enseignant("Diallo", "Karim")  # affecté par défaut à "ufr-test", étranger à ufr-a

        res = post_json(
            self.client_a,
            "/api/creneaux",
            {"creneaux": [{"ueId": ue.id, "enseignantId": ens_externe.id, "groupeId": self.groupe_a.id, "salleId": salle.id, "jour": "samedi", "heureDebut": "08:00", "heureFin": "09:00"}]},
        )
        self.assertEqual(res.status_code, 201)
        self.assertTrue(EnseignantUfr.objects.filter(enseignant=ens_externe, ufr_id="ufr-a").exists())

    # --- Enseignant multi-UFR ---

    def test_enseignant_peut_etre_affecte_a_une_seconde_ufr(self):
        res_creation = post_json(self.client_a, "/api/enseignants", {"nom": "Traoré", "prenom": "Moussa", "identifiant": "traore.multiufr"})
        enseignant_id = res_creation.json()["enseignant"]["id"]
        self.assertEqual([a.ufr_id for a in EnseignantUfr.objects.filter(enseignant_id=enseignant_id)], ["ufr-a"])

        res_affecter = self.client_b.post(f"/api/enseignants/{enseignant_id}/affecter-ufr")
        self.assertEqual(res_affecter.status_code, 201)
        self.assertEqual(sorted(a.ufr_id for a in EnseignantUfr.objects.filter(enseignant_id=enseignant_id)), ["ufr-a", "ufr-b"])

        res_doublon = self.client_b.post(f"/api/enseignants/{enseignant_id}/affecter-ufr")
        self.assertEqual(res_doublon.status_code, 409)

    # --- Audit ---

    def test_audit_ne_fuite_jamais_entre_ufr(self):
        ue = creer_ue("Cours Audit UFR-B", "COD-AUD-B", "ufr-b")
        salle = creer_salle("Salle Audit UFR-B", 50, ufr_id="ufr-b")
        ens = creer_enseignant("Kagambega", "Rasmané", ufr_id="ufr-b")

        res = post_json(
            self.client_b,
            "/api/creneaux",
            {"creneaux": [{"ueId": ue.id, "enseignantId": ens.id, "groupeId": self.groupe_b.id, "salleId": salle.id, "jour": "vendredi", "heureDebut": "08:00", "heureFin": "10:00"}]},
        )
        self.assertEqual(res.status_code, 201)

        audit_a = self.client_a.get("/api/audit")
        self.assertFalse(any("Cours Audit UFR-B" in e["action"] for e in audit_a.json()["entries"]))
        audit_b = self.client_b.get("/api/audit")
        self.assertTrue(any("Cours Audit UFR-B" in e["action"] for e in audit_b.json()["entries"]))
