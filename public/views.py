"""[V3] Surface publique — les seules vues du projet sans authentification.

`permission_classes = [AllowAny]` est écrit explicitement sur CHAQUE vue,
jamais hérité d'une base commune et jamais posé globalement : la valeur par
défaut du projet reste `IsAuthenticatedCM` (config/settings.py). Une route
publique est donc toujours une décision visible dans le diff, jamais un
oubli de décoration — l'erreur par défaut est un 401, pas une fuite
(cf. 04_Exigence_Architecture ligne 19).
"""

from django.conf import settings
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from public import ical, services
from public.models import AbonnementAlerte
from referentiel.models import Groupe


def _requis(params, *champs: str) -> None:
    for champ in champs:
        if not params.get(champ):
            raise ValidationError(f"Le paramètre '{champ}' est obligatoire.")


class UfrsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"ufrs": services.list_ufrs()})


class FilieresView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        _requis(request.query_params, "ufrId")
        return Response({"filieres": services.list_filieres(request.query_params["ufrId"])})


class NiveauxView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        _requis(request.query_params, "ufrId", "filiere")
        return Response(
            {"niveaux": services.list_niveaux(request.query_params["ufrId"], request.query_params["filiere"])}
        )


class GroupesView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        _requis(request.query_params, "ufrId", "filiere", "niveau")
        return Response(
            {
                "groupes": services.list_groupes(
                    request.query_params["ufrId"],
                    request.query_params["filiere"],
                    request.query_params["niveau"],
                )
            }
        )


class ProgrammeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, groupe_id: str):
        return Response(services.programme_semaine(groupe_id, request.query_params.get("semaine")))


class CalendrierView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, groupe_id: str):
        contenu = ical.calendrier_du_groupe(groupe_id)
        reponse = HttpResponse(contenu, content_type="text/calendar; charset=utf-8")
        # Un abonnement n'est pas un téléchargement : pas de
        # Content-Disposition attachment, qui ferait proposer au visiteur
        # d'enregistrer un fichier figé au lieu de s'abonner.
        # 5 minutes : assez pour absorber une rafale de requêtes, assez court
        # pour ne pas ajouter notre propre latence à celle, bien plus longue,
        # du fournisseur d'agenda (FR-NOTIF-05). Générer ce flux coûte une
        # requête SQL — il n'y a rien à gagner à le garder plus longtemps.
        reponse["Cache-Control"] = "public, max-age=300"
        return reponse


class CleAlerteView(APIView):
    """Clé publique VAPID — le navigateur en a besoin pour construire un
    abonnement. Publique par nature (c'est la moitié publique d'une paire de
    clés) ; renvoie null si le canal n'est pas configuré, ce que le front
    interprète en masquant simplement le bouton « M'alerter »."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"cle": settings.VAPID_PUBLIC_KEY or None})


class AlertesView(APIView):
    """FR-PUB-08 : la seule route publique qui écrive quelque chose.

    Elle n'écrit que dans sa propre table d'abonnements anonymes et ne peut
    toucher à aucune donnée du référentiel ou du planning — INV-05 (« aucune
    écriture anonyme sur les données du système ») reste vrai : un
    abonnement n'est pas une donnée du système, c'est une adresse de retour
    déposée par un appareil.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        groupe_id = request.data.get("groupeId")
        abonnement = request.data.get("abonnement") or {}
        endpoint = abonnement.get("endpoint")
        cles = abonnement.get("keys") or {}
        if not groupe_id or not endpoint or not cles.get("p256dh") or not cles.get("auth"):
            raise ValidationError("Abonnement incomplet.")
        if not Groupe.objects.filter(id=groupe_id).exists():
            raise ValidationError("Groupe inconnu.")

        AbonnementAlerte.objects.update_or_create(
            groupe_id=groupe_id,
            endpoint=endpoint,
            defaults={"cle_p256dh": cles["p256dh"], "cle_auth": cles["auth"]},
        )
        return Response(status=201)

    def delete(self, request):
        groupe_id = request.query_params.get("groupeId")
        endpoint = request.query_params.get("endpoint")
        if not groupe_id or not endpoint:
            raise ValidationError("groupeId et endpoint sont obligatoires.")
        AbonnementAlerte.objects.filter(groupe_id=groupe_id, endpoint=endpoint).delete()
        return Response(status=204)
