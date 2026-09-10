"""[V4] 2026-09-09 — un créneau porte une DATE, plus un jour de semaine.

À l'UJKZ, l'emploi du temps n'est pas arrêté pour le semestre : il est publié
semaine par semaine, en fin de semaine précédente, et son contenu change d'une
semaine à l'autre (cette semaine Maths, la suivante Algorithmique). Le modèle
récurrent hérité des universités à programme semestriel ne pouvait pas
représenter ça : il produisait un cours répété à l'identique de la rentrée aux
examens, vacances comprises — ce qui s'est vu dès le premier abonnement à un
agenda réel.

Trois choses disparaissent avec la récurrence, et c'est une simplification
nette : la contrainte de récurrence elle-même, le modèle `SeanceAnnulee`
(annuler la séance du 14 revient maintenant à annuler le créneau du 14), et
les dates de période académique (plus rien à borner).

**La contrainte anti-double-réservation (INV-02) est reconstruite sur la
date.** C'est le point sensible de cette migration : sous l'ancien modèle,
deux cours du lundi dans la même salle s'excluaient toujours ; sous le
nouveau, ils ne s'excluent que s'il s'agit du même lundi. Sans cette
reconstruction, la garantie physique porterait sur une colonne supprimée.

Reprise des données : chaque créneau existant est reporté sur son jour de
semaine dans la semaine en cours. Les données de développement sont de la
démonstration — l'important est qu'elles restent cohérentes et consultables,
pas qu'elles conservent une date historique qui n'a jamais existé.
"""

import datetime

from django.db import migrations, models

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]


def reporter_sur_la_semaine_courante(apps, schema_editor):
    Creneau = apps.get_model("planning", "Creneau")
    aujourdhui = datetime.date.today()
    lundi = aujourdhui - datetime.timedelta(days=aujourdhui.weekday())

    reportes = 0
    for creneau in Creneau.objects.all():
        index = JOURS.index(creneau.jour) if creneau.jour in JOURS else 0
        Creneau.objects.filter(id=creneau.id).update(date=lundi + datetime.timedelta(days=index))
        reportes += 1
    print(f"  [V4] {reportes} créneau(x) reporté(s) sur la semaine du {lundi.isoformat()}.")


class Migration(migrations.Migration):

    dependencies = [
        ("planning", "0003_v3_seance_annulee_version_deplacement"),
        ("core", "0004_ufr_type"),
    ]

    operations = [
        # 1. La contrainte référence "jour" : elle doit tomber avant lui.
        migrations.RunSQL(
            sql='ALTER TABLE "creneau" DROP CONSTRAINT IF EXISTS creneau_no_double_booking;',
            reverse_sql=migrations.RunSQL.noop,
        ),
        # 2. La colonne date, d'abord nullable pour pouvoir être remplie.
        migrations.AddField(
            model_name="creneau", name="date", field=models.DateField(null=True)
        ),
        migrations.RunPython(reporter_sur_la_semaine_courante, migrations.RunPython.noop),
        migrations.AlterField(model_name="creneau", name="date", field=models.DateField()),
        # 3. Les index portaient sur "jour".
        migrations.RemoveIndex(model_name="creneau", name="creneau_salle_i_f3b16c_idx"),
        migrations.RemoveIndex(model_name="creneau", name="creneau_enseign_f76110_idx"),
        migrations.RemoveIndex(model_name="creneau", name="creneau_groupe__868f16_idx"),
        migrations.RemoveField(model_name="creneau", name="jour"),
        migrations.AddIndex(
            model_name="creneau",
            index=models.Index(fields=["salle", "date"], name="creneau_salle_i_c4db73_idx"),
        ),
        migrations.AddIndex(
            model_name="creneau",
            index=models.Index(fields=["enseignant", "date"], name="creneau_enseign_90ec66_idx"),
        ),
        migrations.AddIndex(
            model_name="creneau",
            index=models.Index(fields=["groupe", "date"], name="creneau_groupe__7e17c6_idx"),
        ),
        # 4. Le fantôme d'un cours déplacé pointe vers une date, plus un jour.
        migrations.RemoveField(model_name="creneau", name="ancien_jour"),
        migrations.AddField(
            model_name="creneau", name="ancienne_date", field=models.DateField(blank=True, null=True)
        ),
        # 5. SeanceAnnulee n'a plus d'objet : un créneau EST une séance datée.
        migrations.RemoveConstraint(model_name="seanceannulee", name="seance_annulee_unique"),
        migrations.RemoveConstraint(model_name="seanceannulee", name="seance_annulee_motif_requis"),
        migrations.DeleteModel(name="SeanceAnnulee"),
        # 6. INV-02 reconstruit sur la date.
        migrations.RunSQL(
            sql="""
                ALTER TABLE "creneau"
                  ADD CONSTRAINT creneau_no_double_booking
                  EXCLUDE USING gist (
                    "salle_id" WITH =,
                    "date" WITH =,
                    "plage" WITH &&
                  )
                  WHERE (statut <> 'annule' AND "derogation_motif" IS NULL);
            """,
            reverse_sql='ALTER TABLE "creneau" DROP CONSTRAINT creneau_no_double_booking;',
        ),
    ]
