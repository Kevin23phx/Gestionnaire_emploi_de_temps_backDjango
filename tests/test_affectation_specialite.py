"""[V8.1, 2026-09-21] Affectation d'un créneau à une spécialité.

Retour du porteur de projet : au lieu de créer un groupe par spécialité
(quatre « L2 Médecine »), la scolarité tient UN groupe et affecte chaque
créneau. Un cours sans affectation concerne toute la promotion.

Ce que ces tests protègent, par ordre d'importance :

1. **La règle de conflit.** C'est ce qui rend le mécanisme utilisable ou
   inutilisable : deux cours de spécialités DIFFÉRENTES à la même heure ne
   sont pas un conflit (sous-populations disjointes), mais un cours commun
   et un cours de spécialité à la même heure en sont un (les mêmes
   étudiants sont attendus aux deux). Une régression ici bloquerait chaque
   cours de spécialité, ou laisserait passer de vrais doubles cours.
2. **Le programme d'une spécialité = ses cours PLUS les cours communs.** Ne
   montrer que les cours portant le libellé cacherait à l'étudiant la
   moitié de sa semaine.
3. **Salle et enseignant restent cloisonnés** quelle que soit la
   spécialité : une salle ne se dédouble pas.
"""

import datetime
import json

from django.test import Client, TestCase

from accounts.models import Role
from planning.models import Creneau
from referentiel.models import Departement, Specialite
from tests.base import (
    creer_compte,
    creer_enseignant,
    creer_groupe,
    creer_salle,
    creer_ue,
    jour,
    login,
    post_json,
    ufr_par_defaut,
)


