import logging

from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.models import Utilisateur
from notifications.models import NotificationItem

logger = logging.getLogger(__name__)


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
    enseignant_id: str,
    groupe_id_precedent: str | None = None,
    enseignant_id_precedent: str | None = None,
) -> None:
    """INV-06/FR-NOTIF-01 : une notification par utilisateur concerné,
    créée DANS la même transaction que l'écriture du créneau (appelé
    directement par planning/services.py, jamais après coup) — jamais
    "créneau enregistré mais notification perdue", ni l'inverse."""
    type_notification = "annule" if action == "annulation" else "modifie" if action == "modification" else "info"

    # FR-NOTIF-03/04 : "critique" gouverne seul l'envoi SMS (INT-04) — toute
    # annulation, ou un changement de salle sur une modification.
    critique = action == "annulation" or (action == "modification" and salle_changee)

    titre, description = _construire_texte(action, ue_intitule, jour, heure_debut, heure_fin, salle_nom, salle_changee)

    groupe_ids = [g for g in [groupe_id, groupe_id_precedent] if g]
    enseignant_ids = [e for e in [enseignant_id, enseignant_id_precedent] if e]

    utilisateurs = Utilisateur.objects.filter(
        models_q_etudiant_ou_enseignant(groupe_ids, enseignant_ids)
    ).values_list("id", flat=True)

    if not utilisateurs:
        logger.warning("Aucun utilisateur concerné trouvé pour le créneau %s.", creneau_id)
        return

    NotificationItem.objects.bulk_create(
        [
            NotificationItem(
                utilisateur_id=uid,
                type=type_notification,
                titre=titre,
                description=description,
                critique=critique,
                creneau_id=creneau_id,
            )
            for uid in utilisateurs
        ]
    )


def models_q_etudiant_ou_enseignant(groupe_ids: list[str], enseignant_ids: list[str]):
    from django.db.models import Q

    return Q(etudiant__groupe_id__in=groupe_ids) | Q(enseignant_id__in=enseignant_ids)


def _construire_texte(action, ue_intitule, jour, heure_debut, heure_fin, salle_nom, salle_changee):
    plage = f"{jour} {heure_debut}-{heure_fin}"
    if action == "annulation":
        return "Cours annulé", f"{ue_intitule} annulé ({plage})."
    if action == "modification":
        if salle_changee:
            return "Modification d'horaire", f"{ue_intitule} déplacé, nouvelle salle : {salle_nom} ({plage})."
        return "Modification d'horaire", f"{ue_intitule} modifié ({plage})."
    return "Nouveau cours", f"{ue_intitule} ajouté à l'emploi du temps ({plage}, {salle_nom})."


def list_notifications(utilisateur_id: str):
    return NotificationItem.objects.filter(utilisateur_id=utilisateur_id).order_by("-date_heure")


def mark_read(notification_id: str, utilisateur_id: str) -> NotificationItem:
    try:
        notification = NotificationItem.objects.get(id=notification_id)
    except NotificationItem.DoesNotExist:
        raise NotFound("Notification introuvable.")
    if notification.utilisateur_id != utilisateur_id:
        raise PermissionDenied("Cette notification ne vous appartient pas.")
    notification.lue = True
    notification.save(update_fields=["lue"])
    return notification
