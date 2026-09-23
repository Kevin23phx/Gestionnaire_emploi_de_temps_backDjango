"""[V8, 2026-09-21] Réforme « Niveau / Spécialité ».

Le champ que l'écran intitulait « Parcours » contenait en réalité des
NIVEAUX du cycle LMD. La réforme sépare les deux : le niveau reste la liste
close du LMD, la spécialité devient une entrée de référentiel rattachée à un
COUPLE (département, niveau).

Ce que ces tests protègent, par ordre d'importance :

1. **Le rattachement au couple**, pas au département seul — c'est le cas
   MPCI (tronc commun en L1, quatre choix en L2), et la raison d'être de la
   réforme. Un test qui ne vérifierait que « le département a des
   spécialités » laisserait passer une régression qui les ferait apparaître
   dès la L1.
2. **Le cloisonnement INT-07**, qui a ici une forme nouvelle : `Specialite`
   n'a pas de FK vers `Ufr` (elle en hérite par son département), donc rien
   dans le modèle ne l'empêche mécaniquement de pointer un département
   d'une autre UFR. C'est le service qui le refuse, et c'est le seul point
   de cette réforme où le cloisonnement pourrait se contourner.
3. **INV-21** : le référentiel bouge, les groupes déjà saisis ne bougent
   pas.
"""

import json

from django.test import Client, TestCase

from accounts.models import Role
from referentiel.models import Departement, Groupe, Specialite
from tests.base import creer_compte, creer_groupe, creer_ufr, login, post_json, ufr_par_defaut


def creer_departement(libelle: str, ufr_id: str | None = None) -> Departement:
    return Departement.objects.create(libelle=libelle, ufr_id=ufr_id or ufr_par_defaut())


class SpecialitesReferentielTests(TestCase):
    def setUp(self):
        self.ufr = ufr_par_defaut()
        creer_compte("scolarite.test", "Ouedraogo", "Awa", Role.SCOLARITE, ufr_id=self.ufr)
        self.client = Client()
        login(self.client, "scolarite.test")
        self.mpci = creer_departement("MPCI")

    def test_creation_rattachee_a_un_departement_et_un_niveau(self):
        reponse = post_json(
            self.client, "/api/specialites", {"libelle": "Informatique", "departementId": self.mpci.id, "niveau": "L2"}
        )
        self.assertEqual(reponse.status_code, 201)
        corps = reponse.json()["specialites"][0]
        self.assertEqual(corps["libelle"], "Informatique")
        self.assertEqual(corps["niveau"], "L2")
        self.assertEqual(corps["departement"], "MPCI")
        self.assertEqual(corps["ufrId"], self.ufr)

    def test_le_niveau_fait_partie_de_l_identite_de_la_specialite(self):
        """LE test de la réforme. « Informatique » en L2 et « Informatique »
        en L3 sont deux choix distincts, offerts à deux cohortes
        distinctes : la contrainte d'unicité ne doit PAS les confondre
        (INV-20). Si elle portait sur le seul département, le second appel
        renverrait 409 et la L3 serait impossible à déclarer."""
        for niveau in ("L2", "L3"):
            reponse = post_json(
                self.client,
                "/api/specialites",
                {"libelle": "Informatique", "departementId": self.mpci.id, "niveau": niveau},
            )
            self.assertEqual(reponse.status_code, 201, niveau)
        self.assertEqual(Specialite.objects.filter(libelle="Informatique").count(), 2)

    def test_doublon_refuse_dans_le_meme_couple_meme_a_la_casse_pres(self):
        post_json(self.client, "/api/specialites", {"libelle": "Chimie", "departementId": self.mpci.id, "niveau": "L2"})
        reponse = post_json(
            self.client, "/api/specialites", {"libelle": "chimie", "departementId": self.mpci.id, "niveau": "L2"}
        )
        self.assertEqual(reponse.status_code, 409)

    def test_niveau_hors_cycle_lmd_refuse(self):
        """Une spécialité en « L4 » serait introuvable par la cascade
        publique, qui n'interroge que des niveaux du LMD : autant la refuser
        à l'écriture plutôt que de laisser une ligne inatteignable en base."""
        reponse = post_json(
            self.client, "/api/specialites", {"libelle": "Astrophysique", "departementId": self.mpci.id, "niveau": "L4"}
        )
        self.assertEqual(reponse.status_code, 400)

    def test_filtrage_par_couple_departement_niveau(self):
        for niveau, libelle in (("L2", "Physique"), ("L2", "Chimie"), ("L3", "Informatique")):
            post_json(
                self.client, "/api/specialites", {"libelle": libelle, "departementId": self.mpci.id, "niveau": niveau}
            )
        reponse = self.client.get(f"/api/specialites?departementId={self.mpci.id}&niveau=L2")
        libelles = [s["libelle"] for s in reponse.json()["specialites"]]
        self.assertEqual(sorted(libelles), ["Chimie", "Physique"])

    def test_suppression_ne_touche_pas_les_groupes_qui_la_portent(self):
        """INV-21 : supprimer une entrée de référentiel ne réécrit jamais
        l'historique d'un programme déjà publié."""
        reponse = post_json(
            self.client, "/api/specialites", {"libelle": "Physique", "departementId": self.mpci.id, "niveau": "L2"}
        )
        specialite_id = reponse.json()["specialites"][0]["id"]
        groupe = creer_groupe("L2 MPCI Physique", departement="MPCI", niveau="L2")
        Groupe.objects.filter(id=groupe.id).update(specialite="Physique")

        self.assertEqual(self.client.delete(f"/api/specialites/{specialite_id}").status_code, 204)
        groupe.refresh_from_db()
        self.assertEqual(groupe.specialite, "Physique")


