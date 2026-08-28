from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import require_roles
from planning import services


class CreneauxView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite")()]
        return []

    def get(self, request):
        creneaux = services.list_creneaux(
            request.user,
            request.query_params.get("groupeId"),
            request.query_params.get("enseignantId"),
            request.query_params.get("ufrId"),
        )
        return Response({"creneaux": creneaux})

    def post(self, request):
        items = request.data.get("creneaux")
        if not items or not isinstance(items, list):
            raise ValidationError("Aucun créneau à enregistrer.")
        auteur = f"{request.user.prenom} {request.user.nom}"
        ids = services.write_batch(items, auteur, request.user)
        return Response({"creneaux": [services.find_one(i) for i in ids]}, status=201)


class ProgrammeCompletView(APIView):
    permission_classes = [require_roles("enseignant", "scolarite")]

    def get(self, request):
        return Response({"creneaux": services.list_programme_complet(request.user)})


class CreneauDetailView(APIView):
    def get(self, request, creneau_id: str):
        return Response(services.find_one(creneau_id))

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [require_roles("scolarite")()]
        return []

    def patch(self, request, creneau_id: str):
        auteur = f"{request.user.prenom} {request.user.nom}"
        item = {**request.data, "id": creneau_id}
        creneau_id = services.write_one(item, auteur, request.user)
        return Response(services.find_one(creneau_id))


class VerifierView(APIView):
    permission_classes = [require_roles("scolarite")]

    def post(self, request):
        items = request.data.get("creneaux")
        if not items or not isinstance(items, list):
            raise ValidationError("Aucun créneau à enregistrer.")
        return Response({"conflits": services.verifier(items)})


class AnnulerView(APIView):
    permission_classes = [require_roles("scolarite")]

    def post(self, request, creneau_id: str):
        motif = request.data.get("motif")
        if not motif:
            raise ValidationError("Le motif est obligatoire.")
        auteur = f"{request.user.prenom} {request.user.nom}"
        creneau_id = services.annuler(creneau_id, motif, auteur, request.user)
        return Response(services.find_one(creneau_id))
