"""Tests UNITAIRES du noyau — sans base de données ni requête HTTP.

Ils complètent les tests d'intégration (qui passent par le client Django) en
verrouillant deux briques que tout le reste traverse :

- `core.time_utils` : la frontière entre le "HH:MM" du contrat API et les
  minutes stockées en base. Une erreur ici déplacerait silencieusement des
  cours.
- `core.exceptions` : le contrat d'erreur, qui promet `{"erreur": "..."}`
  sur TOUTES les réponses d'échec. Un écart renverrait le `{"detail": ...}`
  de DRF, que le frontend n'affiche pas — l'utilisateur verrait un message
  vide au lieu de la raison du refus.
"""

from django.db import IntegrityError
from django.http import Http404
from django.test import SimpleTestCase
from rest_framework import exceptions as drf_exceptions

from core.exceptions import contrat_api_exception_handler
from core.time_utils import hhmm_to_minutes, is_valid_hhmm, minutes_to_hhmm

# SimpleTestCase et non TestCase : aucun de ces tests ne touche la base, et
# s'en passer les rend instantanés.


class TimeUtilsTests(SimpleTestCase):
    def test_conversion_en_minutes(self):
        self.assertEqual(hhmm_to_minutes("00:00"), 0)
        self.assertEqual(hhmm_to_minutes("08:00"), 480)
        self.assertEqual(hhmm_to_minutes("10:15"), 615)
        self.assertEqual(hhmm_to_minutes("23:59"), 1439)

    def test_conversion_inverse(self):
        self.assertEqual(minutes_to_hhmm(0), "00:00")
        self.assertEqual(minutes_to_hhmm(480), "08:00")
        self.assertEqual(minutes_to_hhmm(1439), "23:59")

    def test_aller_retour_sur_toutes_les_minutes_de_la_journee(self):
        """La conversion doit être exactement réversible : c'est elle qui
        garantit qu'un horaire saisi ressort identique à l'affichage."""
        for minutes in range(0, 24 * 60):
            self.assertEqual(hhmm_to_minutes(minutes_to_hhmm(minutes)), minutes)

    def test_refuse_les_formats_invalides(self):
        for invalide in ["24:00", "25:00", "08:60", "8:00", "0800", "", "abc", "08:0", "-1:00"]:
            with self.subTest(valeur=invalide):
                self.assertFalse(is_valid_hhmm(invalide))
                with self.assertRaises(ValueError):
                    hhmm_to_minutes(invalide)

    def test_le_message_d_erreur_cite_la_valeur_fautive(self):
        """Sans la valeur reçue dans le message, une saisie refusée est
        indébogable pour celui qui la lit."""
        with self.assertRaises(ValueError) as erreur:
            hhmm_to_minutes("25:99")
        self.assertIn("25:99", str(erreur.exception))

    def test_accepte_les_bornes_valides(self):
        for valide in ["00:00", "09:30", "19:45", "23:59"]:
            with self.subTest(valeur=valide):
                self.assertTrue(is_valid_hhmm(valide))


class ContratErreurTests(SimpleTestCase):
    """Toute réponse d'échec porte la clé "erreur" — jamais "detail"."""

    def test_ressource_introuvable(self):
        reponse = contrat_api_exception_handler(Http404(), {})
        self.assertEqual(reponse.status_code, 404)
        self.assertEqual(reponse.data, {"erreur": "Ressource introuvable."})

    def test_erreur_de_validation_simple(self):
        reponse = contrat_api_exception_handler(drf_exceptions.ValidationError("Le nom est obligatoire."), {})
        self.assertEqual(reponse.status_code, 400)
        self.assertEqual(reponse.data["erreur"], "Le nom est obligatoire.")
        self.assertNotIn("detail", reponse.data)

    def test_erreur_de_validation_par_champ(self):
        """DRF renvoie {champ: [messages]} : on en extrait le premier message
        lisible plutôt que d'afficher la structure brute."""
        reponse = contrat_api_exception_handler(
            drf_exceptions.ValidationError({"nom": ["Ce champ est obligatoire."]}), {}
        )
        self.assertEqual(reponse.data["erreur"], "Ce champ est obligatoire.")

    def test_permission_refusee_et_non_authentifie(self):
        self.assertEqual(contrat_api_exception_handler(drf_exceptions.PermissionDenied(), {}).status_code, 403)
        self.assertEqual(contrat_api_exception_handler(drf_exceptions.NotAuthenticated(), {}).status_code, 401)

    def test_un_corps_deja_conforme_n_est_pas_ecrase(self):
        """Le planning lève des exceptions portant déjà {erreur, conflits} :
        écraser ce corps ferait perdre la liste des conflits, seule
        information qui permet au Gestionnaire de corriger sa saisie."""

        class ConflitDetaille(drf_exceptions.APIException):
            status_code = 409

        exc = ConflitDetaille({"erreur": "Conflit détecté.", "conflits": [{"type": "salle"}]})
        reponse = contrat_api_exception_handler(exc, {})
        self.assertEqual(reponse.status_code, 409)
        self.assertEqual(reponse.data["erreur"], "Conflit détecté.")
        self.assertEqual(reponse.data["conflits"], [{"type": "salle"}])

    def test_double_reservation_en_base_devient_un_409(self):
        """La contrainte d'exclusion Postgres est le dernier rempart contre
        deux cours dans la même salle : elle doit se traduire en conflit
        explicite, pas en 500."""
        reponse = contrat_api_exception_handler(IntegrityError("creneau_no_double_booking"), {})
        self.assertEqual(reponse.status_code, 409)
        self.assertIn("salle déjà réservée", reponse.data["erreur"])

    def test_motif_obligatoire_devient_un_400(self):
        reponse = contrat_api_exception_handler(IntegrityError("creneau_motif_requis_si_non_normal"), {})
        self.assertEqual(reponse.status_code, 400)
        self.assertIn("motif est obligatoire", reponse.data["erreur"])

    def test_doublon_devient_un_409(self):
        for message in ["duplicate key value violates unique constraint", "23505"]:
            with self.subTest(message=message):
                reponse = contrat_api_exception_handler(IntegrityError(message), {})
                self.assertEqual(reponse.status_code, 409)
                self.assertIn("existe déjà", reponse.data["erreur"])

    def test_integrite_inconnue_ne_fuite_pas_le_message_postgres(self):
        """Un message d'erreur Postgres brut renseigne sur le schéma : il
        reste dans les journaux, jamais dans la réponse."""
        reponse = contrat_api_exception_handler(IntegrityError('colonne "mot_de_passe_hash" viole...'), {})
        self.assertEqual(reponse.status_code, 500)
        self.assertEqual(reponse.data["erreur"], "Erreur interne.")

    def test_exception_non_geree_est_laissee_a_django(self):
        """Renvoyer None laisse Django produire un vrai 500 : une erreur de
        programmation ne doit pas être maquillée en réponse normale."""
        self.assertIsNone(contrat_api_exception_handler(KeyError("heureDebut"), {}))
