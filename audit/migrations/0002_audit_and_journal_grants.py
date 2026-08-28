# INV-04 / INT-05 : "audit_entry" (et par la même logique "conflit_journal")
# ne doivent jamais être modifiables ni supprimables, y compris par un
# Gestionnaire ou l'Admin. Les vues n'exposent déjà aucune route
# PATCH/DELETE (première ligne de défense) ; ceci est la seconde,
# indépendante : le rôle applicatif Postgres n'a physiquement pas le droit
# UPDATE/DELETE sur ces deux tables, quel que soit le code qui tourne
# dessus. Idempotent — le mot de passe du rôle est fixé séparément par
# scripts/bootstrap-db-roles.sh (lit APP_DB_PASSWORD, jamais commité).
from django.conf import settings
from django.db import migrations

APP_ROLE = "campus_manager_django_app"


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
        ("planning", "0002_creneau_exclude_constraint"),
    ]

    operations = [
        migrations.RunSQL(
            sql=f"""
                DO $$
                BEGIN
                  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                    CREATE ROLE {APP_ROLE} LOGIN;
                  END IF;
                END $$;

                GRANT CONNECT ON DATABASE {settings.DATABASES['default']['NAME']} TO {APP_ROLE};
                GRANT USAGE ON SCHEMA public TO {APP_ROLE};
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE};
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE};

                REVOKE UPDATE, DELETE ON "audit_entry" FROM {APP_ROLE};
                REVOKE UPDATE, DELETE ON "conflit_journal" FROM {APP_ROLE};
                GRANT SELECT, INSERT ON "audit_entry" TO {APP_ROLE};
                GRANT SELECT, INSERT ON "conflit_journal" TO {APP_ROLE};

                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE};
                ALTER DEFAULT PRIVILEGES IN SCHEMA public
                  GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE};
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
