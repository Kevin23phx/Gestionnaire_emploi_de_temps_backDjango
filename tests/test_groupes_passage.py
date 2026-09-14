from django.test import Client, TestCase

from accounts.models import Role
from referentiel.models import Groupe
from tests.base import creer_compte, creer_groupe, creer_ufr, login, post_json

# [V6] FR-REF-12 — passage à l'année supérieure. Une promotion crée un
# nouveau Groupe (jamais de modification sur place, cf. models.py) : ces
# tests portent donc sur /api/groupes/passage et sur l'état des DEUX lignes
# (l'ancienne conservée telle quelle, la nouvelle créée).


class GroupesPassageTests(TestCase):
    def setUp(self):
        creer_ufr("ufr-a", "UFR Test A", "tsa")
        creer_ufr("ufr-b", "UFR Test B", "tsb")
        creer_compte("scolarite.tsa", "Gestionnaire", "A", Role.SCOLARITE, ufr_id="ufr-a")
        creer_compte("scolarite.tsb", "Gestionnaire", "B", Role.SCOLARITE, ufr_id="ufr-b")

        self.groupe_l1 = creer_groupe(
            "L1 Info - Groupe A", "Informatique", "L1", ufr_id="ufr-a", annee_academique="2026-2027", effectif=40
        )
        self.groupe_l3 = creer_groupe(
            "L3 Info - Groupe A", "Informatique", "L3", ufr_id="ufr-a", annee_academique="2026-2027", effectif=25
        )
        self.groupe_autre_ufr = creer_groupe(
            "L1 Droit - Groupe A", "Droit", "L1", ufr_id="ufr-b", annee_academique="2026-2027", effectif=50
        )

        self.client_a = Client()
        login(self.client_a, "scolarite.tsa")
        self.client_b = Client()
        login(self.client_b, "scolarite.tsb")

    def test_promeut_un_groupe_l1_vers_l2_en_creant_un_nouveau_groupe(self):
        res = post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_l1.id, "nom": "L2 Info - Groupe A", "effectif": 34}]},
        )
        self.assertEqual(res.status_code, 201, res.content)
        nouveau = res.json()["groupes"][0]
        self.assertEqual(nouveau["niveau"], "L2")
        self.assertEqual(nouveau["anneeAcademique"], "2027-2028")
        self.assertEqual(nouveau["effectif"], 34)
        self.assertEqual(nouveau["departement"], "Informatique")

        # L'ancien groupe existe toujours, inchangé (jamais de mutation sur place).
        self.groupe_l1.refresh_from_db()
        self.assertEqual(self.groupe_l1.niveau, "L1")
        self.assertEqual(self.groupe_l1.effectif, 40)
        self.assertEqual(Groupe.objects.get(id=nouveau["id"]).promu_de_id, self.groupe_l1.id)

    def test_effectif_diminue_a_la_promotion_est_pris_en_compte(self):
        """C'est tout le point du mécanisme : le Système ne recopie pas
        l'effectif de l'an dernier sans y toucher, il l'accepte tel que le
        Gestionnaire le corrige (abandons, redoublements)."""
        res = post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_l1.id, "nom": "L2 Info - Groupe A", "effectif": 31}]},
        )
        self.assertEqual(res.json()["groupes"][0]["effectif"], 31)

    def test_refuse_l_absence_de_nom_cible(self):
        """Sans nom explicite, retomber sur celui du groupe source
        collisionnerait avec la contrainte d'unicité (ce nom est déjà pris
        par le groupe source lui-même)."""
        res = post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_l1.id, "effectif": 31}]},
        )
        self.assertEqual(res.status_code, 400)

    def test_refuse_un_groupe_de_fin_de_cycle(self):
        res = post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_l3.id, "effectif": 20}]},
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("fin de cycle", res.json()["erreur"])
        self.assertEqual(Groupe.objects.filter(promu_de_id=self.groupe_l3.id).count(), 0)

    def test_refuse_une_annee_cible_qui_n_est_pas_la_suivante(self):
        res = post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2028-2029", "groupes": [{"id": self.groupe_l1.id, "effectif": 30}]},
        )
        self.assertEqual(res.status_code, 400)

    def test_refuse_de_promouvoir_deux_fois_le_meme_groupe(self):
        premier = post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_l1.id, "nom": "L2 Info - Groupe A", "effectif": 35}]},
        )
        self.assertEqual(premier.status_code, 201)

        second = post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_l1.id, "nom": "L2 Info - Groupe A (bis)", "effectif": 35}]},
        )
        self.assertEqual(second.status_code, 409)

    def test_refuse_un_groupe_d_une_autre_ufr(self):
        res = post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_autre_ufr.id, "nom": "L2 Droit - Groupe A", "effectif": 45}]},
        )
        self.assertEqual(res.status_code, 409)
        self.assertEqual(Groupe.objects.filter(promu_de_id=self.groupe_autre_ufr.id).count(), 0)

    def test_campagne_tout_ou_rien_un_groupe_invalide_annule_tout_le_lot(self):
        """Deux groupes dans la même requête : le premier est valide, le
        second est en fin de cycle. Rien ne doit être créé, y compris pour
        le premier — sinon une campagne partiellement appliquée laisserait
        un état incohérent que le Gestionnaire n'a pas validé."""
        res = post_json(
            self.client_a,
            "/api/groupes/passage",
            {
                "anneeAcademiqueCible": "2027-2028",
                "groupes": [
                    {"id": self.groupe_l1.id, "nom": "L2 Info - Groupe A", "effectif": 35},
                    {"id": self.groupe_l3.id, "nom": "L4 Info - Groupe A", "effectif": 20},
                ],
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Groupe.objects.filter(promu_de_id=self.groupe_l1.id).count(), 0)

    def test_gestionnaire_ne_peut_pas_promouvoir_un_groupe_hors_de_son_ufr(self):
        res = post_json(
            self.client_b,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_l1.id, "nom": "L2 Info - Groupe A", "effectif": 35}]},
        )
        self.assertEqual(res.status_code, 409)

    def test_liste_des_groupes_signale_ceux_deja_promus(self):
        res_avant = self.client_a.get("/api/groupes")
        groupe_avant = next(g for g in res_avant.json()["groupes"] if g["id"] == self.groupe_l1.id)
        self.assertFalse(groupe_avant["aDejaEteSuccede"])

        post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_l1.id, "nom": "L2 Info - Groupe A", "effectif": 35}]},
        )

        res_apres = self.client_a.get("/api/groupes")
        groupe_apres = next(g for g in res_apres.json()["groupes"] if g["id"] == self.groupe_l1.id)
        self.assertTrue(groupe_apres["aDejaEteSuccede"])

    def test_le_nom_d_un_groupe_promu_redevient_disponible_pour_la_promotion_suivante(self):
        """Le groupe source (ex. "L1 Info - Groupe A" 2026-2027) reste en
        base comme historique après son passage en L2 — jamais supprimé
        (FR-REF-12). La PROCHAINE promotion de L1 (nouveaux admis
        2027-2028) doit pouvoir porter exactement le même nom : ce n'est
        pas un doublon, c'est la nouvelle cohorte qui prend la suite."""
        promotion = post_json(
            self.client_a,
            "/api/groupes/passage",
            {"anneeAcademiqueCible": "2027-2028", "groupes": [{"id": self.groupe_l1.id, "nom": "L2 Info - Groupe A", "effectif": 35}]},
        )
        self.assertEqual(promotion.status_code, 201)

        nouvel_intake = post_json(
            self.client_a,
            "/api/groupes",
            {"nom": "L1 Info - Groupe A", "departement": "Informatique", "niveau": "L1", "anneeAcademique": "2027-2028", "effectif": 45},
        )
        self.assertEqual(nouvel_intake.status_code, 201, nouvel_intake.content)

    def test_refuse_toujours_un_doublon_de_nom_dans_la_meme_annee(self):
        """La protection d'origine reste entière : deux groupes ne peuvent
        pas porter le même nom LA MÊME année — seule la répétition d'une
        année à l'autre est désormais permise."""
        res = post_json(
            self.client_a,
            "/api/groupes",
            {"nom": self.groupe_l1.nom, "departement": "Informatique", "niveau": "L1", "anneeAcademique": self.groupe_l1.annee_academique, "effectif": 10},
        )
        self.assertEqual(res.status_code, 409)
