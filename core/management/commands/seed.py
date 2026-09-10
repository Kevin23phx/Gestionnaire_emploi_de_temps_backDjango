"""Données de démonstration.

[V3] Deux comptes de rôles seulement (Gestionnaire, Admin) : les comptes
Étudiant et Enseignant ont disparu avec les rôles correspondants — le
programme se consulte désormais sans compte, à la racine du site.

[V3.1] Le référentiel nominatif des étudiants a été supprimé : l'effectif
d'un groupe est un nombre saisi (RM-02). Les Enseignants, eux, restent des
entités du référentiel — un créneau doit toujours en porter un (INV-01).
"""

import datetime

from argon2 import PasswordHasher
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Enseignant, EnseignantUfr, Role, Session, Utilisateur
from audit.models import AuditEntry
from core.donnees_ujkz import ETABLISSEMENTS, NOMS_COMPLETS_A_CONFIRMER
from core.models import Ufr
from planning.models import ConflitJournal, Creneau
from public.models import AbonnementAlerte
from referentiel.models import Departement, Groupe, Salle, StructureGestionnaire, UniteEnseignement

hasher = PasswordHasher()


class Command(BaseCommand):
    help = "Réinitialise et peuple la base avec les données de démonstration Campus Manager."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Nettoyage des données existantes...")
        AbonnementAlerte.objects.all().delete()
        Departement.objects.all().delete()
        ConflitJournal.objects.all().delete()
        AuditEntry.objects.all().delete()
        Creneau.objects.all().delete()
        Session.objects.all().delete()
        Utilisateur.objects.all().delete()
        EnseignantUfr.objects.all().delete()
        Enseignant.objects.all().delete()
        Salle.objects.all().delete()
        Groupe.objects.all().delete()
        UniteEnseignement.objects.all().delete()
        Ufr.objects.all().delete()

        mot_de_passe_hash = hasher.hash("password")

        self.stdout.write("Établissements (V3.2 — référentiel officiel UJKZ)...")
        # [V4] Le programme est publié semaine par semaine. Le seed en pose
        # deux : la semaine en cours et la suivante — c'est exactement ce
        # qu'un étudiant trouve un vendredi, quand la scolarité vient de
        # faire sortir le programme de la semaine à venir.
        #
        # Calé sur la date du jour et non sur des dates fixes : un seed daté
        # en dur donnerait un programme public vide quelques semaines plus
        # tard, et laisserait croire à un bug.
        aujourdhui = datetime.date.today()
        lundi = aujourdhui - datetime.timedelta(days=aujourdhui.weekday())
        lundi_suivant = lundi + datetime.timedelta(days=7)

        def jour(nom, semaine=None):
            """Date réelle d'un jour de la semaine visée."""
            index = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"].index(nom)
            return (semaine or lundi) + datetime.timedelta(days=index)

        # [V3.2] Les 12 établissements réels (5 UFR + 6 instituts + 1 école
        # doctorale) et leurs 53 départements, depuis core/donnees_ujkz.py.
        Ufr.objects.bulk_create(
            [
                Ufr(id=f"ufr-{sigle}", nom=nom, sigle=sigle, type=type_etab)
                for sigle, nom, type_etab, _ in ETABLISSEMENTS
            ]
        )
        Departement.objects.bulk_create(
            [
                Departement(ufr_id=f"ufr-{sigle}", libelle=libelle)
                for sigle, _, _, departements in ETABLISSEMENTS
                for libelle in departements
            ]
        )
        # Les données pilotes ci-dessous (référentiel Informatique, créneaux,
        # conflits déjà tracés...) restent toutes rattachées à l'UFR-SEA —
        # Informatique en dépend réellement à l'UJKZ.
        ufr_pilote = "ufr-sea"

        self.stdout.write("Référentiel (UE, enseignants, salles, groupes)...")
        ue_algo = UniteEnseignement.objects.create(code="INFO301", intitule="Algorithmique Avancée", niveau="L3", ufr_id=ufr_pilote)
        ue_bdd = UniteEnseignement.objects.create(code="INFO302", intitule="Bases de Données (TP)", niveau="L3", ufr_id=ufr_pilote)
        ue_reseaux = UniteEnseignement.objects.create(code="INFO303", intitule="Réseaux I", niveau="L3", ufr_id=ufr_pilote)
        ue_prog_c = UniteEnseignement.objects.create(code="INFO201", intitule="Programmation C", niveau="L2", ufr_id=ufr_pilote)
        # [V3.3] Un cours mutualisé, pour que le cas « plusieurs départements »
        # soit visible dès la première ouverture de l'écran Cours.
        ue_maths = UniteEnseignement.objects.create(
            code="SEA101", intitule="Mathématiques pour l'ingénieur", niveau="L1", ufr_id=ufr_pilote
        )

        dep_sea = {d.libelle: d for d in Departement.objects.filter(ufr_id=ufr_pilote)}
        ue_algo.departements.set([dep_sea["Informatique"]])
        ue_bdd.departements.set([dep_sea["Informatique"]])
        ue_reseaux.departements.set([dep_sea["Informatique"]])
        ue_prog_c.departements.set([dep_sea["Informatique"]])
        # Dispensé à quatre départements à la fois : c'est exactement le cas
        # qu'un rattachement unique obligerait à saisir quatre fois.
        ue_maths.departements.set(
            [dep_sea["Informatique"], dep_sea["Physique"], dep_sea["Chimie"], dep_sea["Tronc Commun SEA"]]
        )

        kabore = Enseignant.objects.create(nom="Kaboré", prenom="Ismaël")
        traore = Enseignant.objects.create(nom="Traoré", prenom="Moussa")
        sawadogo = Enseignant.objects.create(nom="Sawadogo", prenom="Boukary")
        # FR-REF-06 : rattachement explicite à l'UFR-SEA, jamais déduit des
        # créneaux ci-dessous.
        EnseignantUfr.objects.bulk_create([EnseignantUfr(enseignant=e, ufr_id=ufr_pilote) for e in [kabore, traore, sawadogo]])

        amphi_a = Salle.objects.create(nom="Amphi A", batiment="Amphis Centraux", capacite=1000, type_usage="commune", ufr_id=ufr_pilote)
        salle_102 = Salle.objects.create(nom="Salle 102", batiment="UFR/SEA", capacite=40, type_usage="propre", ufr_id=ufr_pilote)
        Salle.objects.create(nom="Labo Info 1", batiment="UFR/SEA", capacite=30, type_usage="propre", ufr_id=ufr_pilote)
        salle_402 = Salle.objects.create(nom="Salle 402", batiment="UFR/SEA", capacite=70, type_usage="propre", ufr_id=ufr_pilote)
        # Salle volontairement petite : démo de conflit de capacité contre
        # l'effectif saisi du Groupe A (8 étudiants).
        salle_6 = Salle.objects.create(nom="Salle 6", batiment="UFR/SEA", capacite=6, type_usage="propre", ufr_id=ufr_pilote)

        # [V3.1] L'effectif est saisi, plus compté : il n'existe plus de
        # référentiel nominatif d'étudiants (voir referentiel/models.py).
        groupe_a = Groupe.objects.create(nom="L3 INFO - Groupe A", filiere="Informatique", niveau="L3", annee_academique="2025-2026", effectif=8, ufr_id=ufr_pilote)
        groupe_td1 = Groupe.objects.create(nom="L2 INFO - TD 1", filiere="Informatique", niveau="L2", annee_academique="2025-2026", effectif=6, ufr_id=ufr_pilote)

        # [V3.3] La filière d'un groupe DOIT être un département officiel de
        # son établissement. Le seed en avait quatre qui n'en étaient pas
        # ("Biologie", "Géologie", "Médecine" accentué, "Lettres Modernes"
        # sans le "(LM)") : ils apparaissaient dans la recherche publique à
        # côté du département officiel, donnant l'illusion d'un doublon —
        # « Medecine » ET « Médecine » côte à côte pour l'UFR/SDS.
        self.stdout.write("Autres établissements (données fictives pour observer le cloisonnement)...")

        # --- UFR-SVT ---
        ue_bio_cell = UniteEnseignement.objects.create(code="SVT101", intitule="Biologie Cellulaire", niveau="L1", ufr_id="ufr-svt")
        ue_geo_dyn = UniteEnseignement.objects.create(code="SVT102", intitule="Géodynamique Interne", niveau="L2", ufr_id="ufr-svt")
        amphi_svt = Salle.objects.create(nom="Amphi SVT 1", batiment="UFR/SVT", capacite=120, type_usage="propre", ufr_id="ufr-svt")
        groupe_svt_l1 = Groupe.objects.create(nom="L1 SVT - Groupe A", filiere="Biochimie et microbiologie", niveau="L1", annee_academique="2025-2026", effectif=95, ufr_id="ufr-svt")
        groupe_svt_l2 = Groupe.objects.create(nom="L2 Géologie", filiere="Sciences de la Terre", niveau="L2", annee_academique="2024-2025", effectif=42, ufr_id="ufr-svt")
        # FR-REF-06 : Kaboré Ismaël (déjà enseignant à l'UFR-SEA) intervient
        # AUSSI à l'UFR-SVT — même fiche Enseignant, une affectation de plus.
        EnseignantUfr.objects.create(enseignant=kabore, ufr_id="ufr-svt")
        ens_svt = Enseignant.objects.create(nom="Zongo", prenom="Alizèta")
        EnseignantUfr.objects.create(enseignant=ens_svt, ufr_id="ufr-svt")
        Creneau.objects.create(ue=ue_bio_cell, enseignant=ens_svt, groupe=groupe_svt_l1, salle=amphi_svt, date=jour("lundi"), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")
        Creneau.objects.create(ue=ue_geo_dyn, enseignant=kabore, groupe=groupe_svt_l2, salle=amphi_svt, date=jour("mardi"), heure_debut_minutes=10 * 60 + 15, heure_fin_minutes=12 * 60, statut="normal")

        # --- UFR-SH ---
        ue_socio_gen = UniteEnseignement.objects.create(code="SH101", intitule="Sociologie Générale", niveau="L2", ufr_id="ufr-sh")
        salle_sh = Salle.objects.create(nom="Salle 201", batiment="UFR/SH", capacite=60, type_usage="propre", ufr_id="ufr-sh")
        groupe_sh_l2 = Groupe.objects.create(nom="L2 Sociologie", filiere="Sociologie", niveau="L2", annee_academique="2024-2025", effectif=58, ufr_id="ufr-sh")
        ens_sh = Enseignant.objects.create(nom="Compaoré", prenom="Elie")
        EnseignantUfr.objects.create(enseignant=ens_sh, ufr_id="ufr-sh")
        Creneau.objects.create(ue=ue_socio_gen, enseignant=ens_sh, groupe=groupe_sh_l2, salle=salle_sh, date=jour("mercredi"), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")

        # --- UFR-SDS ---
        ue_anat = UniteEnseignement.objects.create(code="SDS101", intitule="Anatomie Générale", niveau="L1", ufr_id="ufr-sds")
        salle_sds = Salle.objects.create(nom="Amphi Santé", batiment="UFR/SDS", capacite=150, type_usage="propre", ufr_id="ufr-sds")
        groupe_sds_l1 = Groupe.objects.create(nom="L1 Médecine - Groupe A", filiere="Medecine", niveau="L1", annee_academique="2025-2026", effectif=140, ufr_id="ufr-sds")
        ens_sds = Enseignant.objects.create(nom="Ilboudo", prenom="Salimata")
        EnseignantUfr.objects.create(enseignant=ens_sds, ufr_id="ufr-sds")
        Creneau.objects.create(ue=ue_anat, enseignant=ens_sds, groupe=groupe_sds_l1, salle=salle_sds, date=jour("jeudi"), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")

        # --- UFR-LAC ---
        ue_lingu = UniteEnseignement.objects.create(code="LAC101", intitule="Linguistique Générale", niveau="L3", ufr_id="ufr-lac")
        salle_lac = Salle.objects.create(nom="Salle 105", batiment="UFR/LAC", capacite=50, type_usage="propre", ufr_id="ufr-lac")
        groupe_lac_l3 = Groupe.objects.create(nom="L3 Lettres Modernes", filiere="Lettres Modernes (LM)", niveau="L3", annee_academique="2023-2024", effectif=35, ufr_id="ufr-lac")
        ens_lac = Enseignant.objects.create(nom="Ouédraogo", prenom="Fatimata")
        EnseignantUfr.objects.create(enseignant=ens_lac, ufr_id="ufr-lac")
        Creneau.objects.create(ue=ue_lingu, enseignant=ens_lac, groupe=groupe_lac_l3, salle=salle_lac, date=jour("vendredi"), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")

        # --- [V3.2] Instituts et école doctorale ---
        # Un jeu minimal par établissement encore vide, pour que les 12
        # apparaissent dans la recherche publique. Sans au moins un groupe
        # ET un créneau, un établissement reste invisible de la cascade
        # (FR-PUB-02, qui ne propose jamais un chemin sans issue) — et
        # l'absence de l'IBAM ressemblerait alors à un bug plutôt qu'à une
        # base non encore remplie par sa scolarité.
        self.stdout.write("Instituts et école doctorale (jeu minimal de démonstration)...")
        JOURS_DEMO = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi"]
        for index, (sigle, nom_etab, type_etab, departements) in enumerate(ETABLISSEMENTS):
            ufr_id = f"ufr-{sigle}"
            if Groupe.objects.filter(ufr_id=ufr_id).exists():
                continue  # UFR déjà pourvue par les données pilotes ci-dessus

            departement = departements[0]
            niveau = "M1" if type_etab == "ecole_doctorale" else "L1"
            sigle_court = sigle.upper()

            ue = UniteEnseignement.objects.create(
                code=f"{sigle_court[:4]}101",
                intitule=f"Introduction — {departement}",
                niveau=niveau,
                ufr_id=ufr_id,
            )
            ue.departements.set(Departement.objects.filter(ufr_id=ufr_id, libelle=departement))
            salle = Salle.objects.create(
                nom=f"Salle A — {sigle_court}", batiment=sigle_court, capacite=80, type_usage="propre", ufr_id=ufr_id
            )
            groupe = Groupe.objects.create(
                nom=f"{niveau} {departement} - Groupe A",
                filiere=departement,
                niveau=niveau,
                annee_academique="2025-2026",
                effectif=60,
                ufr_id=ufr_id,
            )
            enseignant = Enseignant.objects.create(nom="Ouédraogo", prenom=f"Enseignant {sigle_court}")
            EnseignantUfr.objects.create(enseignant=enseignant, ufr_id=ufr_id)
            Creneau.objects.create(
                ue=ue, enseignant=enseignant, groupe=groupe, salle=salle,
                # Réparti sur la semaine plutôt que tout le lundi 8h : sinon
                # les 7 établissements se superposeraient sur la même case et
                # la démonstration donnerait l'impression d'un bug d'affichage.
                date=jour(JOURS_DEMO[index % len(JOURS_DEMO)]),
                heure_debut_minutes=8 * 60,
                heure_fin_minutes=10 * 60,
                statut="normal",
            )

        # --- Salle DEP (transversale) ---
        Salle.objects.create(nom="Grand Amphithéâtre Central", batiment="Bâtiment Administratif", capacite=800, type_usage="commune", structure_gestionnaire=StructureGestionnaire.DEP, ufr=None)

        self.stdout.write('Comptes de connexion (password: "password")...')
        # [V3] Plus aucun compte Étudiant ni Enseignant : le programme est
        # public (FR-PUB-01), il n'y a rien derrière une connexion pour eux.
        #
        # [V3.2] UN compte Gestionnaire par établissement — les 12, instituts
        # et école doctorale compris. Tous sont créés DÉJÀ ACTIVÉS avec le
        # mot de passe "password", à la demande du porteur de projet, pour
        # qu'il puisse se connecter à chacun sans passer par l'écran
        # d'activation. C'est un choix de DÉMONSTRATION : en production,
        # FR-AUTH-03 impose qu'un compte reste non activé (mot_de_passe_hash
        # à None) jusqu'à ce que son titulaire choisisse lui-même son mot de
        # passe — jamais un mot de passe commun connu de tous.
        Utilisateur.objects.create(identifiant="scolarite.general", mot_de_passe_hash=mot_de_passe_hash, nom="Zerbo", prenom="Idrissa", role=Role.ADMIN)
        Utilisateur.objects.bulk_create(
            [
                Utilisateur(
                    identifiant=f"scolarite.{sigle}",
                    mot_de_passe_hash=mot_de_passe_hash,
                    # L'UFR-SEA porte les données pilotes : son compte garde
                    # la persona de démonstration utilisée comme "auteur"
                    # dans les entrées d'audit ci-dessous.
                    nom="Savadogo" if sigle == "sea" else nom,
                    prenom="Rasmata" if sigle == "sea" else "Scolarité",
                    role=Role.SCOLARITE,
                    ufr_id=f"ufr-{sigle}",
                )
                for sigle, nom, _, _ in ETABLISSEMENTS
            ]
        )

        self.stdout.write("Créneaux (un seul jeu de données réconcilié)...")
        c1 = Creneau.objects.create(ue=ue_algo, enseignant=kabore, groupe=groupe_a, salle=amphi_a, date=jour("lundi"), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")

        # Scindé autour de la pause de 10h00-10h15.
        Creneau.objects.create(ue=ue_bdd, enseignant=traore, groupe=groupe_a, salle=salle_402, date=jour("mardi"), heure_debut_minutes=9 * 60, heure_fin_minutes=10 * 60, statut="modifie", motif="Changement de salle demandé par l'enseignant")
        Creneau.objects.create(ue=ue_bdd, enseignant=traore, groupe=groupe_a, salle=salle_402, date=jour("mardi"), heure_debut_minutes=10 * 60 + 15, heure_fin_minutes=12 * 60, statut="modifie", motif="Changement de salle demandé par l'enseignant")

        Creneau.objects.create(ue=ue_reseaux, enseignant=sawadogo, groupe=groupe_a, salle=salle_102, date=jour("mercredi"), heure_debut_minutes=7 * 60, heure_fin_minutes=9 * 60, statut="annule", motif="Absence enseignant")

        # FR-CONF-01 : même salle (Amphi A), même horaire (lundi 08h-10h) que
        # c1, mais un groupe différent — conflit de salle authentique.
        # "derogation_motif" est obligatoire pour que cette ligne puisse
        # physiquement coexister avec c1 (contrainte EXCLUDE).
        derogation_salle = "Amphi A exceptionnellement partagé le temps du semestre (accord DEP)"
        c_conflit_salle = Creneau.objects.create(ue=ue_prog_c, enseignant=traore, groupe=groupe_td1, salle=amphi_a, date=jour("lundi"), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal", derogation_motif=derogation_salle)
        AuditEntry.objects.create(auteur="Savadogo Rasmata", action="Création créneau — Programmation C (dérogation conflit: salle)", motif=derogation_salle, creneau_id=c_conflit_salle.id)
        # Trace du conflit lui-même — donne au dashboard un vrai
        # "conflitsDetectes" à compter dès le premier chargement.
        ConflitJournal.objects.create(
            type="salle", gravite="bloquant", titre="Double réservation — Amphi A",
            description="Algorithmique Avancée et Programmation C sur le même créneau (lundi 08:00-10:00).",
            creneau_a_id=c_conflit_salle.id, creneau_b_id=c1.id, derogation_motif=derogation_salle, detecte_par="Savadogo Rasmata",
        )

        # FR-CONF-04 : effectif saisi du Groupe A = 8 — la Salle 6
        # (6 places) déclenche un vrai avertissement de capacité (RM-02).
        Creneau.objects.create(ue=ue_bdd, enseignant=sawadogo, groupe=groupe_a, salle=salle_6, date=jour("jeudi"), heure_debut_minutes=10 * 60 + 15, heure_fin_minutes=12 * 60, statut="normal")

        # [V3] FR-EDT-07 : une séance annulée à une date précise, à la
        # place de l'ancienne "demande enseignant en attente". C'est
        # exactement le scénario décrit par les responsables : l'enseignant
        # téléphone pour signaler une absence, le Gestionnaire annule LA
        # séance concernée, le cours reprend la semaine suivante.
        # [V4] La semaine SUIVANTE, avec un programme différent — c'est le
        # cœur du modèle : d'une semaine à l'autre, ce ne sont pas les mêmes
        # cours. Et l'un d'eux y est annulé, pour que le cas soit visible dès
        # la première ouverture.
        self.stdout.write("Programme de la semaine suivante (contenu différent)...")
        Creneau.objects.create(
            ue=ue_maths, enseignant=traore, groupe=groupe_a, salle=salle_402,
            date=jour("lundi", lundi_suivant), heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60,
            statut="normal",
        )
        Creneau.objects.create(
            ue=ue_algo, enseignant=kabore, groupe=groupe_a, salle=amphi_a,
            date=jour("mercredi", lundi_suivant), heure_debut_minutes=14 * 60, heure_fin_minutes=16 * 60,
            statut="annule", motif="Conférence internationale — enseignant absent",
        )
        AuditEntry.objects.create(
            auteur="Savadogo Rasmata",
            action=f"Annulation créneau du {jour('mercredi', lundi_suivant).isoformat()} — Algorithmique Avancée",
            motif="Conférence internationale — enseignant absent",
            creneau_id=c1.id,
        )

        nb_departements = Departement.objects.count()
        self.stdout.write(
            f"\nTerminé. {len(ETABLISSEMENTS)} établissements, {nb_departements} départements."
        )
        self.stdout.write('\nComptes (mot de passe : "password", tous déjà activés) :')
        self.stdout.write("  Admin                       scolarite.general")
        for sigle, nom, type_etab, departements in ETABLISSEMENTS:
            prefixe = "UFR/" if type_etab == "ufr" else ""
            self.stdout.write(
                f"  Gestionnaire {prefixe + sigle.upper():<12} scolarite.{sigle:<10} "
                f"{len(departements)} département(s) — {nom}"
            )

        self.stdout.write("\n  [V3] Le programme se consulte SANS COMPTE, à la racine du site :")
        self.stdout.write(f"       UFR Sciences Exactes et Appliquées → Informatique → L3 → {groupe_a.nom}")
        self.stdout.write(f"       Semaines publiées  : {lundi.isoformat()} et {lundi_suivant.isoformat()}")

        # Les intitulés de départements viennent du responsable de la
        # scolarité et sont repris verbatim : rien à confirmer de ce côté
        # (voir ARBITRAGES dans core/donnees_ujkz.py). Le seul point encore
        # ouvert vient de nous — les noms complets que nous avons composés
        # pour les établissements dont la source ne donnait que le sigle.
        self.stdout.write(
            f"\n  [V3.2] Noms complets à faire confirmer (composés par nos soins, "
            f"la source ne donnait que le sigle) : {', '.join(s.upper() for s in NOMS_COMPLETS_A_CONFIRMER)}"
        )