class AffectationCreneauTests(TestCase):
    def setUp(self):
        self.ufr = ufr_par_defaut()
        creer_compte("scolarite.test", "Ouedraogo", "Awa", Role.SCOLARITE, ufr_id=self.ufr)
        self.client = Client()
        login(self.client, "scolarite.test")

        # UN seul groupe — c'est tout l'objet de la V8.1.
        self.groupe = creer_groupe("L2 Médecine", departement="Médecine", niveau="L2", effectif=40)
        self.dep = Departement.objects.create(libelle="Médecine", ufr_id=self.ufr)
        for libelle in ("Informatique", "Chimie"):
            Specialite.objects.create(departement=self.dep, niveau="L2", libelle=libelle)

        self.ue_a = creer_ue("Algorithmique", code="INFO1")
        self.ue_b = creer_ue("Chimie organique", code="CHIM1")
        self.ue_c = creer_ue("Anatomie générale", code="ANAT1")
        self.ens_a = creer_enseignant("Kabore", "Paul")
        self.ens_b = creer_enseignant("Sawadogo", "Marie")
        self.salle_a = creer_salle("Amphi A", capacite=200)
        self.salle_b = creer_salle("Amphi B", capacite=200)
        self.mardi = jour("mardi").isoformat()

    def _creneau(self, ue, enseignant, salle, specialite="", heure=("08:00", "10:00"), **extra):
        return {
            "ueId": ue.id,
            "enseignantId": enseignant.id,
            "salleId": salle.id,
            "groupeId": self.groupe.id,
            "date": self.mardi,
            "heureDebut": heure[0],
            "heureFin": heure[1],
            "specialite": specialite,
            **extra,
        }

    def _poster(self, *creneaux):
        return post_json(self.client, "/api/creneaux", {"creneaux": list(creneaux)})

    # --- 1. La règle de conflit --------------------------------------------

    def test_deux_specialites_differentes_a_la_meme_heure_ne_sont_pas_un_conflit(self):
        """LE test de la V8.1. Maths et Chimie le mardi à 8h : deux salles,
        deux enseignants, deux sous-populations disjointes. Sans cette
        règle, le mécanisme serait inutilisable — chaque cours de
        spécialité bloquerait tous les autres."""
        self.assertEqual(self._poster(self._creneau(self.ue_a, self.ens_a, self.salle_a, "Informatique")).status_code, 201)
        reponse = self._poster(self._creneau(self.ue_b, self.ens_b, self.salle_b, "Chimie"))
        self.assertEqual(reponse.status_code, 201, reponse.content)
        self.assertEqual(Creneau.objects.filter(groupe=self.groupe).count(), 2)

    def test_un_cours_commun_et_un_cours_de_specialite_a_la_meme_heure_sont_un_conflit(self):
        """Les étudiants d'Informatique sont attendus AUSSI au cours commun
        d'anatomie : ils ne peuvent pas être aux deux."""
        self._poster(self._creneau(self.ue_c, self.ens_a, self.salle_a))  # commun
        reponse = self._poster(self._creneau(self.ue_a, self.ens_b, self.salle_b, "Informatique"))
        self.assertEqual(reponse.status_code, 409)
        types = [c["type"] for c in reponse.json()["conflits"]]
        self.assertIn("groupe", types)

    def test_deux_cours_de_la_MEME_specialite_a_la_meme_heure_sont_un_conflit(self):
        self._poster(self._creneau(self.ue_a, self.ens_a, self.salle_a, "Informatique"))
        reponse = self._poster(self._creneau(self.ue_b, self.ens_b, self.salle_b, "Informatique"))
        self.assertEqual(reponse.status_code, 409)
        self.assertIn("groupe", [c["type"] for c in reponse.json()["conflits"]])

    def test_deux_cours_communs_a_la_meme_heure_restent_un_conflit(self):
        """Le comportement d'avant la V8.1, inchangé pour un groupe dont
        aucun créneau n'est affecté."""
        self._poster(self._creneau(self.ue_c, self.ens_a, self.salle_a))
        reponse = self._poster(self._creneau(self.ue_a, self.ens_b, self.salle_b))
        self.assertEqual(reponse.status_code, 409)
        self.assertIn("groupe", [c["type"] for c in reponse.json()["conflits"]])

    def test_la_casse_ne_cree_pas_deux_specialites_distinctes(self):
        """« Informatique » et « informatique » sont la même sous-population :
        les opposer ferait passer un vrai double cours pour deux cours
        parallèles."""
        self._poster(self._creneau(self.ue_a, self.ens_a, self.salle_a, "Informatique"))
        reponse = self._poster(self._creneau(self.ue_b, self.ens_b, self.salle_b, "informatique"))
        self.assertEqual(reponse.status_code, 409)

    # --- 2. Salle et enseignant ne se dédoublent jamais ---------------------

    def test_la_meme_salle_reste_un_conflit_entre_specialites_differentes(self):
        """Une salle ne peut pas héberger deux cours simultanés, quelle que
        soit la spécialité des étudiants en face."""
        self._poster(self._creneau(self.ue_a, self.ens_a, self.salle_a, "Informatique"))
        reponse = self._poster(self._creneau(self.ue_b, self.ens_b, self.salle_a, "Chimie"))
        self.assertEqual(reponse.status_code, 409)
        self.assertIn("salle", [c["type"] for c in reponse.json()["conflits"]])

    def test_le_meme_enseignant_reste_un_conflit_entre_specialites_differentes(self):
        self._poster(self._creneau(self.ue_a, self.ens_a, self.salle_a, "Informatique"))
        reponse = self._poster(self._creneau(self.ue_b, self.ens_a, self.salle_b, "Chimie"))
        self.assertEqual(reponse.status_code, 409)
        self.assertIn("enseignant", [c["type"] for c in reponse.json()["conflits"]])

    # --- 3. L'affectation est enregistrée et modifiable ---------------------

    def test_l_affectation_est_enregistree_et_relue(self):
        cree = self._poster(self._creneau(self.ue_a, self.ens_a, self.salle_a, "Informatique")).json()["creneaux"][0]
        self.assertEqual(cree["specialite"], "Informatique")
        self.assertEqual(self.client.get(f"/api/creneaux/{cree['id']}").json()["specialite"], "Informatique")

    def test_un_creneau_sans_affectation_concerne_tout_le_groupe(self):
        cree = self._poster(self._creneau(self.ue_c, self.ens_a, self.salle_a)).json()["creneaux"][0]
        self.assertEqual(cree["specialite"], "")

    def test_l_affectation_est_corrigeable(self):
        cree = self._poster(self._creneau(self.ue_a, self.ens_a, self.salle_a, "Informatique")).json()["creneaux"][0]
        corrige = self.client.patch(
            f"/api/creneaux/{cree['id']}",
            data=json.dumps({**self._creneau(self.ue_a, self.ens_a, self.salle_a, "Chimie"), "id": cree["id"]}),
            content_type="application/json",
        )
        self.assertEqual(corrige.status_code, 200)
        self.assertEqual(corrige.json()["specialite"], "Chimie")


