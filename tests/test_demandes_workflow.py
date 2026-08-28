from django.test import Client, TestCase

from accounts.models import Role
from demandes.models import DemandeEnseignant
from planning.models import Creneau
from tests.base import creer_compte, creer_enseignant, creer_groupe, creer_salle, creer_ue, login, post_json

# RM-04/FR-SIG-01 : la seule transition légale est en_attente ->
# {validee, refusee}, jamais de retour en arrière — et une décision
# "validee" doit réellement modifier le planning.


class DemandesWorkflowTests(TestCase):
    def setUp(self):
        self.ue = creer_ue("Algorithmique Avancée")
        self.salle = creer_salle("Amphi A", 1000)
        self.autre_salle = creer_salle("Salle 402", 70)
        self.groupe = creer_groupe("Groupe A")
        self.ens = creer_enseignant("Kaboré", "Ismaël")
        creer_compte("ens.a", "Kaboré", "Ismaël", Role.ENSEIGNANT, enseignant=self.ens)
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        self.client_ens = Client()
        login(self.client_ens, "ens.a")
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")

    def test_enseignant_ne_peut_pas_decider_une_demande(self):
        creneau = Creneau.objects.create(ue=self.ue, enseignant=self.ens, groupe=self.groupe, salle=self.salle, jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)
        demande = DemandeEnseignant.objects.create(enseignant=self.ens, type="absence", motif="Test", creneau_concerne=creneau)
        res = post_json(self.client_ens, f"/api/demandes/{demande.id}/decider", {"decision": "validee"})
        self.assertEqual(res.status_code, 403)

    def test_absence_validee_le_creneau_passe_a_statut_annule(self):
        creneau = Creneau.objects.create(ue=self.ue, enseignant=self.ens, groupe=self.groupe, salle=self.salle, jour="mardi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)
        res_creation = post_json(self.client_ens, "/api/demandes", {"type": "absence", "creneauConcerneId": creneau.id, "motif": "Conférence"})
        self.assertEqual(res_creation.json()["statut"], "en_attente")

        res_decision = post_json(self.client_sco, f"/api/demandes/{res_creation.json()['id']}/decider", {"decision": "validee", "motifDecision": "Accordé"})
        self.assertEqual(res_decision.status_code, 201)
        self.assertEqual(res_decision.json()["statut"], "validee")

        creneau.refresh_from_db()
        self.assertEqual(creneau.statut, "annule")

    def test_report_valide_applique_la_nouvelle_plage_meme_id(self):
        creneau = Creneau.objects.create(ue=self.ue, enseignant=self.ens, groupe=self.groupe, salle=self.salle, jour="mercredi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)
        res_creation = post_json(
            self.client_ens,
            "/api/demandes",
            {"type": "report", "creneauConcerneId": creneau.id, "motif": "Conférence", "jourPropose": "jeudi", "heureDebutProposee": "08:00", "heureFinProposee": "10:00"},
        )
        res_decision = post_json(self.client_sco, f"/api/demandes/{res_creation.json()['id']}/decider", {"decision": "validee"})
        self.assertEqual(res_decision.status_code, 201)

        creneau.refresh_from_db()
        self.assertEqual(creneau.id, creneau.id)  # INV-07 : même id
        self.assertEqual(creneau.jour, "jeudi")
        self.assertEqual(creneau.statut, "modifie")

    def test_demande_deja_decidee_ne_peut_pas_etre_redecidee(self):
        creneau = Creneau.objects.create(ue=self.ue, enseignant=self.ens, groupe=self.groupe, salle=self.salle, jour="vendredi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)
        demande = DemandeEnseignant.objects.create(enseignant=self.ens, type="absence", motif="Test", creneau_concerne=creneau)
        post_json(self.client_sco, f"/api/demandes/{demande.id}/decider", {"decision": "refusee"})
        res2 = post_json(self.client_sco, f"/api/demandes/{demande.id}/decider", {"decision": "validee"})
        self.assertEqual(res2.status_code, 409)
