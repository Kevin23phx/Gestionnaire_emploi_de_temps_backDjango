from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from audit import services as audit_services
from core.exceptions_helpers import Conflict
from core.time_utils import hhmm_to_minutes, minutes_to_hhmm
from core.ufr_scope import resolve_ufr_scope
from demandes.models import DemandeEnseignant
from planning import services as planning_services
from planning.models import Creneau
from planning.services import EXEMPTION_TECHNIQUE_PERMUTATION

# Module sans aucune implémentation préalable côté mock — les choix
# d'interprétation ci-dessous sont documentés faute de contrat préexistant.
#
# - "report" propose une plage totalement nouvelle (jour/heure/salle).
# - "permutation" échange (jour, heure, salle) entre deux créneaux déjà
#   existants ; chacun garde son propre UE/enseignant/groupe.
# - RM-04 : la seule transition légale est en_attente -> {validee, refusee},
#   appliquée via un UPDATE conditionné sur le statut courant.


def create(enseignant_id: str, dto: dict) -> DemandeEnseignant:
    if dto["type"] == "report":
        if not dto.get("jourPropose") or not dto.get("heureDebutProposee") or not dto.get("heureFinProposee"):
            raise ValidationError("Un report nécessite un jour, une heure de début et une heure de fin proposés.")
    if dto["type"] == "permutation" and not dto.get("creneauProposeId"):
        raise ValidationError("Une permutation nécessite un créneau proposé.")

    if not Creneau.objects.filter(id=dto["creneauConcerneId"]).exists():
        raise NotFound("Créneau concerné introuvable.")

    return DemandeEnseignant.objects.create(
        enseignant_id=enseignant_id,
        type=dto["type"],
        motif=dto["motif"],
        creneau_concerne_id=dto["creneauConcerneId"],
        jour_propose=dto.get("jourPropose"),
        heure_debut_proposee_minutes=hhmm_to_minutes(dto["heureDebutProposee"]) if dto.get("heureDebutProposee") else None,
        heure_fin_proposee_minutes=hhmm_to_minutes(dto["heureFinProposee"]) if dto.get("heureFinProposee") else None,
        salle_proposee_id=dto.get("salleProposeeId"),
        creneau_propose_id=dto.get("creneauProposeId"),
    )


def list_demandes(user):
    """INT-07 (V2) : un Gestionnaire ne voit que les demandes dont le
    créneau concerné appartient à sa propre UFR (via son groupe) ; un
    Enseignant ne voit que les siennes."""
    if user.role == "enseignant":
        enseignant_id = user.enseignant.id if user.enseignant else "__aucun__"
        qs = DemandeEnseignant.objects.filter(enseignant_id=enseignant_id)
    else:
        scope = resolve_ufr_scope(user)
        qs = DemandeEnseignant.objects.all()
        if not scope.toutes:
            qs = qs.filter(creneau_concerne__groupe__ufr_id__in=scope.ufr_ids)
    return qs.select_related("enseignant").order_by("-created_at")


@transaction.atomic
def decider(demande_id: str, dto: dict, decideur) -> DemandeEnseignant:
    try:
        demande = DemandeEnseignant.objects.select_related(
            "creneau_concerne__groupe", "creneau_propose__groupe"
        ).get(id=demande_id)
    except DemandeEnseignant.DoesNotExist:
        raise NotFound("Demande introuvable.")

    if decideur.role == "scolarite" and (
        demande.creneau_concerne.groupe.ufr_id != decideur.ufr_id
        or (demande.creneau_propose and demande.creneau_propose.groupe.ufr_id != decideur.ufr_id)
    ):
        raise PermissionDenied("Cette demande concerne une autre UFR.")

    auteur = f"{decideur.prenom} {decideur.nom}"

    transition = DemandeEnseignant.objects.filter(id=demande_id, statut="en_attente").update(
        statut=dto["decision"],
        motif_decision=dto.get("motifDecision"),
        decide_par_id=decideur.id,
        decide_le=timezone.now(),
    )
    if transition == 0:
        raise Conflict("Cette demande a déjà été décidée.")

    if dto["decision"] == "refusee":
        audit_services.record(auteur, f"Refus demande ({demande.type})", dto.get("motifDecision") or demande.motif)
        return DemandeEnseignant.objects.select_related("enseignant").get(id=demande_id)

    creneau_id_a_ecrire = None
    creneau_id_a_ecrire2 = None

    if demande.type == "absence":
        item = planning_services.charger_comme_dto(demande.creneau_concerne_id)
        creneau_id_a_ecrire = planning_services.write_one_in_transaction(
            {**item, "statut": "annule", "motif": dto.get("motifDecision") or demande.motif, "motifDerogation": dto.get("motifDerogation")},
            auteur,
            [],
            decideur,
        )
    elif demande.type == "report":
        item = planning_services.charger_comme_dto(demande.creneau_concerne_id)
        creneau_id_a_ecrire = planning_services.write_one_in_transaction(
            {
                **item,
                # Pas de salle proposée par l'enseignant (FR-REF-02 : seule
                # la scolarité assigne une salle) — la salle actuelle du
                # créneau est conservée par défaut.
                "salleId": demande.salle_proposee_id or item["salleId"],
                "jour": demande.jour_propose,
                "heureDebut": minutes_to_hhmm(demande.heure_debut_proposee_minutes),
                "heureFin": minutes_to_hhmm(demande.heure_fin_proposee_minutes),
                "statut": "modifie",
                "motif": dto.get("motifDecision") or demande.motif,
                "motifDerogation": dto.get("motifDerogation"),
            },
            auteur,
            [],
            decideur,
        )
    elif demande.type == "permutation":
        if not demande.creneau_propose_id:
            raise ValidationError("Aucun créneau proposé pour cette permutation.")
        a = planning_services.charger_comme_dto(demande.creneau_concerne_id)
        b = planning_services.charger_comme_dto(demande.creneau_propose_id)

        creneau_id_a_ecrire = planning_services.write_one_in_transaction(
            {
                **a,
                "jour": b["jour"],
                "heureDebut": b["heureDebut"],
                "heureFin": b["heureFin"],
                "salleId": b["salleId"],
                "motif": dto.get("motifDecision") or demande.motif,
                "motifDerogation": dto.get("motifDerogation"),
            },
            auteur,
            [demande.creneau_propose_id],
            decideur,
        )
        creneau_id_a_ecrire2 = planning_services.write_one_in_transaction(
            {
                **b,
                "jour": a["jour"],
                "heureDebut": a["heureDebut"],
                "heureFin": a["heureFin"],
                "salleId": a["salleId"],
                "motif": dto.get("motifDecision") or demande.motif,
                "motifDerogation": dto.get("motifDerogation"),
            },
            auteur,
            [demande.creneau_concerne_id],
            decideur,
        )

        # Les deux créneaux sont maintenant dans leur état final : l'exemption
        # technique posée pour franchir l'état intermédiaire n'a plus lieu
        # d'être.
        Creneau.objects.filter(
            id__in=[i for i in [creneau_id_a_ecrire, creneau_id_a_ecrire2] if i],
            derogation_motif=EXEMPTION_TECHNIQUE_PERMUTATION,
        ).update(derogation_motif=None)

    return DemandeEnseignant.objects.select_related("enseignant").get(id=demande_id)