class SpecialitesCloisonnementTests(TestCase):
    """INT-07 sous sa forme nouvelle : `Specialite` n'a pas d'`ufr_id`, elle
    en hérite par son département. Le cloisonnement ne peut donc pas être
    assuré par le modèle — seul le service le fait, et c'est ici qu'on le
    vérifie."""

    def setUp(self):
        self.ufr_a = ufr_par_defaut()
        creer_ufr("ufr-b", "UFR B", "b")
        creer_compte("scolarite.a", "A", "A", Role.SCOLARITE, ufr_id=self.ufr_a)
        creer_compte("scolarite.b", "B", "B", Role.SCOLARITE, ufr_id="ufr-b")
        self.dep_b = creer_departement("Informatique B", ufr_id="ufr-b")

    def test_un_gestionnaire_ne_cree_pas_de_specialite_dans_une_autre_ufr(self):
        client = Client()
        login(client, "scolarite.a")
        reponse = post_json(
            client, "/api/specialites", {"libelle": "Réseaux", "departementId": self.dep_b.id, "niveau": "M1"}
        )
        # 404 et non 403 : dire « ce département appartient à une autre
        # UFR » confirmerait son existence à qui tâtonne.
        self.assertEqual(reponse.status_code, 404)
        self.assertFalse(Specialite.objects.filter(libelle="Réseaux").exists())

    def test_un_gestionnaire_ne_voit_que_les_specialites_de_son_ufr(self):
        client_b = Client()
        login(client_b, "scolarite.b")
        post_json(client_b, "/api/specialites", {"libelle": "Réseaux", "departementId": self.dep_b.id, "niveau": "M1"})

        client_a = Client()
        login(client_a, "scolarite.a")
        self.assertEqual(client_a.get("/api/specialites").json()["specialites"], [])

    def test_un_gestionnaire_ne_supprime_pas_la_specialite_d_une_autre_ufr(self):
        client_b = Client()
        login(client_b, "scolarite.b")
        cree = post_json(
            client_b, "/api/specialites", {"libelle": "Réseaux", "departementId": self.dep_b.id, "niveau": "M1"}
        ).json()["specialites"][0]

        client_a = Client()
        login(client_a, "scolarite.a")
        self.assertEqual(client_a.delete(f"/api/specialites/{cree['id']}").status_code, 404)
        self.assertTrue(Specialite.objects.filter(id=cree["id"]).exists())

    def test_l_admin_lit_mais_n_ecrit_pas(self):
        """FR-ADMIN-04 : l'Admin n'a aucun moyen de savoir qu'une licence de
        portail se scinde en L2 — c'est une décision pédagogique de
        l'établissement. Contrairement aux départements (exception V7), il
        n'y a donc pas de porte de secours ici."""
        client_b = Client()
        login(client_b, "scolarite.b")
        post_json(client_b, "/api/specialites", {"libelle": "Réseaux", "departementId": self.dep_b.id, "niveau": "M1"})

        creer_compte("admin.test", "Admin", "Root", Role.ADMIN)
        client_admin = Client()
        login(client_admin, "admin.test")
        self.assertEqual(len(client_admin.get("/api/specialites").json()["specialites"]), 1)
        reponse = post_json(
            client_admin, "/api/specialites", {"libelle": "Sécurité", "departementId": self.dep_b.id, "niveau": "M1"}
        )
        self.assertEqual(reponse.status_code, 403)


