from django.conf import settings
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework.throttling import ScopedRateThrottle

from accounts import auth_service
from accounts.throttling import (
    ConnexionParCompteThrottle,
    ConnexionParIpThrottle,
    ParCompteConnecteThrottle,
)


def _requis(data: dict, *champs: str) -> None:
    for champ in champs:
        if not data.get(champ):
            raise ValidationError(f"Le champ '{champ}' est obligatoire.")


class LoginView(APIView):
    permission_classes = [AllowAny]
    # [V8.8] OWASP A07. Les DEUX clés, et pas une seule : par IP contre
    # l'automate depuis une machine, par compte visé contre l'attaque
    # distribuée qui change d'adresse à chaque essai. La seconde est
    # indispensable ici — les identifiants sont publics et devinables
    # (`scolarite.<sigle>`, FR-ADMIN-02), et le parc tient en douze comptes.
    # Voir accounts/throttling.py.
    throttle_classes = [ConnexionParIpThrottle, ConnexionParCompteThrottle]

    def post(self, request):
        _requis(request.data, "identifiant", "motDePasse")
        response = Response()
        resultat = auth_service.login(
            request.data["identifiant"],
            request.data["motDePasse"],
            response,
            # L'adresse vient du throttle de DRF, qui sait déjà lire
            # X-Forwarded-For quand le serveur est derrière un relais.
            ConnexionParIpThrottle().get_ident(request),
        )
        response.data = resultat
        response.status_code = 200
        return response


class ActivateView(APIView):
    permission_classes = [AllowAny]
    # Limitée elle aussi : c'est la seconde porte ouverte sans
    # authentification, et elle DÉFINIT un mot de passe. Elle permet en
    # outre de distinguer un compte inexistant d'un compte déjà activé
    # (messages volontairement distincts, cf. auth_service) — donc d'énumérer
    # les comptes. Sans limite, cette énumération est gratuite.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "activation"

    def post(self, request):
        _requis(request.data, "identifiant", "nouveauMotDePasse", "confirmationMotDePasse")
        response = Response()
        resultat = auth_service.activate(
            request.data["identifiant"],
            request.data["nouveauMotDePasse"],
            request.data["confirmationMotDePasse"],
            response,
        )
        response.data = resultat
        response.status_code = 200
        return response


class MotDePasseView(APIView):
    """[V8.3] FR-AUTH-07 — changement de mot de passe par son titulaire.

    Pas de `permission_classes` : la valeur par défaut du projet
    (`IsAuthenticatedCM`) s'applique, donc la route est fermée aux appels
    anonymes. C'est volontairement l'inverse de la page d'activation, qui
    doit rester ouverte puisqu'on n'y est par définition pas encore
    connecté.

    L'utilisateur vient de `request.user`, c'est-à-dire du cookie de
    session — jamais du corps de la requête. Un compte ne peut donc changer
    que SON mot de passe, y compris pour l'Admin : rien dans cette route ne
    permet de désigner quelqu'un d'autre.
    """

    # Le mot de passe actuel y est vérifié : sans limite, cette route
    # deviendrait un oracle pour le deviner depuis une session volée.
    #
    # Throttle maison et non `ScopedRateThrottle` : celui de DRF lit
    # `request.user.pk`, absent de l'`AuthenticatedUser` de ce projet.
    throttle_classes = [ParCompteConnecteThrottle]

    def post(self, request):
        _requis(request.data, "motDePasseActuel", "nouveauMotDePasse", "confirmationMotDePasse")
        response = Response()
        resultat = auth_service.changer_mot_de_passe(
            request.user.id,
            request.data["motDePasseActuel"],
            request.data["nouveauMotDePasse"],
            request.data["confirmationMotDePasse"],
            response,
        )
        response.data = resultat
        response.status_code = 200
        return response


class LogoutView(APIView):
    def post(self, request):
        raw_token = request.COOKIES.get(settings.SESSION_COOKIE_NAME)
        response = Response()
        auth_service.logout(raw_token, response)
        response.data = {"ok": True}
        response.status_code = 200
        return response


class MeView(APIView):
    def get(self, request):
        user = request.user
        return Response({"nom": user.nom, "prenom": user.prenom, "role": user.role, "ufrId": user.ufr_id})
