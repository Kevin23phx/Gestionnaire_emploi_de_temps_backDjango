from django.test import Client, TestCase

from accounts.models import Role
from planning.models import Creneau
from tests.base import creer_compte, creer_enseignant, creer_groupe, creer_salle, creer_ue, login, post_json


class PlanningConflictsTests(TestCase):
    def setUp(self):
        self.ue1 = creer_ue("Algorithmique Avancée", "COD1")
        self.ue2 = creer_ue("Bases de Données", "COD2")
        self.salle = creer_salle("Amphi A", 1000)
        self.autre_salle = creer_salle("Salle 402", 70)
        self.groupe1 = creer_groupe("Groupe 1")
        self.groupe2 = creer_groupe("Groupe 2")
        self.ens1 = creer_enseignant("Kaboré", "Ismaël")
        self.ens2 = creer_enseignant("Traoré", "Moussa")
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")

    def _creneau(self, ue, ens, groupe, salle, jour, hd, hf, **extra):
        return {"ueId": ue.id, "enseignantId": ens.id, "groupeId": groupe.id, "salleId": salle.id, "jour": jour, "heureDebut": hd, "heureFin": hf, **extra}

    def test_conflit_de_salle_409_sans_derogation_201_avec(self):
        existant = Creneau.objects.create(ue=self.ue1, enseignant=self.ens1, groupe=self.groupe1, salle=self.salle, jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)

        candidat = self._creneau(self.ue2, self.ens2, self.groupe2, self.salle, "lundi", "09:00", "09:30")
        rejet = post_json(self.client_sco, "/api/creneaux", {"creneaux": [candidat]})
        self.assertEqual(rejet.status_code, 409)
        self.assertIn("dérogation", rejet.json()["erreur"])
        self.assertTrue(any(c["type"] == "salle" for c in rejet.json()["conflits"]))

        avec_derogation = post_json(self.client_sco, "/api/creneaux", {"creneaux": [{**candidat, "motifDerogation": "Autorisé"}]})
        self.assertEqual(avec_derogation.status_code, 201)
        creneau_id = avec_derogation.json()["creneaux"][0]["id"]
        self.assertEqual(Creneau.objects.get(id=creneau_id).derogation_motif, "Autorisé")

    def test_conflit_enseignant_meme_enseignant_deux_creneaux_simultanes(self):
        Creneau.objects.create(ue=self.ue1, enseignant=self.ens1, groupe=self.groupe1, salle=self.salle, jour="mardi", heure_debut_minutes=9 * 60, heure_fin_minutes=10 * 60)
        candidat = self._creneau(self.ue2, self.ens1, self.groupe2, self.autre_salle, "mardi", "09:00", "09:45")
        res = post_json(self.client_sco, "/api/creneaux", {"creneaux": [candidat]})
        self.assertEqual(res.status_code, 409)
        self.assertTrue(any(c["type"] == "enseignant" for c in res.json()["conflits"]))

    def test_conflit_groupe_meme_groupe_deux_cours_simultanes(self):
        Creneau.objects.create(ue=self.ue1, enseignant=self.ens1, groupe=self.groupe1, salle=self.salle, jour="mercredi", heure_debut_minutes=9 * 60, heure_fin_minutes=10 * 60)
        candidat = self._creneau(self.ue2, self.ens2, self.groupe1, self.autre_salle, "mercredi", "09:00", "09:45")
        res = post_json(self.client_sco, "/api/creneaux", {"creneaux": [candidat]})
        self.assertEqual(res.status_code, 409)
        self.assertTrue(any(c["type"] == "groupe" for c in res.json()["conflits"]))

    def test_conflit_capacite_avertissement_accepte_sans_derogation_bloquante(self):
        petite_salle = creer_salle("Petite Salle", 2)
        # [V3.1] L'effectif est saisi sur le groupe, plus compté : RM-02
        # compare cette valeur à la capacité de la salle.
        self.groupe1.effectif = 5
        self.groupe1.save(update_fields=["effectif"])
        candidat = self._creneau(self.ue1, self.ens1, self.groupe1, petite_salle, "jeudi", "08:00", "09:00")
        res = post_json(self.client_sco, "/api/creneaux", {"creneaux": [candidat]})
        # Un avertissement de capacité seul n'empêche PAS la sauvegarde côté
        # moteur (pas de conflit "bloquant"), mais notre implémentation exige
        # une dérogation dès qu'un conflit (même avertissement) est détecté —
        # comportement identique au backend NestJS de référence.
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.json()["conflits"][0]["type"], "capacite")
        self.assertEqual(res.json()["conflits"][0]["gravite"], "avertissement")

        avec_derogation = post_json(self.client_sco, "/api/creneaux", {"creneaux": [{**candidat, "motifDerogation": "Accepté"}]})
        self.assertEqual(avec_derogation.status_code, 201)

    def test_atomicite_du_batch_un_item_en_conflit_fait_echouer_tout_le_lot(self):
        Creneau.objects.create(ue=self.ue1, enseignant=self.ens1, groupe=self.groupe1, salle=self.salle, jour="samedi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60)
        compte_avant = Creneau.objects.count()

        valide = self._creneau(self.ue2, self.ens2, self.groupe2, self.autre_salle, "samedi", "08:00", "08:45")
        en_conflit = self._creneau(self.ue1, self.ens1, self.groupe1, self.salle, "samedi", "08:30", "09:00")
        res = post_json(self.client_sco, "/api/creneaux", {"creneaux": [valide, en_conflit]})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(Creneau.objects.count(), compte_avant)

    def test_pause_fixe_est_rejetee(self):
        candidat = self._creneau(self.ue1, self.ens1, self.groupe1, self.salle, "lundi", "09:45", "10:30")
        res = post_json(self.client_sco, "/api/creneaux", {"creneaux": [candidat]})
        self.assertEqual(res.status_code, 400)
        self.assertIn("pause", res.json()["erreur"])