class CascadePubliqueSpecialiteTests(TestCase):
    """Le cinquième étage de FR-PUB-02, et la seule étape de la cascade qui
    puisse légitimement être vide."""

    def setUp(self):
        self.ufr = ufr_par_defaut()
        self.mpci = creer_departement("MPCI")
        Specialite.objects.create(departement=self.mpci, niveau="L2", libelle="Informatique")
        Specialite.objects.create(departement=self.mpci, niveau="L2", libelle="Chimie")
        self.client = Client()

    def _specialites(self, niveau: str) -> list[str]:
        reponse = self.client.get(f"/api/public/specialites?ufrId={self.ufr}&departement=MPCI&niveau={niveau}")
        self.assertEqual(reponse.status_code, 200)
        return reponse.json()["specialites"]

    def test_la_l1_est_un_tronc_commun_la_l2_propose_des_choix(self):
        """Le cas MPCI de bout en bout, tel que le chef de projet l'a
        décrit : rien à choisir en L1, un choix en L2."""
        self.assertEqual(self._specialites("L1"), [])
        self.assertEqual(self._specialites("L2"), ["Chimie", "Informatique"])

    def test_accessible_sans_authentification(self):
        """FR-AUTH-05 : la cascade publique est ouverte, et ce nouvel étage
        ne doit pas y faire exception par oubli de décoration."""
        self.assertEqual(Client().get(f"/api/public/specialites?ufrId={self.ufr}&departement=MPCI&niveau=L2").status_code, 200)

    def test_une_specialite_portee_par_un_groupe_reste_proposee(self):
        """Un groupe saisi avant l'ouverture de sa spécialité — ou dont la
        spécialité a été refermée depuis — ne doit pas devenir introuvable
        parce que le référentiel ne la contient plus."""
        groupe = creer_groupe("L3 MPCI Maths", departement="MPCI", niveau="L3")
        Groupe.objects.filter(id=groupe.id).update(specialite="Mathématiques")
        self.assertEqual(self._specialites("L3"), ["Mathématiques"])

    def test_le_filtre_par_specialite_isole_le_bon_groupe(self):
        for libelle in ("Informatique", "Chimie"):
            groupe = creer_groupe(f"L2 MPCI {libelle}", departement="MPCI", niveau="L2")
            Groupe.objects.filter(id=groupe.id).update(specialite=libelle)

        params = f"ufrId={self.ufr}&departement=MPCI&niveau=L2&specialite=Informatique"
        noms = [g["nom"] for g in self.client.get(f"/api/public/groupes?{params}").json()["groupes"]]
        self.assertEqual(noms, ["L2 MPCI Informatique"])

    def test_sans_specialite_demandee_tous_les_groupes_du_niveau_remontent(self):
        """Ne pas demander de spécialité veut dire « tous les groupes », et
        surtout PAS « ceux dont la spécialité est vide » — ce qui masquerait
        tous les groupes spécialisés au visiteur qui n'a pas touché au
        champ (cas d'un favori enregistré avant la réforme)."""
        for libelle in ("Informatique", "Chimie"):
            groupe = creer_groupe(f"L2 MPCI {libelle}", departement="MPCI", niveau="L2")
            Groupe.objects.filter(id=groupe.id).update(specialite=libelle)

        params = f"ufrId={self.ufr}&departement=MPCI&niveau=L2"
        self.assertEqual(len(self.client.get(f"/api/public/groupes?{params}").json()["groupes"]), 2)


