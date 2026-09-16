"""[V3.2] Établissements et départements officiels de l'UJKZ.

Le référentiel officiel transmis le 2026-09-07 recense 12 établissements
(5 UFR, 6 instituts, 1 école doctorale) et 53 départements. La V2 avait
délibérément restreint le périmètre aux 5 UFR ; ces tests vérifient que la
restriction est bien levée et que le cloisonnement INT-07, lui, ne l'est
pas.
"""

import json

from django.test import Client, TestCase

from accounts.models import Role
from core.donnees_ujkz import ARBITRAGES, ETABLISSEMENTS, ORTHOGRAPHE_SOURCE
from core.models import TypeEtablissement, Ufr
from referentiel.models import Departement
from tests.base import creer_compte, creer_ufr, login, post_json, ufr_par_defaut


class DonneesOfficiellesTests(TestCase):
    """Le fichier de référence lui-même — il n'est chargé que par le seed,
    donc rien d'autre ne le vérifierait."""

    def test_douze_etablissements_dont_cinq_ufr(self):
        self.assertEqual(len(ETABLISSEMENTS), 12)
        types = [e[2] for e in ETABLISSEMENTS]
        self.assertEqual(types.count(TypeEtablissement.UFR), 5)
        self.assertEqual(types.count(TypeEtablissement.INSTITUT), 6)
        self.assertEqual(types.count(TypeEtablissement.ECOLE_DOCTORALE), 1)

    def test_cinquante_trois_departements(self):
        self.assertEqual(sum(len(e[3]) for e in ETABLISSEMENTS), 53)

    def test_sigles_uniques_et_utilisables_comme_identifiant_de_compte(self):
        """Le sigle sert à `scolarite.<sigle>` et à `ufr-<sigle>` : un
        doublon ou un caractère exotique casserait les deux."""
        sigles = [e[0] for e in ETABLISSEMENTS]
        self.assertEqual(len(sigles), len(set(sigles)))
        for sigle in sigles:
            self.assertTrue(sigle.isalpha() and sigle.islower(), sigle)
            self.assertLessEqual(len(sigle), 10, sigle)

    def test_aucun_departement_en_double_dans_un_meme_etablissement(self):
        for sigle, _, _, departements in ETABLISSEMENTS:
            minuscules = [d.lower() for d in departements]
            self.assertEqual(len(minuscules), len(set(minuscules)), sigle)

    def test_les_departements_proches_restent_distincts(self):
        """Arbitrage de la scolarité du 2026-09-07 : « Philosophie
        -Psychologie » / « Pshychologie » et « Médecine et Spécialités
        médicales » / « Medecine » sont des départements à part entière,
        aux contenus différents — PAS des doublons.

        Ce test est un garde-fou contre une future « correction » de bonne
        foi : quiconque fusionnerait ces paires en les prenant pour des
        doublons casserait le référentiel officiel de deux établissements,
        et le verrait ici avant de le livrer.
        """
        par_sigle = {sigle: deps for sigle, _, _, deps in ETABLISSEMENTS}
        for sigle, paire, motif in ARBITRAGES:
            for libelle in paire:
                self.assertIn(libelle, par_sigle[sigle], f"{libelle} — {motif}")

    def test_l_orthographe_de_la_source_est_reprise_verbatim(self):
        """Les intitulés viennent du responsable de la scolarité : lui seul
        fait foi. Les « corriger » ferait diverger le référentiel de son
        document officiel, sans que personne ne s'en aperçoive."""
        par_sigle = {sigle: deps for sigle, _, _, deps in ETABLISSEMENTS}
        for sigle, libelle in ORTHOGRAPHE_SOURCE:
            self.assertIn(libelle, par_sigle[sigle])


class SigleAfficheTests(TestCase):
    def test_prefixe_ufr_uniquement_pour_les_ufr(self):
        """Les UFR de l'UJKZ se désignent « UFR/SH » dans les documents
        officiels, jamais les instituts."""
        ufr = Ufr.objects.create(id="ufr-sh", nom="UFR SH", sigle="sh", type=TypeEtablissement.UFR)
        institut = Ufr.objects.create(id="ufr-ibam", nom="IBAM", sigle="ibam", type=TypeEtablissement.INSTITUT)
        ecole = Ufr.objects.create(id="ufr-edicc", nom="EDICC", sigle="edicc", type=TypeEtablissement.ECOLE_DOCTORALE)

        self.assertEqual(ufr.sigle_affiche, "UFR/SH")
        self.assertEqual(institut.sigle_affiche, "IBAM")
        self.assertEqual(ecole.sigle_affiche, "EDICC")


