"""[V3] Diffusion d'un changement de programme (INV-06, FR-PUB-08, FR-NOTIF-01).

Remplace l'ancien `notifications/services.py`, dont tout le travail
consistait à résoudre des destinataires nominatifs — « quels comptes
Étudiant sont dans ce groupe, quel compte Enseignant assure ce cours ». Ce
travail n'a plus d'objet : il n'y a plus de comptes, et le programme public
est lui-même le message. Ce qui reste ici est le seul canal réellement
immédiat dont dispose encore le système, l'alerte navigateur.

Appelé DANS la transaction d'écriture du créneau, jamais après (INV-06) :
« créneau enregistré mais changement non diffusé » ne doit pas exister. En
contrepartie, l'envoi réseau ne doit jamais faire échouer l'écriture — une
annulation valide ne peut pas être perdue parce qu'un service de push tiers
répond mal. D'où le `try` large autour de l'envoi, et lui seul.
"""

import json
import logging

from django.conf import settings

from public.models import AbonnementAlerte

logger = logging.getLogger(__name__)


def _envoyer(abonnements, charge: dict) -> None:
    """Deux expéditeurs : `console` (défaut, développement) et `webpush`.

    Le défaut est volontairement l'expéditeur inerte : sans clés VAPID
    configurées, le système doit fonctionner de bout en bout — programme
    public, favoris, agenda — et se contenter de journaliser les alertes.
    Faire dépendre le démarrage d'une paire de clés reviendrait à rendre le
    déploiement plus fragile que le service rendu par ce canal.
    """
    if not abonnements:
        return

    if settings.PUSH_SENDER != "webpush":
        logger.info("[push:console] %s destinataire(s) — %s", len(abonnements), charge["titre"])
        return

    from pywebpush import WebPushException, webpush

    perimes = []
    for abonnement in abonnements:
        try:
            webpush(
                subscription_info={
                    "endpoint": abonnement.endpoint,
                    "keys": {"p256dh": abonnement.cle_p256dh, "auth": abonnement.cle_auth},
                },
                data=json.dumps(charge),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
            )
        except WebPushException as exc:
            # 404/410 = l'appareil a désinstallé la PWA ou révoqué la
            # permission. L'abonnement ne redeviendra jamais valide : le
            # garder ferait grossir la table indéfiniment et ralentirait
            # chaque diffusion ultérieure.
            statut = getattr(exc.response, "status_code", None)
            if statut in (404, 410):
                perimes.append(abonnement.id)
            else:
                logger.warning("Échec d'envoi d'alerte (%s) : %s", statut, exc)
        except Exception:  # noqa: BLE001
            logger.exception("Échec inattendu d'envoi d'alerte — l'écriture du créneau n'est pas remise en cause")

    if perimes:
        AbonnementAlerte.objects.filter(id__in=perimes).delete()


def _abonnes(groupe_ids: list[str]):
    ids = [g for g in groupe_ids if g]
    if not ids:
        return []
    return list(AbonnementAlerte.objects.filter(groupe_id__in=ids))


def on_creneau_changed(
    *,
    creneau_id: str,
    action: str,
    ue_intitule: str,
    jour: str,
    heure_debut: str,
    heure_fin: str,
    salle_nom: str,
    salle_changee: bool,
    groupe_id: str,
    groupe_id_precedent: str | None = None,
) -> None:
    plage = f"{jour} {heure_debut}-{heure_fin}"
    if action == "annulation":
        titre, corps = "Cours annulé", f"{ue_intitule} annulé ({plage})."
    elif action == "modification":
        titre = "Modification d'horaire"
        corps = (
            f"{ue_intitule} déplacé, nouvelle salle : {salle_nom} ({plage})."
            if salle_changee
            else f"{ue_intitule} modifié ({plage})."
        )
    else:
        titre, corps = "Nouveau cours", f"{ue_intitule} ajouté ({plage}, {salle_nom})."

    # Le groupe précédent est prévenu lui aussi quand un créneau change de
    # groupe : ses abonnés viennent de perdre un cours sans que rien n'ait
    # bougé de leur côté.
    _envoyer(
        _abonnes([groupe_id, groupe_id_precedent]),
        {"titre": titre, "corps": corps, "groupeId": groupe_id, "creneauId": creneau_id},
    )


def on_seance_annulee(*, creneau_id: str, groupe_id: str, ue_intitule: str, date: str) -> None:
    _envoyer(
        _abonnes([groupe_id]),
        {
            "titre": "Séance annulée",
            "corps": f"{ue_intitule} — séance du {date} annulée.",
            "groupeId": groupe_id,
            "creneauId": creneau_id,
        },
    )
