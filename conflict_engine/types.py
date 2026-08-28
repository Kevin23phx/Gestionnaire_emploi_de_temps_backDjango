from dataclasses import dataclass


@dataclass
class CandidateCreneau:
    """Forme minimale nécessaire pour comparer/décrire un créneau —
    délibérément découplée du modèle Django complet ("effectif" n'est
    jamais une colonne mais toujours une valeur calculée fournie ici)."""

    id: str
    jour: str
    heure_debut_minutes: int
    heure_fin_minutes: int
    statut: str
    ue_intitule: str
    enseignant_id: str
    enseignant_nom: str
    enseignant_prenom: str
    groupe_id: str
    groupe_nom: str
    groupe_effectif: int
    salle_id: str
    salle_nom: str
    salle_capacite: int


@dataclass
class ConflitDetecteResult:
    type: str
    gravite: str
    titre: str
    description: str
    creneau_a_id: str
    creneau_b_id: str | None