class DepartementsApiTests(TestCase):
    def setUp(self):
        ufr_par_defaut()
        creer_ufr("ufr-b", "Institut B", "b")
        Departement.objects.create(ufr_id="ufr-test", libelle="Informatique")
        Departement.objects.create(ufr_id="ufr-test", libelle="Mathématique")
        Departement.objects.create(ufr_id="ufr-b", libelle="Démographie")

        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        creer_compte("scolarite.general", "Zerbo", "Idrissa", Role.ADMIN)
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")
        self.client_admin = Client()
        login(self.client_admin, "scolarite.general")

    def test_un_gestionnaire_ne_voit_que_ses_propres_departements(self):
        """INT-07 : élargir le périmètre aux instituts n'a rien assoupli."""
        libelles = [d["libelle"] for d in self.client_sco.get("/api/departements").json()["departements"]]
        self.assertEqual(libelles, ["Informatique", "Mathématique"])
        self.assertNotIn("Démographie", libelles)

    def test_l_admin_voit_tous_les_departements(self):
        """FR-ADMIN-03."""
        libelles = [d["libelle"] for d in self.client_admin.get("/api/departements").json()["departements"]]
        self.assertEqual(len(libelles), 3)

    def test_ouvrir_un_nouveau_departement(self):
        """FR-REF-21 : sans cette porte, un Gestionnaire dont la filière
        vient d'être créée serait bloqué jusqu'à une mise à jour du seed."""
        res = post_json(self.client_sco, "/api/departements", {"libelle": "Chimie"})
        self.assertEqual(res.status_code, 201)
        self.assertTrue(Departement.objects.filter(ufr_id="ufr-test", libelle="Chimie").exists())

    def test_le_nouveau_departement_est_toujours_dans_l_etablissement_de_la_session(self):
        """L'ufr_id ne vient jamais de la requête (INT-07)."""
        post_json(self.client_sco, "/api/departements", {"libelle": "Physique", "ufrId": "ufr-b"})
        self.assertTrue(Departement.objects.filter(ufr_id="ufr-test", libelle="Physique").exists())
        self.assertFalse(Departement.objects.filter(ufr_id="ufr-b", libelle="Physique").exists())

    def test_doublon_insensible_a_la_casse(self):
        """C'est exactement le doublon que ce modèle existe pour empêcher :
        « Informatique » et « informatique » deviendraient deux filières
        distinctes dans la cascade publique (FR-PUB-02)."""
        res = post_json(self.client_sco, "/api/departements", {"libelle": "informatique"})
        self.assertEqual(res.status_code, 409)

    def test_le_meme_libelle_est_permis_dans_deux_etablissements(self):
        """« Informatique » existe réellement à l'UFR/SEA et à l'IBAM."""
        Departement.objects.create(ufr_id="ufr-b", libelle="Informatique")
        self.assertEqual(Departement.objects.filter(libelle="Informatique").count(), 2)

    def test_libelle_vide_refuse(self):
        self.assertEqual(post_json(self.client_sco, "/api/departements", {"libelle": "   "}).status_code, 400)

    def test_un_admin_cree_un_departement_avec_ufr_id_explicite(self):
        """[V7] Exception ciblée à INV-11 : retour des gestionnaires, l'Admin
        doit pouvoir créer un département si le Gestionnaire de l'UFR n'est
        pas disponible — mais seulement en désignant l'UFR explicitement,
        l'Admin n'en ayant aucune en session."""
        res = post_json(self.client_admin, "/api/departements", {"libelle": "Chimie", "ufrId": "ufr-b"})
        self.assertEqual(res.status_code, 201)
        self.assertTrue(Departement.objects.filter(ufr_id="ufr-b", libelle="Chimie").exists())

    def test_un_admin_sans_ufr_id_est_refuse(self):
        """L'ufrId ne peut pas être omis pour un Admin : il n'a pas d'UFR de
        session vers laquelle se replier."""
        self.assertEqual(post_json(self.client_admin, "/api/departements", {"libelle": "X"}).status_code, 400)

    def test_un_anonyme_ne_lit_pas_les_departements(self):
        """INT-10 : le référentiel de gestion reste fermé. La cascade
        publique, elle, ne propose que les filières qui ont réellement un
        groupe (public/services.py), pas ce référentiel."""
        self.assertEqual(Client().get("/api/departements").status_code, 401)


