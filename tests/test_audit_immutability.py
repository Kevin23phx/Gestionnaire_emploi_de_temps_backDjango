import os

import psycopg
from django.conf import settings
from django.test import Client, TestCase

from accounts.models import Role
from audit.models import AuditEntry
from tests.base import creer_compte, login


class AuditImmutabilityTests(TestCase):
    """INV-04/INT-05 : deux lignes de défense indépendantes — aucune route
    PATCH/DELETE (vérifié ici), et le rôle applicatif Postgres n'a
    physiquement pas le droit UPDATE/DELETE sur audit_entry/conflit_journal
    (vérifié via une connexion psycopg distincte, authentifiée avec les
    identifiants du rôle restreint — jamais la connexion superutilisateur
    que Django utilise pour ce run de tests)."""

    def setUp(self):
        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")

    def test_aucune_route_patch_delete_sur_audit(self):
        entry = AuditEntry.objects.create(auteur="Test", action="Test", motif="—")
        self.assertEqual(self.client_sco.patch(f"/api/audit/{entry.id}").status_code, 404)
        self.assertEqual(self.client_sco.delete(f"/api/audit/{entry.id}").status_code, 404)

    def test_role_applicatif_ne_peut_pas_modifier_audit_entry(self):
        entry = AuditEntry.objects.create(auteur="Test", action="Test", motif="—")
        db = settings.DATABASES["default"]
        app_conninfo = (
            f"host={db['HOST']} port={db['PORT']} dbname={db['NAME']} "
            f"user=campus_manager_django_app password={os.environ['APP_DB_PASSWORD']}"
        )
        with psycopg.connect(app_conninfo) as conn, conn.cursor() as cur:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                cur.execute("UPDATE audit_entry SET motif = 'falsifie' WHERE id = %s", [entry.id])
