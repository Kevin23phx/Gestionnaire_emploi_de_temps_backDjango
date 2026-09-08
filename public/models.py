from django.db import models

from core.utils import generate_id
from referentiel.models import Groupe


class AbonnementAlerte(models.Model):
    """[V3] FR-PUB-08 : abonnement Web Push d'un visiteur à UN groupe.

    Ce modèle est la seule chose que le système retienne d'un visiteur, et
    c'est délibérément le strict minimum technique nécessaire pour lui faire
    parvenir une alerte : l'adresse opaque fournie par son navigateur et les
    deux clés de chiffrement associées. Aucun nom, aucun INE, aucun lien
    avec le référentiel des étudiants (INT-10) — le système ne sait pas, et
    ne doit pas savoir, QUI est abonné, seulement qu'un appareil quelque
    part attend des nouvelles de tel groupe.

    Conséquence assumée : on ne peut pas "retrouver ses alertes" depuis un
    autre appareil, exactement comme pour les favoris (FR-PUB-04). C'est le
    prix de l'absence de compte, et c'était le choix.
    """

    id = models.CharField(primary_key=True, max_length=64, default=generate_id, editable=False)
    groupe = models.ForeignKey(Groupe, related_name="abonnements_alerte", on_delete=models.CASCADE)

    # L'endpoint identifie l'appareil auprès de son service de push. Unique
    # par (appareil, groupe) : un même téléphone peut suivre plusieurs
    # groupes, mais jamais deux fois le même.
    endpoint = models.TextField()
    cle_p256dh = models.CharField(max_length=255)
    cle_auth = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "abonnement_alerte"
        indexes = [models.Index(fields=["groupe"])]
        constraints = [
            models.UniqueConstraint(fields=["groupe", "endpoint"], name="abonnement_alerte_unique"),
        ]

    def __str__(self) -> str:
        return f"alerte {self.groupe_id}"