class ProgrammePublicSpecialiteTests(TestCase):
    """Le programme que voit l'étudiant : ses cours PLUS les cours communs."""

    def setUp(self):
        self.ufr = ufr_par_defaut()
        creer_compte("scolarite.test", "Ouedraogo", "Awa", Role.SCOLARITE, ufr_id=self.ufr)
        gestionnaire = Client()
        login(gestionnaire, "scolarite.test")

        self.groupe = creer_groupe("L2 Médecine", departement="Médecine", niveau="L2", effectif=40)
        dep = Departement.objects.create(libelle="Médecine", ufr_id=self.ufr)
        for libelle in ("Informatique", "Chimie"):
            Specialite.objects.create(departement=dep, niveau="L2", libelle=libelle)

        # Deux enseignants : les cours d'Informatique et de Chimie tombent
        # à la même heure, et un même enseignant ne peut pas être aux deux —
        # ce serait un conflit « enseignant » bien réel, qui empêcherait la
        # fixture de se construire (et masquerait ce qu'on veut tester).
        ens_commun = creer_enseignant("Kabore", "Paul")
        ens_info = creer_enseignant("Sawadogo", "Marie")
        ens_chimie = creer_enseignant("Zongo", "Ali")
        mardi = jour("mardi").isoformat()

        def poser(intitule, code, salle_nom, heure, specialite, enseignant):
            reponse = post_json(
                gestionnaire,
                "/api/creneaux",
                {
                    "creneaux": [
                        {
                            "ueId": creer_ue(intitule, code=code).id,
                            "enseignantId": enseignant.id,
                            "salleId": creer_salle(salle_nom, capacite=200).id,
                            "groupeId": self.groupe.id,
                            "date": mardi,
                            "heureDebut": heure[0],
                            "heureFin": heure[1],
                            "specialite": specialite,
                        }
                    ]
                },
            )
            # Une fixture qui échoue en silence produit des tests qui
            # passent pour de mauvaises raisons : on le constate ici.
            assert reponse.status_code == 201, (intitule, reponse.status_code, reponse.content)

        poser("Anatomie générale", "ANAT1", "Amphi A", ("08:00", "10:00"), "", ens_commun)
        poser("Algorithmique", "INFO1", "Amphi B", ("10:15", "12:00"), "Informatique", ens_info)
        poser("Chimie organique", "CHIM1", "Amphi C", ("10:15", "12:00"), "Chimie", ens_chimie)

        self.anonyme = Client()
        self.semaine = jour("lundi").isoformat()

    def _seances(self, specialite: str | None = None) -> list[str]:
        url = f"/api/public/programme/{self.groupe.id}?semaine={self.semaine}"
        if specialite is not None:
            url += f"&specialite={specialite}"
        reponse = self.anonyme.get(url)
        self.assertEqual(reponse.status_code, 200)
        return sorted(s["ue"]["intitule"] for s in reponse.json()["seances"])

    def test_l_etudiant_voit_sa_specialite_ET_le_tronc_commun(self):
        """La règle centrale. Ne montrer que « Algorithmique » cacherait
        l'anatomie — et l'étudiant manquerait un cours qu'il doit suivre."""
        self.assertEqual(self._seances("Informatique"), ["Algorithmique", "Anatomie générale"])
        self.assertEqual(self._seances("Chimie"), ["Anatomie générale", "Chimie organique"])

    def test_sans_specialite_le_programme_complet_du_groupe_est_servi(self):
        self.assertEqual(
            self._seances(), ["Algorithmique", "Anatomie générale", "Chimie organique"]
        )

    def test_la_specialite_consultee_titre_la_feuille(self):
        reponse = self.anonyme.get(
            f"/api/public/programme/{self.groupe.id}?semaine={self.semaine}&specialite=Informatique"
        ).json()
        self.assertEqual(reponse["groupe"]["specialiteConsultee"], "Informatique")

    def test_chaque_seance_dit_a_qui_elle_s_adresse(self):
        reponse = self.anonyme.get(f"/api/public/programme/{self.groupe.id}?semaine={self.semaine}").json()
        par_ue = {s["ue"]["intitule"]: s["specialite"] for s in reponse["seances"]}
        self.assertEqual(par_ue["Anatomie générale"], "")
        self.assertEqual(par_ue["Algorithmique"], "Informatique")

    def test_la_cascade_retrouve_le_groupe_unique_par_sa_specialite(self):
        """Le groupe ne porte AUCUNE spécialité (c'est le modèle V8.1) :
        sans la clause « ou vide », la recherche ne renverrait plus rien."""
        params = f"ufrId={self.ufr}&departement=Médecine&niveau=L2&specialite=Informatique"
        groupes = self.anonyme.get(f"/api/public/groupes?{params}").json()["groupes"]
        self.assertEqual([g["nom"] for g in groupes], ["L2 Médecine"])

    def test_les_specialites_portees_par_les_creneaux_alimentent_la_cascade(self):
        """Une spécialité refermée au référentiel mais encore portée par des
        créneaux reste proposée — sinon son programme deviendrait
        introuvable."""
        Specialite.objects.all().delete()
        params = f"ufrId={self.ufr}&departement=Médecine&niveau=L2"
        self.assertEqual(
            self.anonyme.get(f"/api/public/specialites?{params}").json()["specialites"],
            ["Chimie", "Informatique"],
        )

    def test_le_flux_calendrier_est_filtre_par_specialite(self):
        contenu = self.anonyme.get(
            f"/api/public/calendrier/{self.groupe.id}.ics?specialite=Informatique"
        ).content.decode()
        self.assertIn("Algorithmique", contenu)
        self.assertIn("Anatomie générale", contenu)
        self.assertNotIn("Chimie organique", contenu)
