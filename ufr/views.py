import re

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import require_roles
from ufr import services
from ufr.serializers import UfrSerializer

SIGLE_RE = re.compile(r"^[a-zA-Z]{2,10}$")

# [V3.2] Le sigle reste alphabétique et court : il sert d'identifiant de
# compte (scolarite.<sigle>) et d'identifiant technique (ufr-<sigle>). Le
# préfixe "UFR/" des documents officiels n'y entre donc jamais — il est
# ajouté à l'affichage, à partir du type (cf. Ufr.sigle_affiche).


class UfrListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            # [V3] `return []` retirait TOUTE permission au lieu de retomber
            # sur IsAuthenticatedCM : la route devenait ouverte aux appels
            # anonymes, qui plantaient ensuite en 500 sur `user.role` au
            # lieu du 401 attendu. Bug antérieur à la V3, corrigé ici parce
            # qu'il devient autrement plus grave dès lors qu'une surface
            # publique existe pour de bon : le défaut du projet doit rester
            # « tout est fermé », et l'ouverture une déclaration explicite
            # (public/views.py, AllowAny écrit vue par vue).
            return super().get_permissions()  # IsAuthenticatedCM
        return [require_roles("admin")()]

    def get(self, request):
        return Response({"ufrs": services.list_ufrs()})

    def post(self, request):
        nom = request.data.get("nom")
        sigle = request.data.get("sigle")
        if not nom:
            raise ValidationError("Le nom est obligatoire.")
        if not sigle or not SIGLE_RE.match(sigle):
            raise ValidationError("Le sigle doit contenir entre 2 et 10 lettres, sans espace ni accent.")

        auteur = f"{request.user.prenom} {request.user.nom}"
        ufr = services.create(nom, sigle, request.data.get("type", "ufr"), auteur)
        return Response({"ufr": UfrSerializer(ufr).data}, status=201)


class PeriodeAcademiqueView(APIView):
    """[V3] FR-REF-16 : le Gestionnaire définit la période de SA propre UFR.

    Le `ufr_id` n'est jamais lu dans la requête : il vient de la session
    (INT-07). Un Gestionnaire ne peut donc pas, même en forgeant l'appel,
    déplacer la rentrée d'une UFR voisine.
    """

    permission_classes = [require_roles("scolarite")]

    def put(self, request):
        debut = request.data.get("debut")
        fin = request.data.get("fin")
        if not debut or not fin:
            raise ValidationError("Les dates de début et de fin sont obligatoires.")
        auteur = f"{request.user.prenom} {request.user.nom}"
        ufr = services.definir_periode(request.user.ufr_id, request.data.get("libelle"), debut, fin, auteur)
        return Response({"ufr": UfrSerializer(ufr).data})


class GestionnaireCreateView(APIView):
    permission_classes = [require_roles("admin")]

    def post(self, request, ufr_id: str):
        nom = request.data.get("nom")
        prenom = request.data.get("prenom")
        if not nom or not prenom:
            raise ValidationError("Le nom et le prénom sont obligatoires.")

        auteur = f"{request.user.prenom} {request.user.nom}"
        resultat = services.create_gestionnaire(ufr_id, nom, prenom, auteur)
        return Response(
            {"identifiant": resultat["identifiant"], "ufr": UfrSerializer(resultat["ufr"]).data}, status=201
        )
