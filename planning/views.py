from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import require_roles
from planning import services


class CreneauxView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [require_roles("scolarite")()]
        return super().get_permissions()  # IsAuthenticatedCM par défaut

    def get(self, request):
        creneaux = services.list_creneaux(
            request.user,
            request.query_params.get("groupeId"),
            request.query_params.get("enseignantId"),
            request.query_params.get("ufrId"),
            # [V3] FR-FILT-01/06
            (request.query_params.get("recherche") or "").strip() or None,
        )
        return Response({"creneaux": creneaux})

    def post(self, request):
        items = request.data.get("creneaux")
        if not items or not isinstance(items, list):
            raise ValidationError("Aucun créneau à enregistrer.")
        auteur = f"{request.user.prenom} {request.user.nom}"
        ids = services.write_batch(items, auteur, request.user)
        return Response({"creneaux": [services.find_one(i) for i in ids]}, status=201)


class CreneauDetailView(APIView):
    def get(self, request, creneau_id: str):
        return Response(services.find_one(creneau_id))

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [require_roles("scolarite")()]
        return super().get_permissions()  # IsAuthenticatedCM par défaut

    def patch(self, request, creneau_id: str):
        auteur = f"{request.user.prenom} {request.user.nom}"
        item = {**request.data, "id": creneau_id}
        creneau_id = services.write_one(item, auteur, request.user)
        return Response(services.find_one(creneau_id))


class SeanceView(APIView):
    """[V3] FR-EDT-07 : annuler (POST) ou rétablir (DELETE) UNE séance datée.

    Route distincte de /creneaux/<id>/annuler, qui reste l'annulation de
    l'ensemble de la période (RM-10) — deux verbes différents pour deux
    actes différents, plutôt qu'un drapeau sur la même route qu'on finirait
    par oublier de renseigner."""

    permission_classes = [require_roles("scolarite")]

    def post(self, request, creneau_id: str):
        date = request.data.get("date")
        motif = request.data.get("motif")
        if not date:
            raise ValidationError("La date de la séance est obligatoire.")
        if not motif:
            raise ValidationError("Le motif est obligatoire.")
        auteur = f"{request.user.prenom} {request.user.nom}"
        return Response(services.annuler_seance(creneau_id, date, motif, auteur, request.user))

    def delete(self, request, creneau_id: str):
        date = request.query_params.get("date")
        if not date:
            raise ValidationError("La date de la séance est obligatoire.")
        auteur = f"{request.user.prenom} {request.user.nom}"
        return Response(services.retablir_seance(creneau_id, date, auteur, request.user))


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
