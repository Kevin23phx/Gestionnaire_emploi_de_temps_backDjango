from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import require_roles
from referentiel.serializers import (
    DepartementSerializer,
    GroupeSerializer,
    SalleSerializer,
    UniteEnseignementSerializer,
)
from referentiel.services import cours as cours_service
from referentiel.services import departements as departements_service
from referentiel.services import groupes as groupes_service
from referentiel.services import salles as salles_service


def _requis(data: dict, *champs: str) -> None:
    for champ in champs:
        if not data.get(champ):
            raise ValidationError(f"Le champ '{champ}' est obligatoire.")


class DepartementsView(APIView):
    """[V3.2] FR-REF-20/21 — les départements officiels de l'établissement.

    Source de la liste déroulante « Filière » à la création d'un groupe.
    GET ouvert à tout compte authentifié (l'Admin en a besoin pour la
    supervision) ; POST réservé au Gestionnaire, qui n'ouvre un département
    que dans SON propre établissement — l'ufr_id vient de la session,
    jamais de la requête (INT-07).
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite")()]
        return super().get_permissions()  # IsAuthenticatedCM par défaut

    def get(self, request):
        departements = departements_service.list_departements(request.user, request.query_params.get("ufrId"))
        return Response({"departements": DepartementSerializer(departements, many=True).data})

    def post(self, request):
        _requis(request.data, "libelle")
        departement = departements_service.create_departement(request.data["libelle"], request.user.ufr_id)
        return Response({"departement": DepartementSerializer(departement).data}, status=201)


class GroupesView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite")()]
        return super().get_permissions()  # IsAuthenticatedCM par défaut

    def get(self, request):
        groupes = groupes_service.list_groupes(request.user, request.query_params.get("ufrId"))
        return Response({"groupes": GroupeSerializer(groupes, many=True).data})

    def post(self, request):
        _requis(request.data, "nom", "departement", "niveau", "anneeAcademique")
        # "effectif" n'est pas dans _requis : 0 est une valeur légitime (un
        # groupe créé avant la rentrée), et `_requis` rejette tout ce qui est
        # falsy — il refuserait donc précisément ce cas.
        groupe = groupes_service.create_groupe(
            request.data["nom"],
            request.data["departement"],
            request.data["niveau"],
            request.data["anneeAcademique"],
            request.data.get("effectif", 0),
            request.user.ufr_id,
        )
        return Response({"groupe": GroupeSerializer(groupe).data}, status=201)


class GroupeDetailView(APIView):
    """[V3.1] Modification d'un groupe — en pratique surtout son effectif,
    qui bouge en cours d'année (abandons, inscriptions tardives). Sans cette
    route, la détection de conflit de capacité (RM-02) travaillerait sur la
    valeur saisie le jour de la création, et se tromperait de plus en plus."""

    permission_classes = [require_roles("scolarite")]

    def patch(self, request, groupe_id: str):
        groupe = groupes_service.update_groupe(groupe_id, request.data, request.user)
        return Response({"groupe": GroupeSerializer(groupe).data})


class GroupesPassageView(APIView):
    """[V6] FR-REF-12 — passage à l'année supérieure. Une seule requête pour
    toute la campagne (tout-ou-rien, cf. groupes_service.promouvoir_groupes) :
    le Gestionnaire réunit dans un même écran tous les groupes éligibles
    d'une année, ajuste chaque effectif, puis valide en bloc."""

    permission_classes = [require_roles("scolarite")]

    def post(self, request):
        _requis(request.data, "anneeAcademiqueCible", "groupes")
        groupes = groupes_service.promouvoir_groupes(
            request.data["groupes"], request.data["anneeAcademiqueCible"], request.user
        )
        return Response({"groupes": GroupeSerializer(groupes, many=True).data}, status=201)


class SallesView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite", "admin")()]
        return super().get_permissions()  # IsAuthenticatedCM par défaut

    def get(self, request):
        salles = salles_service.list_salles(request.user, request.query_params.get("ufrId"))
        return Response({"salles": SalleSerializer(salles, many=True).data})

    def post(self, request):
        _requis(request.data, "nom", "batiment", "capacite", "typeUsage")
        salle = salles_service.create_salle(
            request.data["nom"], request.data["batiment"], request.data["capacite"], request.data["typeUsage"], request.user
        )
        return Response({"salle": SalleSerializer(salle).data}, status=201)


class CoursView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite")()]
        return super().get_permissions()  # IsAuthenticatedCM par défaut

    def get(self, request):
        cours = cours_service.list_cours(request.user, request.query_params.get("ufrId"))
        return Response({"cours": UniteEnseignementSerializer(cours, many=True).data})

    def post(self, request):
        _requis(request.data, "intitule", "niveau")
        ue = cours_service.create_cours(
            request.data["intitule"],
            request.data.get("code"),
            request.data["niveau"],
            request.user.ufr_id,
            request.data.get("departementIds"),
        )
        return Response({"ue": UniteEnseignementSerializer(ue).data}, status=201)


class CoursDetailView(APIView):
    """[V3.3] Modification d'un cours — en pratique surtout le rattachement à
    ses départements, que les cours antérieurs à cette version n'ont pas."""

    permission_classes = [require_roles("scolarite")]

    def patch(self, request, cours_id: str):
        ue = cours_service.update_cours(cours_id, request.data, request.user)
        return Response({"ue": UniteEnseignementSerializer(ue).data})
