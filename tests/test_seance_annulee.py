"""[V3] Annulation d'une séance à une date précise (FR-EDT-07, INV-14, RM-10).

Le cas d'usage central de la V3 côté gestion : un enseignant téléphone pour
signaler une absence ponctuelle. Avant, la seule réponse possible retirait
le cours du programme pour tout le semestre.
"""

import datetime

from django.test import Client, TestCase

from accounts.models import Role
from audit.models import AuditEntry
from core.models import Ufr
from planning.models import Creneau, SeanceAnnulee
from tests.base import (
    creer_compte,
    creer_enseignant,
    creer_groupe,
    creer_salle,
    creer_ue,
    creer_ufr,
    login,
    post_json,
    prochain,
    ufr_par_defaut,
)


class SeanceAnnuleeTests(TestCase):
    def setUp(self):
        ufr_par_defaut()
        creer_ufr("ufr-b", "UFR B", "b")
        self.ue = creer_ue("Algorithmique Avancée")
        self.salle = creer_salle("Amphi A", 1000)
        self.groupe = creer_groupe("Groupe A")
        self.enseignant = creer_enseignant("Kaboré", "Ismaël")
        self.creneau = Creneau.objects.create(
            ue=self.ue, enseignant=self.enseignant, groupe=self.groupe, salle=self.salle,
            jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60,
        )
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        creer_compte("scolarite.b", "Gestionnaire", "B", Role.SCOLARITE, ufr_id="ufr-b")
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")
        self.client_b = Client()
        login(self.client_b, "scolarite.b")
        self.lundi = prochain("lundi")

    def _annuler(self, client=None, date=None, motif="Absence enseignant"):
        return post_json(
            client or self.client_sco,
            f"/api/creneaux/{self.creneau.id}/seance",
            {"date": (date or self.lundi).isoformat(), "motif": motif},
        )

    def test_annule_une_seule_occurrence_et_laisse_le_creneau_actif(self):
        """INV-14 : c'est toute la différence avec FR-EDT-03."""
        res = self._annuler()
        self.assertEqual(res.status_code, 200)

        self.creneau.refresh_from_db()
        self.assertEqual(self.creneau.statut, "normal")
        self.assertEqual(SeanceAnnulee.objects.filter(creneau=self.creneau).count(), 1)

    def test_incremente_la_revision_du_creneau(self):
        """INV-13 : sans cet incrément, les agendas déjà abonnés ignorent
        l'annulation — le mécanisme aurait l'air de marcher sans rien
        transmettre."""
        avant = self.creneau.version
        self._annuler()
        self.creneau.refresh_from_db()
        self.assertEqual(self.creneau.version, avant + 1)

    def test_motif_obligatoire(self):
        """INT-03 : jamais d'annulation muette, ici comme sur un créneau."""
        res = post_json(
            self.client_sco, f"/api/creneaux/{self.creneau.id}/seance", {"date": self.lundi.isoformat()}
        )
        self.assertEqual(res.status_code, 400)

    def test_refuse_une_date_qui_ne_tombe_pas_le_bon_jour(self):
        """Sans ce contrôle, l'annulation ne suspendrait rien du tout et le
        Gestionnaire croirait l'absence traitée."""
        mardi = self.lundi + datetime.timedelta(days=1)
        res = self._annuler(date=mardi)
        self.assertEqual(res.status_code, 400)
        self.assertIn("lundi", res.json()["erreur"])

    def test_refuse_une_date_hors_periode_academique(self):
        """INT-11 : on n'annule pas une séance jamais programmée."""
        ufr = Ufr.objects.get(id=ufr_par_defaut())
        hors = ufr.periode_fin + datetime.timedelta(days=30)
        hors = hors + datetime.timedelta(days=(0 - hors.weekday()) % 7)  # un lundi
        res = self._annuler(date=hors)
        self.assertEqual(res.status_code, 400)
        self.assertIn("période académique", res.json()["erreur"])

    def test_refuse_sur_un_creneau_deja_annule_pour_toute_la_periode(self):
        """ERR-09 : une annulation d'annulation ne s'interpréterait pas."""
        Creneau.objects.filter(id=self.creneau.id).update(statut="annule", motif="Cours supprimé")
        res = self._annuler()
        self.assertEqual(res.status_code, 400)

    def test_refuse_un_doublon(self):
        self._annuler()
        res = self._annuler()
        self.assertEqual(res.status_code, 409)

    def test_un_gestionnaire_d_une_autre_ufr_ne_peut_pas_annuler(self):
        """INT-07 : lever le cloisonnement en LECTURE pour le public n'a rien
        levé du côté écriture."""
        res = self._annuler(client=self.client_b)
        self.assertEqual(res.status_code, 403)

    def test_un_anonyme_ne_peut_pas_annuler(self):
        """INV-05 élargi."""
        res = post_json(Client(), f"/api/creneaux/{self.creneau.id}/seance", {"date": self.lundi.isoformat(), "motif": "x"})
        self.assertEqual(res.status_code, 401)

    def test_l_annulation_est_tracee_a_l_audit(self):
        """FR-AUD-01 : le circuit de demandes a disparu, la traçabilité non.
        C'est la contrepartie explicite de sa suppression (02_SRS §2.7)."""
        self._annuler(motif="Conférence internationale")
        entree = AuditEntry.objects.filter(creneau_id=self.creneau.id).latest("date_heure")
        self.assertIn("Annulation séance", entree.action)
        self.assertIn(self.lundi.isoformat(), entree.action)
        self.assertEqual(entree.motif, "Conférence internationale")

    def test_retablir_une_seance_annulee_par_erreur(self):
        self._annuler()
        res = self.client_sco.delete(
            f"/api/creneaux/{self.creneau.id}/seance?date={self.lundi.isoformat()}"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(SeanceAnnulee.objects.count(), 0)
        # Le rétablissement est tracé lui aussi : l'audit doit raconter
        # l'histoire complète, pas seulement sa première moitié (INV-04).
        self.assertTrue(
            AuditEntry.objects.filter(creneau_id=self.creneau.id, action__startswith="Rétablissement").exists()
        )

    def test_retablir_une_seance_qui_n_etait_pas_annulee(self):
        res = self.client_sco.delete(
            f"/api/creneaux/{self.creneau.id}/seance?date={self.lundi.isoformat()}"
        )
        self.assertEqual(res.status_code, 404)
