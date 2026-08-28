"""Données de démonstration — traduction directe de
backend/prisma/seed.ts (backend NestJS de référence, dépôt distinct
appartenant à un coéquipier). Mêmes comptes de démo (mot de passe
"password" pour tous)."""

from argon2 import PasswordHasher
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import Enseignant, EnseignantUfr, Role, Session, Utilisateur
from audit.models import AuditEntry
from core.models import Ufr
from demandes.models import DemandeEnseignant
from notifications.models import NotificationItem
from planning.models import ConflitJournal, Creneau
from referentiel.models import Etudiant, Groupe, Salle, StructureGestionnaire, UniteEnseignement

hasher = PasswordHasher()


class Command(BaseCommand):
    help = "Réinitialise et peuple la base avec les données de démonstration Campus Manager."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Nettoyage des données existantes...")
        NotificationItem.objects.all().delete()
        ConflitJournal.objects.all().delete()
        DemandeEnseignant.objects.all().delete()
        AuditEntry.objects.all().delete()
        Creneau.objects.all().delete()
        Session.objects.all().delete()
        Utilisateur.objects.all().delete()
        EnseignantUfr.objects.all().delete()
        Etudiant.objects.all().delete()
        Enseignant.objects.all().delete()
        Salle.objects.all().delete()
        Groupe.objects.all().delete()
        UniteEnseignement.objects.all().delete()
        Ufr.objects.all().delete()

        mot_de_passe_hash = hasher.hash("password")

        self.stdout.write("UFR (V2 multi-UFR — les 5 UFR réelles de l'UJKZ)...")
        Ufr.objects.bulk_create(
            [
                Ufr(id="ufr-sh", nom="UFR Sciences Humaines", sigle="sh"),
                Ufr(id="ufr-sds", nom="UFR Sciences de la Santé", sigle="sds"),
                Ufr(id="ufr-svt", nom="UFR Sciences de la Vie et de la Terre", sigle="svt"),
                Ufr(id="ufr-sea", nom="UFR Sciences Exactes et Appliquées", sigle="sea"),
                Ufr(id="ufr-lac", nom="UFR Lettres Arts et Communication", sigle="lac"),
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
        # Salle volontairement petite : démo de conflit de capacité contre un
        # effectif RÉELLEMENT compté (8 étudiants).
        salle_6 = Salle.objects.create(nom="Salle 6", batiment="UFR/SEA", capacite=6, type_usage="propre", ufr_id=ufr_pilote)

        groupe_a = Groupe.objects.create(nom="L3 INFO - Groupe A", filiere="Informatique", niveau="L3", annee_academique="2025-2026", ufr_id=ufr_pilote)
        groupe_td1 = Groupe.objects.create(nom="L2 INFO - TD 1", filiere="Informatique", niveau="L2", annee_academique="2025-2026", ufr_id=ufr_pilote)

        self.stdout.write("Étudiants...")
        # L'INE encode l'année d'inscription (préfixe "2023" = rentrée
        # 2023-2024) — anneeAcademique la reprend fidèlement (FR-REF-09).
        etudiants_groupe_a = [
            Etudiant.objects.create(
                ine=ine, nom=nom, prenom=prenom, filiere="Informatique", niveau="L3", annee_academique="2023-2024",
                groupe=groupe_a, ufr_id=ufr_pilote,
            )
            for ine, nom, prenom in [
                ("20230145", "Ouédraogo", "Aïcha"),
                ("20230101", "Kaboré", "Awa"),
                ("20230102", "Zongo", "Issa"),
                ("20230103", "Compaoré", "Fatoumata"),
                ("20230104", "Ouattara", "Boureima"),
                ("20230105", "Nikiéma", "Salamata"),
                ("20230106", "Bamogo", "Yacouba"),
                ("20230107", "Ilboudo", "Nathalie"),
            ]
        ]
        aicha_ouedraogo = etudiants_groupe_a[0]

        for ine, nom, prenom in [
            ("20240201", "Sanou", "Abdoulaye"),
            ("20240202", "Congo", "Aminata"),
            ("20240203", "Kagambega", "Rasmané"),
            ("20240204", "Tapsoba", "Mariam"),
            ("20240205", "Ky", "Adama"),
            ("20240206", "Kologo", "Hawa"),
        ]:
            Etudiant.objects.create(ine=ine, nom=nom, prenom=prenom, filiere="Informatique", niveau="L2", annee_academique="2024-2025", groupe=groupe_td1, ufr_id=ufr_pilote)

        # Fraîchement importés, pas encore affectés à un groupe.
        for ine, nom, prenom in [
            ("20250301", "Ouédraogo", "Boukary"),
            ("20250302", "Sawadogo", "Aïda"),
            ("20250303", "Traoré", "Inoussa"),
            ("20250304", "Kaboré", "Ramata"),
        ]:
            Etudiant.objects.create(ine=ine, nom=nom, prenom=prenom, filiere="Électricité", niveau="L1", annee_academique="2025-2026", ufr_id=ufr_pilote)

        self.stdout.write("Autres UFR (données fictives pour observer le cloisonnement multi-UFR)...")

        # --- UFR-SVT ---
        ue_bio_cell = UniteEnseignement.objects.create(code="SVT101", intitule="Biologie Cellulaire", niveau="L1", ufr_id="ufr-svt")
        ue_geo_dyn = UniteEnseignement.objects.create(code="SVT102", intitule="Géodynamique Interne", niveau="L2", ufr_id="ufr-svt")
        amphi_svt = Salle.objects.create(nom="Amphi SVT 1", batiment="UFR/SVT", capacite=120, type_usage="propre", ufr_id="ufr-svt")
        groupe_svt_l1 = Groupe.objects.create(nom="L1 SVT - Groupe A", filiere="Biologie", niveau="L1", annee_academique="2025-2026", ufr_id="ufr-svt")
        groupe_svt_l2 = Groupe.objects.create(nom="L2 Géologie", filiere="Géologie", niveau="L2", annee_academique="2024-2025", ufr_id="ufr-svt")
        etudiants_svt_l1 = [
            Etudiant.objects.create(ine=ine, nom=nom, prenom=prenom, filiere="Biologie", niveau="L1", annee_academique="2025-2026", ufr_id="ufr-svt", groupe=groupe_svt_l1)
            for ine, nom, prenom in [("SVT-0001", "Barry", "Aminata"), ("SVT-0002", "Ouédraogo", "Karim"), ("SVT-0003", "Yaméogo", "Sarah")]
        ]
        for ine, nom, prenom in [("SVT-0004", "Kaboré", "Désiré"), ("SVT-0005", "Sanou", "Fatao")]:
            Etudiant.objects.create(ine=ine, nom=nom, prenom=prenom, filiere="Géologie", niveau="L2", annee_academique="2024-2025", ufr_id="ufr-svt", groupe=groupe_svt_l2)
        # FR-REF-06 : Kaboré Ismaël (déjà enseignant à l'UFR-SEA) intervient
        # AUSSI à l'UFR-SVT — même fiche Enseignant, une affectation de plus.
        EnseignantUfr.objects.create(enseignant=kabore, ufr_id="ufr-svt")
        ens_svt = Enseignant.objects.create(nom="Zongo", prenom="Alizèta")
        EnseignantUfr.objects.create(enseignant=ens_svt, ufr_id="ufr-svt")
        Creneau.objects.create(ue=ue_bio_cell, enseignant=ens_svt, groupe=groupe_svt_l1, salle=amphi_svt, jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")
        Creneau.objects.create(ue=ue_geo_dyn, enseignant=kabore, groupe=groupe_svt_l2, salle=amphi_svt, jour="mardi", heure_debut_minutes=10 * 60 + 15, heure_fin_minutes=12 * 60, statut="normal")

        # --- UFR-SH ---
        ue_socio_gen = UniteEnseignement.objects.create(code="SH101", intitule="Sociologie Générale", niveau="L2", ufr_id="ufr-sh")
        salle_sh = Salle.objects.create(nom="Salle 201", batiment="UFR/SH", capacite=60, type_usage="propre", ufr_id="ufr-sh")
        groupe_sh_l2 = Groupe.objects.create(nom="L2 Sociologie", filiere="Sociologie", niveau="L2", annee_academique="2024-2025", ufr_id="ufr-sh")
        for ine, nom, prenom in [("SH-0001", "Tapsoba", "Awa"), ("SH-0002", "Ouali", "Boureima"), ("SH-0003", "Nabaloum", "Clarisse")]:
            Etudiant.objects.create(ine=ine, nom=nom, prenom=prenom, filiere="Sociologie", niveau="L2", annee_academique="2024-2025", ufr_id="ufr-sh", groupe=groupe_sh_l2)
        ens_sh = Enseignant.objects.create(nom="Compaoré", prenom="Elie")
        EnseignantUfr.objects.create(enseignant=ens_sh, ufr_id="ufr-sh")
        Creneau.objects.create(ue=ue_socio_gen, enseignant=ens_sh, groupe=groupe_sh_l2, salle=salle_sh, jour="mercredi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")

        # --- UFR-SDS ---
        ue_anat = UniteEnseignement.objects.create(code="SDS101", intitule="Anatomie Générale", niveau="L1", ufr_id="ufr-sds")
        salle_sds = Salle.objects.create(nom="Amphi Santé", batiment="UFR/SDS", capacite=150, type_usage="propre", ufr_id="ufr-sds")
        groupe_sds_l1 = Groupe.objects.create(nom="L1 Médecine - Groupe A", filiere="Médecine", niveau="L1", annee_academique="2025-2026", ufr_id="ufr-sds")
        for ine, nom, prenom in [("SDS-0001", "Kientega", "Rahim"), ("SDS-0002", "Diallo", "Mariam")]:
            Etudiant.objects.create(ine=ine, nom=nom, prenom=prenom, filiere="Médecine", niveau="L1", annee_academique="2025-2026", ufr_id="ufr-sds", groupe=groupe_sds_l1)
        ens_sds = Enseignant.objects.create(nom="Ilboudo", prenom="Salimata")
        EnseignantUfr.objects.create(enseignant=ens_sds, ufr_id="ufr-sds")
        Creneau.objects.create(ue=ue_anat, enseignant=ens_sds, groupe=groupe_sds_l1, salle=salle_sds, jour="jeudi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")

        # --- UFR-LAC ---
        ue_lingu = UniteEnseignement.objects.create(code="LAC101", intitule="Linguistique Générale", niveau="L3", ufr_id="ufr-lac")
        salle_lac = Salle.objects.create(nom="Salle 105", batiment="UFR/LAC", capacite=50, type_usage="propre", ufr_id="ufr-lac")
        groupe_lac_l3 = Groupe.objects.create(nom="L3 Lettres Modernes", filiere="Lettres Modernes", niveau="L3", annee_academique="2023-2024", ufr_id="ufr-lac")
        for ine, nom, prenom in [("LAC-0001", "Sawadogo", "Nathalie"), ("LAC-0002", "Kabré", "Ousmane")]:
            Etudiant.objects.create(ine=ine, nom=nom, prenom=prenom, filiere="Lettres Modernes", niveau="L3", annee_academique="2023-2024", ufr_id="ufr-lac", groupe=groupe_lac_l3)
        ens_lac = Enseignant.objects.create(nom="Ouédraogo", prenom="Fatimata")
        EnseignantUfr.objects.create(enseignant=ens_lac, ufr_id="ufr-lac")
        Creneau.objects.create(ue=ue_lingu, enseignant=ens_lac, groupe=groupe_lac_l3, salle=salle_lac, jour="vendredi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")

        # --- Salle DEP (transversale) ---
        Salle.objects.create(nom="Grand Amphithéâtre Central", batiment="Bâtiment Administratif", capacite=800, type_usage="commune", structure_gestionnaire=StructureGestionnaire.DEP, ufr=None)

        self.stdout.write('Comptes de connexion (password: "password")...')
        Utilisateur.objects.create(identifiant="20230145", mot_de_passe_hash=mot_de_passe_hash, nom=aicha_ouedraogo.nom, prenom=aicha_ouedraogo.prenom, role=Role.ETUDIANT, etudiant=aicha_ouedraogo)
        Utilisateur.objects.create(identifiant="kabore.enseignant", mot_de_passe_hash=mot_de_passe_hash, nom=kabore.nom, prenom=kabore.prenom, role=Role.ENSEIGNANT, enseignant=kabore)
        # Étudiante de l'UFR-SVT — pour observer l'espace étudiant sur une
        # UFR autre que la pilote (SEA).
        Utilisateur.objects.create(identifiant="SVT-0001", mot_de_passe_hash=mot_de_passe_hash, nom=etudiants_svt_l1[0].nom, prenom=etudiants_svt_l1[0].prenom, role=Role.ETUDIANT, etudiant=etudiants_svt_l1[0])
        # V2 multi-UFR : l'ancien compte unique "scolarite.info" (MVP) se
        # scinde en un Admin central et un Gestionnaire par UFR. "Savadogo
        # Rasmata" (identité utilisée comme "auteur" plus bas) devient le
        # Gestionnaire de l'UFR-SEA, pas l'Admin.
        Utilisateur.objects.create(identifiant="scolarite.general", mot_de_passe_hash=mot_de_passe_hash, nom="Zerbo", prenom="Idrissa", role=Role.ADMIN)
        Utilisateur.objects.create(identifiant="scolarite.sh", mot_de_passe_hash=mot_de_passe_hash, nom="UFR Sciences Humaines", prenom="Scolarité", role=Role.SCOLARITE, ufr_id="ufr-sh")
        Utilisateur.objects.create(identifiant="scolarite.sds", mot_de_passe_hash=mot_de_passe_hash, nom="UFR Sciences de la Santé", prenom="Scolarité", role=Role.SCOLARITE, ufr_id="ufr-sds")
        Utilisateur.objects.create(identifiant="scolarite.svt", mot_de_passe_hash=mot_de_passe_hash, nom="UFR Sciences de la Vie et de la Terre", prenom="Scolarité", role=Role.SCOLARITE, ufr_id="ufr-svt")
        Utilisateur.objects.create(identifiant="scolarite.sea", mot_de_passe_hash=mot_de_passe_hash, nom="Savadogo", prenom="Rasmata", role=Role.SCOLARITE, ufr_id="ufr-sea")
        Utilisateur.objects.create(identifiant="scolarite.lac", mot_de_passe_hash=mot_de_passe_hash, nom="UFR Lettres Arts et Communication", prenom="Scolarité", role=Role.SCOLARITE, ufr_id="ufr-lac")

        self.stdout.write("Créneaux (un seul jeu de données réconcilié)...")
        c1 = Creneau.objects.create(ue=ue_algo, enseignant=kabore, groupe=groupe_a, salle=amphi_a, jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal")

        # Scindé autour de la pause de 10h00-10h15.
        Creneau.objects.create(ue=ue_bdd, enseignant=traore, groupe=groupe_a, salle=salle_402, jour="mardi", heure_debut_minutes=9 * 60, heure_fin_minutes=10 * 60, statut="modifie", motif="Changement de salle demandé par l'enseignant")
        Creneau.objects.create(ue=ue_bdd, enseignant=traore, groupe=groupe_a, salle=salle_402, jour="mardi", heure_debut_minutes=10 * 60 + 15, heure_fin_minutes=12 * 60, statut="modifie", motif="Changement de salle demandé par l'enseignant")

        Creneau.objects.create(ue=ue_reseaux, enseignant=sawadogo, groupe=groupe_a, salle=salle_102, jour="mercredi", heure_debut_minutes=7 * 60, heure_fin_minutes=9 * 60, statut="annule", motif="Absence enseignant")

        # FR-CONF-01 : même salle (Amphi A), même horaire (lundi 08h-10h) que
        # c1, mais un groupe différent — conflit de salle authentique.
        # "derogation_motif" est obligatoire pour que cette ligne puisse
        # physiquement coexister avec c1 (contrainte EXCLUDE).
        derogation_salle = "Amphi A exceptionnellement partagé le temps du semestre (accord DEP)"
        c_conflit_salle = Creneau.objects.create(ue=ue_prog_c, enseignant=traore, groupe=groupe_td1, salle=amphi_a, jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60, statut="normal", derogation_motif=derogation_salle)
        AuditEntry.objects.create(auteur="Savadogo Rasmata", action="Création créneau — Programmation C (dérogation conflit: salle)", motif=derogation_salle, creneau_id=c_conflit_salle.id)
        # Trace du conflit lui-même — donne au dashboard un vrai
        # "conflitsDetectes" à compter dès le premier chargement.
        ConflitJournal.objects.create(
            type="salle", gravite="bloquant", titre="Double réservation — Amphi A",
            description="Algorithmique Avancée et Programmation C sur le même créneau (lundi 08:00-10:00).",
            creneau_a_id=c_conflit_salle.id, creneau_b_id=c1.id, derogation_motif=derogation_salle, detecte_par="Savadogo Rasmata",
        )

        # FR-CONF-04 : Groupe A compte réellement 8 étudiants — la Salle 6
        # (6 places) déclenche un vrai avertissement de capacité.
        Creneau.objects.create(ue=ue_bdd, enseignant=sawadogo, groupe=groupe_a, salle=salle_6, jour="jeudi", heure_debut_minutes=10 * 60 + 15, heure_fin_minutes=12 * 60, statut="normal")

        self.stdout.write("Demande enseignant (report, en attente)...")
        DemandeEnseignant.objects.create(
            enseignant=kabore, type="report", statut="en_attente", creneau_concerne_id=c1.id, motif="Conférence internationale",
            jour_propose="jeudi", heure_debut_proposee_minutes=8 * 60, heure_fin_proposee_minutes=10 * 60, salle_proposee_id=amphi_a.id,
        )

        self.stdout.write('\nTerminé. Comptes de démonstration (mot de passe : "password") :')
        self.stdout.write("  Étudiant (UFR-SEA) 20230145")
        self.stdout.write("  Étudiant (UFR-SVT) SVT-0001")
        self.stdout.write("  Enseignant         kabore.enseignant  (intervient à la fois en UFR-SEA et UFR-SVT, FR-REF-06)")
        self.stdout.write("  Admin              scolarite.general")
        self.stdout.write("  Gestionnaire (SEA) scolarite.sea  (données pilotes Informatique)")
        self.stdout.write("  Gestionnaire (SVT) scolarite.svt  (Biologie/Géologie)")
        self.stdout.write("  Gestionnaire (SH)  scolarite.sh   (Sociologie)")
        self.stdout.write("  Gestionnaire (SDS) scolarite.sds  (Médecine)")
        self.stdout.write("  Gestionnaire (LAC) scolarite.lac  (Lettres Modernes)")