class GroupeSpecialiteTests(TestCase):
    def setUp(self):
        self.ufr = ufr_par_defaut()
        creer_compte("scolarite.test", "Ouedraogo", "Awa", Role.SCOLARITE, ufr_id=self.ufr)
        self.client = Client()
        login(self.client, "scolarite.test")

    def test_la_specialite_est_facultative_a_la_creation(self):
        """FR-REF-34 : une L1 de tronc commun n'en a pas, et la rendre
        obligatoire interdirait de créer ces groupes-là."""
        reponse = post_json(
            self.client,
            "/api/groupes",
            {"nom": "L1 MPCI", "departement": "MPCI", "niveau": "L1", "anneeAcademique": "2026-2027"},
        )
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.json()["groupe"]["specialite"], "")

    def test_la_specialite_est_enregistree_et_modifiable(self):
        cree = post_json(
            self.client,
            "/api/groupes",
            {
                "nom": "L2 MPCI Info",
                "departement": "MPCI",
                "niveau": "L2",
                "anneeAcademique": "2026-2027",
                "specialite": "Informatique",
            },
        ).json()["groupe"]
        self.assertEqual(cree["specialite"], "Informatique")

        corrige = self.client.patch(
            f"/api/groupes/{cree['id']}",
            data=json.dumps({"specialite": "Chimie"}),
            content_type="application/json",
        )
        self.assertEqual(corrige.json()["groupe"]["specialite"], "Chimie")

    def test_le_passage_d_annee_ne_reporte_pas_la_specialite_du_groupe_source(self):
        """FR-REF-36 : le passage d'année est le moment où une cohorte de
        portail se spécialise. La spécialité du niveau précédent n'a aucune
        raison d'exister au niveau suivant — la reporter en silence ferait
        valider un choix que personne n'a fait."""
        source = post_json(
            self.client,
            "/api/groupes",
            {"nom": "L1 MPCI", "departement": "MPCI", "niveau": "L1", "anneeAcademique": "2026-2027", "effectif": 120},
        ).json()["groupe"]

        reponse = post_json(
            self.client,
            "/api/groupes/passage",
            {
                "anneeAcademiqueCible": "2027-2028",
                "groupes": [{"id": source["id"], "nom": "L2 MPCI Informatique", "effectif": 30, "specialite": "Informatique"}],
            },
        )
        self.assertEqual(reponse.status_code, 201)
        promu = reponse.json()["groupes"][0]
        self.assertEqual(promu["niveau"], "L2")
        self.assertEqual(promu["specialite"], "Informatique")


