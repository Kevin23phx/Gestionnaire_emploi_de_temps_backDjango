# INV-02 / FR-CONF-01 : filet de sécurité physique contre le double
# réservation d'une salle, indépendant de toute logique applicative — même
# approche que le backend NestJS d'origine (colonne générée + EXCLUDE USING
# gist), traduite en RunSQL brut plutôt que via l'API déclarative Django
# (trop spécifique à PostgreSQL pour être exprimée proprement autrement).
from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("planning", "0001_initial")]

    operations = [
        BtreeGistExtension(),
        migrations.RunSQL(
            sql="""
                ALTER TABLE "creneau"
                  ADD COLUMN "plage" int4range
                  GENERATED ALWAYS AS (int4range("heure_debut_minutes", "heure_fin_minutes", '[)')) STORED;

                ALTER TABLE "creneau"
                  ADD CONSTRAINT creneau_no_double_booking
                  EXCLUDE USING gist (
                    "salle_id" WITH =,
                    "jour" WITH =,
                    "plage" WITH &&
                  )
                  WHERE (statut <> 'annule' AND "derogation_motif" IS NULL);
            """,
            reverse_sql="""
                ALTER TABLE "creneau" DROP CONSTRAINT creneau_no_double_booking;
                ALTER TABLE "creneau" DROP COLUMN "plage";
            """,
        ),
    ]
