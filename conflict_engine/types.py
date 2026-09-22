from dataclasses import dataclass


@dataclass
class CandidateCreneau:
    """Forme minimale nécessaire pour comparer/décrire un créneau —
    délibérément découplée du modèle Django complet ("effectif" n'est
    jamais une colonne mais toujours une valeur calculée fournie ici)."""

    id: str
    date: str  # [V4] ISO — deux cours ne s'opposent que s'ils sont le MÊME JOUR, pas le même jour de semaine
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

    # [V8.1] Spécialité à laquelle ce créneau est affecté ; vide = tout le
    # groupe. Elle entre dans la comparaison de conflit « groupe » — voir
    # `_memes_etudiants` dans services.py.
    #
    # EN DERNIER, et pas à côté des autres champs du groupe où sa place
    # logique serait : un champ à valeur par défaut ne peut pas précéder un
    # champ qui n'en a pas dans une dataclass (Python lève à l'import).
    #
    # Un défaut vide signifie « concerne tout le groupe », c'est-à-dire
    # exactement le comportement d'avant la V8.1. Un appelant qui oublierait
    # l'argument retrouve donc l'ancienne règle, la plus stricte : il fait
    # détecter un conflit de trop, jamais un conflit de moins.
    specialite: str = ""


@dataclass
class ConflitDetecteResult:
    type: str
    gravite: str
    titre: str
    description: str
    creneau_a_id: str
    creneau_b_id: str | None