class SaisieMultipleTests(TestCase):
    """[V8.1] Plusieurs spécialités en une saisie.

    Défaut constaté à l'usage le 2026-09-21 : le Gestionnaire a tapé
    « medecine generale, science du cerveau, sicence des membres » dans la
    zone de saisie, et le Système a enregistré UNE spécialité dont le
    libellé contenait toute la phrase. Elle s'affichait telle quelle dans
    la recherche publique, où l'étudiant ne retrouvait aucune des trois.
    """

    def setUp(self):
        self.ufr = ufr_par_defaut()
        creer_compte("scolarite.test", "Ouedraogo", "Awa", Role.SCOLARITE, ufr_id=self.ufr)
        self.client = Client()
        login(self.client, "scolarite.test")
        self.dep = creer_departement("Medecine")

    def _poster(self, libelle: str):
        return post_json(
            self.client, "/api/specialites", {"libelle": libelle, "departementId": self.dep.id, "niveau": "L2"}
        )

    def test_une_saisie_separee_par_des_virgules_cree_autant_de_specialites(self):
        """LE test du correctif, avec la saisie exacte du Gestionnaire."""
        reponse = self._poster("medecine generale, science du cerveau, sicence des membres")
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(
            sorted(s["libelle"] for s in reponse.json()["specialites"]),
            ["medecine generale", "science du cerveau", "sicence des membres"],
        )
        self.assertEqual(Specialite.objects.count(), 3)

    def test_aucune_specialite_ne_conserve_de_virgule(self):
        """Le symptôme visible, vérifié pour lui-même : une virgule restée
        dans un libellé, c'est une spécialité fantôme dans la cascade."""
        self._poster("Médecine générale, Sciences du cerveau")
        for libelle in Specialite.objects.values_list("libelle", flat=True):
            self.assertNotIn(",", libelle)

    def test_les_espaces_autour_des_virgules_sont_retires(self):
        self._poster("  Chimie ,Physique  ")
        self.assertEqual(
            sorted(Specialite.objects.values_list("libelle", flat=True)), ["Chimie", "Physique"]
        )

    def test_retours_a_la_ligne_et_points_virgules_acceptes(self):
        """Une liste collée depuis un tableur arrive avec des retours à la
        ligne, pas des virgules."""
        reponse = self._poster("Chimie;Physique\nMathématiques")
        self.assertEqual(len(reponse.json()["specialites"]), 3)

    def test_un_doublon_dans_la_saisie_ne_cree_qu_une_entree(self):
        self._poster("Chimie, chimie, Physique")
        self.assertEqual(Specialite.objects.count(), 2)

    def test_un_doublon_deja_en_base_n_empeche_pas_les_autres(self):
        """Refuser les trois parce que l'une existait déjà obligerait le
        Gestionnaire à retirer lui-même celle qui bloque."""
        self._poster("Chimie")
        reponse = self._poster("Chimie, Physique, Mathématiques")
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(
            sorted(s["libelle"] for s in reponse.json()["specialites"]), ["Mathématiques", "Physique"]
        )
        self.assertEqual(reponse.json()["doublons"], ["Chimie"])

    def test_une_saisie_entierement_en_doublon_est_un_echec(self):
        """Sinon l'écran annoncerait un ajout réussi sans que rien n'ait
        changé."""
        self._poster("Chimie, Physique")
        reponse = self._poster("chimie, PHYSIQUE")
        self.assertEqual(reponse.status_code, 409)

    def test_une_saisie_vide_ou_faite_de_separateurs_est_refusee(self):
        for saisie in (" ", ",", " , ; "):
            self.assertEqual(self._poster(saisie).status_code, 400, saisie)

    def test_chaque_specialite_decoupee_est_proposee_separement_au_public(self):
        """La finalité : trois entrées distinctes dans la liste déroulante
        du visiteur, pas une seule ligne à rallonge."""
        self._poster("Médecine générale, Sciences du cerveau, Sciences des membres")
        params = f"ufrId={self.ufr}&departement=Medecine&niveau=L2"
        self.assertEqual(
            Client().get(f"/api/public/specialites?{params}").json()["specialites"],
            ["Médecine générale", "Sciences des membres", "Sciences du cerveau"],
        )


class PassageSpecialiteNonReporteeTests(TestCase):
    """[V8.6] FR-REF-36 — la spécialité du groupe SOURCE ne se reporte jamais.

    Régression trouvée le 2026-09-23 en relisant le code : le service
    écrivait `item.get("specialite") or groupe.specialite`, et comme le
    front envoie toujours la clé — vide quand le Gestionnaire n'a rien
    choisi — `"" or x` valait `x`. Une L1 rattachée à une spécialité,
    promue en laissant le champ sur « Aucune », emportait donc l'ancienne.

    Le test précédent ne l'attrapait pas : il fournissait une spécialité
    cible explicite, donc le repli ne se déclenchait jamais.
    """

    def setUp(self):
        self.ufr = ufr_par_defaut()
        creer_compte("scolarite.test", "Ouedraogo", "Awa", Role.SCOLARITE, ufr_id=self.ufr)
        self.client = Client()
        login(self.client, "scolarite.test")

        self.source = creer_groupe("L1 MPCI", departement="MPCI", niveau="L1", annee_academique="2026-2027")
        Groupe.objects.filter(id=self.source.id).update(specialite="Tronc commun scientifique")

    def _promouvoir(self, item_extra: dict):
        return post_json(
            self.client,
            "/api/groupes/passage",
            {
                "anneeAcademiqueCible": "2027-2028",
                "groupes": [{"id": self.source.id, "nom": "L2 MPCI", "effectif": 30, **item_extra}],
            },
        )

    def test_une_specialite_vide_ne_recopie_pas_celle_de_la_source(self):
        reponse = self._promouvoir({"specialite": ""})
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.json()["groupes"][0]["specialite"], "")

    def test_une_specialite_absente_ne_recopie_pas_non_plus(self):
        """Un appel qui omet complètement la clé — script, client ancien."""
        reponse = self._promouvoir({})
        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.json()["groupes"][0]["specialite"], "")

    def test_la_specialite_cible_choisie_est_bien_enregistree(self):
        reponse = self._promouvoir({"specialite": "Informatique"})
        self.assertEqual(reponse.json()["groupes"][0]["specialite"], "Informatique")
