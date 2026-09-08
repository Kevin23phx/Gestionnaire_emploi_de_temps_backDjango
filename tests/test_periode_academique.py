"""[V3] Période académique par UFR (FR-REF-16/17, INT-11).

Deux mécanismes en dépendent, et aucun n'est visible depuis l'écran : la
borne de fin de récurrence du flux calendrier — sans elle, un cours se
répète indéfiniment dans l'agenda des étudiants abonnés — et la validation
des dates d'annulation de séance.
"""

import datetime

from django.test import Client, TestCase

from accounts.models import Role
from audit.models import AuditEntry
from core.models import Ufr
from tests.base import creer_compte, creer_ufr, login, ufr_par_defaut


def put_json(client, path, data):
    import json

    return client.put(path, data=json.dumps(data), content_type="application/json")


class PeriodeAcademiqueTests(TestCase):
    def setUp(self):
        ufr_par_defaut()
        creer_ufr("ufr-b", "UFR B", "b")
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        creer_compte("scolarite.general", "Zerbo", "Idrissa", Role.ADMIN)
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")
        self.client_admin = Client()
        login(self.client_admin, "scolarite.general")

    def test_le_gestionnaire_definit_la_periode_de_son_ufr(self):
        res = put_json(
            self.client_sco,
            "/api/ufrs/periode",
            {"libelle": "Semestre 1", "debut": "2026-09-01", "fin": "2027-01-31"},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["ufr"]["periodeDebut"], "2026-09-01")

        ufr = Ufr.objects.get(id="ufr-test")
        self.assertEqual(ufr.periode_debut, datetime.date(2026, 9, 1))
        self.assertEqual(ufr.periode_libelle, "Semestre 1")

    def test_la_periode_ne_touche_que_sa_propre_ufr(self):
        """INT-07/FR-REF-17 : l'ufr_id vient de la session, jamais de la
        requête — un Gestionnaire ne peut pas déplacer la rentrée d'une UFR
        voisine, même en forgeant l'appel."""
        avant = Ufr.objects.get(id="ufr-b").periode_debut
        put_json(self.client_sco, "/api/ufrs/periode", {"debut": "2026-09-01", "fin": "2027-01-31", "ufrId": "ufr-b"})
        self.assertEqual(Ufr.objects.get(id="ufr-b").periode_debut, avant)
        self.assertEqual(Ufr.objects.get(id="ufr-test").periode_debut, datetime.date(2026, 9, 1))

    def test_refuse_une_fin_avant_le_debut(self):
        res = put_json(self.client_sco, "/api/ufrs/periode", {"debut": "2027-01-01", "fin": "2026-09-01"})
        self.assertEqual(res.status_code, 400)

    def test_refuse_des_dates_manquantes(self):
        self.assertEqual(put_json(self.client_sco, "/api/ufrs/periode", {"debut": "2026-09-01"}).status_code, 400)

    def test_un_admin_ne_definit_pas_la_periode_d_une_ufr(self):
        """INV-11 : l'Admin n'écrit jamais dans le périmètre d'une UFR."""
        res = put_json(self.client_admin, "/api/ufrs/periode", {"debut": "2026-09-01", "fin": "2027-01-31"})
        self.assertEqual(res.status_code, 403)

    def test_un_anonyme_ne_definit_pas_la_periode(self):
        res = put_json(Client(), "/api/ufrs/periode", {"debut": "2026-09-01", "fin": "2027-01-31"})
        self.assertEqual(res.status_code, 401)

    def test_le_changement_est_trace_a_l_audit(self):
        """Déplacer la fin de période raccourcit ou allonge d'un coup tous
        les flux calendrier de l'UFR, ce qui se voit chez chaque étudiant
        abonné. Ce n'est pas un réglage anodin."""
        put_json(self.client_sco, "/api/ufrs/periode", {"libelle": "S1", "debut": "2026-09-01", "fin": "2027-01-31"})
        self.assertTrue(AuditEntry.objects.filter(action__startswith="Période académique").exists())

    def test_la_periode_accompagne_l_ufr_dans_la_liste(self):
        """Trois écrans la lisent depuis GET /ufrs et n'ont pas d'autre
        endroit où aller la chercher."""
        put_json(self.client_sco, "/api/ufrs/periode", {"debut": "2026-09-01", "fin": "2027-01-31"})
        ufrs = self.client_sco.get("/api/ufrs").json()["ufrs"]
        test = next(u for u in ufrs if u["id"] == "ufr-test")
        self.assertEqual(test["periodeDebut"], "2026-09-01")
        self.assertEqual(test["periodeFin"], "2027-01-31")
