from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import require_roles
from referentiel.serializers import EtudiantSerializer, GroupeSerializer, SalleSerializer, UniteEnseignementSerializer
from referentiel.services import cours as cours_service
from referentiel.services import etudiants as etudiants_service
from referentiel.services import groupes as groupes_service
from referentiel.services import salles as salles_service


def _requis(data: dict, *champs: str) -> None:
    for champ in champs:
        if not data.get(champ):
            raise ValidationError(f"Le champ '{champ}' est obligatoire.")


class GroupesView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite")()]
        return []

    def get(self, request):
        groupes = groupes_service.list_groupes(request.user, request.query_params.get("ufrId"))
        return Response({"groupes": GroupeSerializer(groupes, many=True).data})

    def post(self, request):
        _requis(request.data, "nom", "filiere", "niveau", "anneeAcademique")
        groupe = groupes_service.create_groupe(
            request.data["nom"],
            request.data["filiere"],
            request.data["niveau"],
            request.data["anneeAcademique"],
            request.user.ufr_id,
        )
        return Response({"groupe": GroupeSerializer(groupe).data}, status=201)


class SallesView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite", "admin")()]
        return []

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
        return []

    def get(self, request):
        cours = cours_service.list_cours(request.user, request.query_params.get("ufrId"))
        return Response({"cours": UniteEnseignementSerializer(cours, many=True).data})

    def post(self, request):
        _requis(request.data, "intitule", "niveau")
        ue = cours_service.create_cours(
            request.data["intitule"], request.data.get("code"), request.data["niveau"], request.user.ufr_id
        )
        return Response({"ue": UniteEnseignementSerializer(ue).data}, status=201)


class EtudiantsView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite")()]
        return []

    def get(self, request):
        etudiants = etudiants_service.list_etudiants(
            request.user,
            request.query_params.get("anneeAcademique"),
            request.query_params.get("filiere"),
            request.query_params.get("ufrId"),
        )
        return Response({"etudiants": EtudiantSerializer(etudiants, many=True).data})

    def post(self, request):
        lignes = request.data.get("etudiants")
        if not lignes or not isinstance(lignes, list):
            raise ValidationError("Aucun étudiant à importer.")
        resultat = etudiants_service.import_etudiants(lignes, request.data.get("groupeId"), request.user.ufr_id)
        return Response(
            {
                "etudiants": EtudiantSerializer(resultat["etudiants"], many=True).data,
                "doublons": resultat["doublons"],
                "invalides": resultat["invalides"],
            },
            status=201,
        )


class AffecterEtudiantsView(APIView):
    permission_classes = [require_roles("scolarite")]

    def post(self, request):
        etudiant_ids = request.data.get("etudiantIds")
        if not etudiant_ids or not isinstance(etudiant_ids, list):
            raise ValidationError("Aucun étudiant sélectionné.")
        # null = retirer du groupe ; absent n'est pas un cas valide.
        if "groupeId" not in request.data:
            raise ValidationError("Le champ 'groupeId' est obligatoire (null pour retirer du groupe).")
        etudiants = etudiants_service.affecter(etudiant_ids, request.data.get("groupeId"), request.user.ufr_id)
        return Response({"etudiants": EtudiantSerializer(etudiants, many=True).data}, status=201)


class TransfererUfrView(APIView):
    permission_classes = [require_roles("admin")]

    def post(self, request, etudiant_id: str):
        _requis(request.data, "ufrId")
        etudiant = etudiants_service.transferer_ufr(etudiant_id, request.data["ufrId"])
        return Response({"etudiant": EtudiantSerializer(etudiant).data}, status=201)
