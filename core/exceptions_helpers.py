from rest_framework.exceptions import APIException


class Conflict(APIException):
    """DRF n'a pas d'exception 409 intégrée — équivalent de
    NestJS ConflictException."""

    status_code = 409
    default_detail = "Conflit."


class ConflictWithBody(APIException):
    """Équivalent de `throw new ConflictException({erreur, conflits})` côté
    NestJS (PlanningService) : le corps complet est déjà au bon format,
    core.exceptions.contrat_api_exception_handler ne doit rien y ajouter."""

    status_code = 409

    def __init__(self, detail: dict):
        self.detail = detail