class CreationEtablissementTests(TestCase):
    def setUp(self):
        creer_compte("scolarite.general", "Zerbo", "Idrissa", Role.ADMIN)
        self.client_admin = Client()
        login(self.client_admin, "scolarite.general")

    def test_admin_cree_un_institut(self):
        """[V3.2] Ce que la V2 interdisait : le périmètre n'est plus limité
        aux UFR."""
        res = post_json(self.client_admin, "/api/ufrs", {"nom": "Institut Test", "sigle": "itest", "type": "institut"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["ufr"]["type"], "institut")
        self.assertEqual(res.json()["ufr"]["sigleAffiche"], "ITEST")

    def test_le_type_par_defaut_reste_ufr(self):
        """Rétrocompatibilité : un appel qui ne précise pas le type — comme
        le faisait tout le frontend avant la V3.2 — crée une UFR."""
        res = post_json(self.client_admin, "/api/ufrs", {"nom": "UFR Test", "sigle": "utest"})
        self.assertEqual(res.json()["ufr"]["type"], "ufr")
        self.assertEqual(res.json()["ufr"]["sigleAffiche"], "UFR/UTEST")

    def test_type_inconnu_refuse(self):
        res = post_json(self.client_admin, "/api/ufrs", {"nom": "X", "sigle": "xx", "type": "faculte"})
        self.assertEqual(res.status_code, 400)


class CoherenceSeedTests(TestCase):
    """[V3.3] La filière d'un groupe doit être un département officiel.

    Quatre groupes du seed portaient une filière absente du référentiel
    (« Biologie » au lieu de « Biochimie et microbiologie », « Médecine »
    accentué au lieu de « Medecine »...). Elles apparaissaient dans la
    recherche publique **à côté** du département officiel, donnant à voir
    deux entrées quasi identiques — exactement ce qu'un visiteur interprète
    comme un doublon, alors que la cause était une incohérence du seed.

    Ce test relit le seed lui-même : c'est le seul endroit où l'écart peut
    être attrapé, la base ne contraignant pas `Groupe.departement` (chaîne
    dénormalisée volontaire, cf. referentiel/models.py).
    """

    def test_tout_departement_de_groupe_est_officiel(self):
        from io import StringIO

        from django.core.management import call_command

        from referentiel.models import Departement, Groupe

        call_command("seed", stdout=StringIO())

        officiels = {(d.ufr_id, d.libelle) for d in Departement.objects.all()}
        ecarts = [
            f"{g.nom} ({g.ufr_id}) → département {g.departement!r} absent du référentiel"
            for g in Groupe.objects.all()
            if (g.ufr_id, g.departement) not in officiels
        ]
        self.assertEqual(ecarts, [], "\n".join(ecarts))


class CoursDepartementsTests(TestCase):
    """[V3.3] Un cours est rattaché à un ou plusieurs départements.

    Le cas « plusieurs » est le seul qui justifie la relation multiple : un
    tronc commun dispensé à quatre départements devrait sinon être ressaisi
    quatre fois, et la question « quels départements suivent ce cours ? »
    resterait sans réponse.
    """

    def setUp(self):
        ufr_par_defaut()
        creer_ufr("ufr-b", "Institut B", "b")
        self.info = Departement.objects.create(ufr_id="ufr-test", libelle="Informatique")
        self.physique = Departement.objects.create(ufr_id="ufr-test", libelle="Physique")
        self.chez_b = Departement.objects.create(ufr_id="ufr-b", libelle="Démographie")

        creer_compte("scolarite.test", "Savadogo", "Rasmata", Role.SCOLARITE)
        self.client_sco = Client()
        login(self.client_sco, "scolarite.test")

    def test_cree_un_cours_mutualise(self):
        res = post_json(
            self.client_sco,
            "/api/cours",
            {"intitule": "Mathématiques", "departementIds": [self.info.id, self.physique.id]},
        )
        self.assertEqual(res.status_code, 201)
        libelles = sorted(d["libelle"] for d in res.json()["ue"]["departements"])
        self.assertEqual(libelles, ["Informatique", "Physique"])

    def test_un_cours_sans_departement_reste_possible(self):
        """Comme l'effectif à zéro : accepté, mais l'écran le signale. Refuser
        bloquerait la saisie d'un cours dont le rattachement n'est pas encore
        arbitré."""
        res = post_json(self.client_sco, "/api/cours", {"intitule": "Cours orphelin"})
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()["ue"]["departements"], [])

    def test_impossible_de_rattacher_un_departement_d_un_autre_etablissement(self):
        """INT-07 : les identifiants viennent du client, les valider côté
        serveur est le seul garde-fou."""
        res = post_json(
            self.client_sco,
            "/api/cours",
            {"intitule": "Cours hors périmètre", "departementIds": [self.chez_b.id]},
        )
        self.assertEqual(res.status_code, 400)

    def test_rattacher_un_cours_existant(self):
        """Les cours créés avant la V3.3 n'ont aucun département : sans route
        de modification, il faudrait les supprimer — ce que le référentiel
        interdit dès qu'un créneau les référence."""
        cree = post_json(self.client_sco, "/api/cours", {"intitule": "Ancien cours"}).json()["ue"]
        res = self.client_sco.patch(
            f"/api/cours/{cree['id']}",
            data=json.dumps({"departementIds": [self.info.id]}),
            content_type="application/json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual([d["libelle"] for d in res.json()["ue"]["departements"]], ["Informatique"])

    def test_le_rattachement_remplace_et_n_ajoute_pas(self):
        """`set()` et non `add()` : décocher un département dans l'interface
        doit réellement le retirer."""
        cree = post_json(
            self.client_sco,
            "/api/cours",
            {"intitule": "Cours évolutif", "departementIds": [self.info.id, self.physique.id]},
        ).json()["ue"]
        res = self.client_sco.patch(
            f"/api/cours/{cree['id']}",
            data=json.dumps({"departementIds": [self.info.id]}),
            content_type="application/json",
        )
        self.assertEqual([d["libelle"] for d in res.json()["ue"]["departements"]], ["Informatique"])
