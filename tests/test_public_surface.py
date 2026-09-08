"""[V3] La surface publique — les tests les plus importants de cette version.

Une erreur de périmètre n'expose plus une donnée au mauvais utilisateur
connecté : elle l'expose à Internet. Ces tests couvrent donc autant ce que
la surface publique DOIT montrer que ce qu'elle ne doit jamais laisser
passer (INV-05, INV-12, INT-10, NFR-SEC-03).
"""

import json

from django.test import Client, TestCase

from planning.models import Creneau, SeanceAnnulee
from tests.base import (
    creer_enseignant,
    creer_groupe,
    creer_salle,
    creer_ue,
    creer_ufr,
    prochain,
    ufr_par_defaut,
)


class SurfacePubliqueTests(TestCase):
    def setUp(self):
        ufr_par_defaut()
        creer_ufr("ufr-vide", "UFR Sans Groupe", "vide")
        self.ue = creer_ue("Réseaux Informatiques", code="INFO303")
        self.salle = creer_salle("Amphi A", 1000)
        self.groupe = creer_groupe("L3 INFO - Groupe A", filiere="Informatique", niveau="L3", effectif=40)
        self.autre = creer_groupe("L2 INFO - Groupe B", filiere="Informatique", niveau="L2")
        self.enseignant = creer_enseignant("Kaboré", "Ismaël")

        self.creneau = Creneau.objects.create(
            ue=self.ue, enseignant=self.enseignant, groupe=self.groupe, salle=self.salle,
            jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60,
        )
        self.anonyme = Client()

    # --- FR-PUB-01/02 : accès et cascade -----------------------------------

    def test_le_programme_est_lisible_sans_aucune_authentification(self):
        res = self.anonyme.get(f"/api/public/programme/{self.groupe.id}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["seances"]), 1)

    def test_la_cascade_ne_propose_que_des_valeurs_qui_menent_a_un_programme(self):
        """FR-PUB-02 : une UFR sans aucun groupe n'apparaît pas — un visiteur
        ne doit pas pouvoir s'engager dans un chemin qui ne mène nulle part."""
        sigles = [u["sigle"] for u in self.anonyme.get("/api/public/ufrs").json()["ufrs"]]
        self.assertIn("test", sigles)
        self.assertNotIn("vide", sigles)

    def test_la_cascade_se_resserre_a_chaque_etage(self):
        ufr = ufr_par_defaut()
        filieres = self.anonyme.get(f"/api/public/filieres?ufrId={ufr}").json()["filieres"]
        self.assertEqual(filieres, ["Informatique"])

        niveaux = self.anonyme.get(f"/api/public/niveaux?ufrId={ufr}&filiere=Informatique").json()["niveaux"]
        self.assertEqual(niveaux, ["L2", "L3"])

        groupes = self.anonyme.get(
            f"/api/public/groupes?ufrId={ufr}&filiere=Informatique&niveau=L3"
        ).json()["groupes"]
        self.assertEqual([g["id"] for g in groupes], [self.groupe.id])

    def test_ufr_plus_niveau_ne_suffisent_pas_a_designer_un_programme(self):
        """RM-09 : justification de la cascade à 4 étages. Deux filières au
        même niveau donnent deux programmes distincts — c'est la raison pour
        laquelle « UFR + niveau », proposé au départ, a été écarté."""
        creer_groupe("L3 MATHS - Groupe A", filiere="Mathématiques", niveau="L3")
        ufr = ufr_par_defaut()
        info = self.anonyme.get(f"/api/public/groupes?ufrId={ufr}&filiere=Informatique&niveau=L3").json()
        maths = self.anonyme.get(f"/api/public/groupes?ufrId={ufr}&filiere=Mathématiques&niveau=L3").json()
        self.assertEqual(len(info["groupes"]), 1)
        self.assertEqual(len(maths["groupes"]), 1)
        self.assertNotEqual(info["groupes"][0]["id"], maths["groupes"][0]["id"])

    # --- INV-12 / INT-10 / NFR-SEC-03 : ce qui ne doit JAMAIS sortir --------

    def test_aucune_donnee_nominative_d_etudiant_dans_le_programme_public(self):
        """INV-12/NFR-SEC-03 : un programme public ne doit pas devenir un
        annuaire d'étudiants consultable par n'importe qui."""
        brut = self.anonyme.get(f"/api/public/programme/{self.groupe.id}").content.decode()
        # [V3.1] Le référentiel nominatif des étudiants n'existe plus, mais
        # l'effectif du groupe subsiste (valeur saisie) : il ne doit pas
        # sortir pour autant — c'est une donnée de gestion, pas une
        # information d'emploi du temps (INV-12).
        self.assertNotIn("effectif", brut)

        seance = json.loads(brut)["seances"][0]
        self.assertEqual(
            sorted(seance.keys()),
            ["date", "enseignant", "heureDebut", "heureFin", "id", "jour", "motif", "salle", "statut", "ue"],
        )

    def test_les_referentiels_restent_fermes_aux_appels_anonymes(self):
        """INT-10 : ouvrir le programme n'ouvre rien d'autre."""
        for route in ["/api/groupes", "/api/enseignants", "/api/salles", "/api/cours", "/api/audit"]:
            self.assertEqual(self.anonyme.get(route).status_code, 401, route)

    def test_aucune_ecriture_possible_sur_la_surface_publique(self):
        """INV-05 : la surface publique n'expose aucune méthode d'écriture,
        hors l'abonnement aux alertes qui n'écrit que sa propre table."""
        res = self.anonyme.post(f"/api/public/programme/{self.groupe.id}", data="{}", content_type="application/json")
        self.assertEqual(res.status_code, 405)

    # --- FR-PUB-07 / INV-15 : une annulation reste visible ------------------

    def test_une_seance_annulee_reste_visible_et_signalee(self):
        """INV-15 : la faire disparaître priverait l'étudiant de
        l'information même qu'on cherche à lui transmettre."""
        date = prochain("lundi")
        SeanceAnnulee.objects.create(creneau=self.creneau, date=date, motif="Absence enseignant", annule_par="Test")

        res = self.anonyme.get(f"/api/public/programme/{self.groupe.id}?semaine={date.isoformat()}")
        seances = res.json()["seances"]
        self.assertEqual(len(seances), 1)
        self.assertEqual(seances[0]["statut"], "annule_seance")
        self.assertEqual(seances[0]["motif"], "Absence enseignant")

    def test_l_annulation_ne_vaut_que_pour_sa_date(self):
        """INV-14 : la semaine suivante, le cours a de nouveau lieu."""
        date = prochain("lundi")
        SeanceAnnulee.objects.create(creneau=self.creneau, date=date, motif="Absence", annule_par="Test")

        import datetime

        suivante = date + datetime.timedelta(days=7)
        res = self.anonyme.get(f"/api/public/programme/{self.groupe.id}?semaine={suivante.isoformat()}")
        self.assertEqual(res.json()["seances"][0]["statut"], "normal")

    # --- ERR-07 / ERR-08 ----------------------------------------------------

    def test_groupe_supprime_message_explicite(self):
        """ERR-08 : le favori d'un visiteur pointe vers un groupe disparu."""
        res = self.anonyme.get("/api/public/programme/nexistepas")
        self.assertEqual(res.status_code, 404)
        self.assertIn("Refaites une recherche", res.json()["erreur"])

    def test_programme_vide_et_combinaison_inexistante_ne_se_ressemblent_pas(self):
        """ERR-07 : un groupe sans créneau répond 200 avec zéro séance ; une
        combinaison qui ne désigne rien répond une liste de groupes vide."""
        vide = self.anonyme.get(f"/api/public/programme/{self.autre.id}")
        self.assertEqual(vide.status_code, 200)
        self.assertEqual(vide.json()["seances"], [])

        inexistant = self.anonyme.get(
            f"/api/public/groupes?ufrId={ufr_par_defaut()}&filiere=Inexistante&niveau=L3"
        )
        self.assertEqual(inexistant.status_code, 200)
        self.assertEqual(inexistant.json()["groupes"], [])


class SurfacePubliqueEtablissementsTests(TestCase):
    """[V3.2] Le sigle affiché sur la surface publique.

    C'est la première chose que lit un visiteur, à l'étape 1 de la cascade.
    Ces champs ont été oubliés lors de l'ajout du type d'établissement — la
    surface publique construisant ses propres représentations (INV-12), elle
    ne suit pas automatiquement le sérialiseur de gestion. C'est le prix,
    assumé, de la séparation : ces tests sont ce qui le rend supportable.
    """

    def setUp(self):
        from core.models import TypeEtablissement, Ufr
        from tests.base import PERIODE_TEST

        Ufr.objects.create(
            id="ufr-ibam", nom="Institut Burkinabè des Arts et Métiers", sigle="ibam",
            type=TypeEtablissement.INSTITUT, **PERIODE_TEST,
        )
        self.groupe_institut = creer_groupe("L1 Gestion - Groupe A", filiere="Gestion", niveau="L1", ufr_id="ufr-ibam")
        Creneau.objects.create(
            ue=creer_ue("Comptabilité", code="IBAM101", ufr_id="ufr-ibam"),
            enseignant=creer_enseignant("Sanou", "Adama", ufr_id="ufr-ibam"),
            groupe=self.groupe_institut,
            salle=creer_salle("Salle IBAM", 80, ufr_id="ufr-ibam"),
            jour="lundi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60,
        )
        # Une UFR avec un groupe, pour comparer les deux formes de sigle
        # dans la même réponse — la cascade ne liste que les établissements
        # qui mènent réellement à un programme (FR-PUB-02).
        groupe_ufr = creer_groupe("L1 Info - Groupe A", filiere="Informatique", niveau="L1")
        Creneau.objects.create(
            ue=creer_ue("Algorithmique", code="TEST101"),
            enseignant=creer_enseignant("Kaboré", "Ismaël"),
            groupe=groupe_ufr,
            salle=creer_salle("Salle Test", 80),
            jour="mardi", heure_debut_minutes=8 * 60, heure_fin_minutes=10 * 60,
        )
        self.anonyme = Client()

    def test_un_institut_apparait_dans_la_cascade_publique(self):
        """[V3.2] Ce que la V2 rendait impossible : le périmètre n'est plus
        limité aux 5 UFR."""
        sigles = [u["sigle"] for u in self.anonyme.get("/api/public/ufrs").json()["ufrs"]]
        self.assertIn("ibam", sigles)

    def test_le_sigle_affiche_distingue_institut_et_ufr(self):
        ufrs = {u["sigle"]: u for u in self.anonyme.get("/api/public/ufrs").json()["ufrs"]}
        self.assertEqual(ufrs["ibam"]["sigleAffiche"], "IBAM")
        self.assertEqual(ufrs["test"]["sigleAffiche"], "UFR/TEST")

    def test_le_programme_public_porte_le_sigle_affiche(self):
        """Lu tel quel par la page programme : un `sigle` brut y afficherait
        « ibam » en minuscules."""
        res = self.anonyme.get(f"/api/public/programme/{self.groupe_institut.id}")
        self.assertEqual(res.json()["groupe"]["ufr"]["sigleAffiche"], "IBAM")

    def test_le_calendrier_porte_le_sigle_affiche(self):
        """Ce nom reste dans l'agenda du visiteur pour toute l'année."""
        ics = self.anonyme.get(f"/api/public/calendrier/{self.groupe_institut.id}.ics").content.decode()
        self.assertIn("X-WR-CALNAME:L1 Gestion - Groupe A — IBAM", ics)
