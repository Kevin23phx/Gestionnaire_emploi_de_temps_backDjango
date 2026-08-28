"""
Le contrat API est TOUJOURS { erreur: "<message français>" } (jamais le
{detail: ...} par défaut de DRF) — équivalent direct de
backend/src/common/filters/http-exception.filter.ts et
prisma-exception.filter.ts.
"""

from django.db import IntegrityError
from django.http import Http404
from rest_framework import exceptions as drf_exceptions
from rest_framework.response import Response
from rest_framework.views import set_rollback


def _premier_message(detail) -> str:
    if isinstance(detail, dict):
        for valeur in detail.values():
            return _premier_message(valeur)
        return "Requête invalide."
    if isinstance(detail, (list, tuple)):
        return _premier_message(detail[0]) if detail else "Requête invalide."
    return str(detail)


def _erreur_integrite(exc: IntegrityError) -> tuple[int, str]:
    message = str(exc.__cause__ or exc)
    if "creneau_no_double_booking" in message or "exclusion_violation" in message.lower() or "23P01" in message:
        return 409, "Conflit détecté au niveau base de données — salle déjà réservée sur ce créneau."
    if "creneau_motif_requis_si_non_normal" in message or "23514" in message:
        return 400, "Le motif est obligatoire pour ce créneau."
    if "23505" in message or "duplicate key value" in message or "unique constraint" in message.lower():
        return 409, "Une ressource identique existe déjà."
    return 500, "Erreur interne."


def contrat_api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        return Response({"erreur": "Ressource introuvable."}, status=404)

    if isinstance(exc, IntegrityError):
        set_rollback()
        statut, message = _erreur_integrite(exc)
        return Response({"erreur": message}, status=statut)

    if isinstance(exc, drf_exceptions.APIException):
        set_rollback()
        detail = exc.detail
        # Un handler applicatif peut déjà avoir levé une exception avec un
        # corps complet ({erreur, conflits}, cf. planning) — ne jamais
        # l'écraser dans ce cas.
        if isinstance(detail, dict) and "erreur" in detail:
            return Response(detail, status=exc.status_code, headers=getattr(exc, "headers", {}))
        return Response({"erreur": _premier_message(detail)}, status=exc.status_code)

    return None
