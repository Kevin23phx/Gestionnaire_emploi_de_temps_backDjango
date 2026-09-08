"""[V3.2] Référentiel officiel des établissements et départements de l'UJKZ.

Transmis par le porteur de projet le 2026-09-07 : 12 établissements
(5 UFR, 6 instituts, 1 école doctorale) et 53 départements. Remplace le
périmètre « 5 UFR » de la V2, qui excluait délibérément les instituts.

**Les libellés sont repris VERBATIM de la source, et doivent le rester.**
Ce fichier reproduit un document administratif émis par le responsable de
la scolarité de l'UJKZ : lui seul fait foi sur le découpage et sur les
intitulés. Toute « correction » apportée ici ferait diverger le référentiel
de sa source, silencieusement — voir `ARBITRAGES` en bas de fichier pour ce
qui a déjà été vérifié auprès de la scolarité, et ne pas y revenir.

"sigle" est le code court en minuscules : il sert d'identifiant technique
(`ufr-<sigle>`) et d'identifiant de compte (`scolarite.<sigle>`). Il doit
rester stable — le changer casserait les comptes existants.
"""

from core.models import TypeEtablissement

UFR = TypeEtablissement.UFR
INSTITUT = TypeEtablissement.INSTITUT
ECOLE_DOCTORALE = TypeEtablissement.ECOLE_DOCTORALE

# (sigle, nom officiel, type, [départements])
ETABLISSEMENTS: list[tuple[str, str, str, list[str]]] = [
    (
        "sh",
        "UFR Sciences Humaines",
        UFR,
        [
            "Histoire et Archéologie",
            "Géographie",
            "Sociologie",
            "Philosophie -Psychologie",
            "Pshychologie",
            "Développement et Education Des Adultes",
        ],
    ),
    (
        "lac",
        "UFR Lettres, Arts et Communication",
        UFR,
        [
            "Lettres Modernes (LM)",
            "Traduction et Interprétation",
            "Etudes anglophones",
            "Etudes germaniques",
            "Linguistique",
            "Langues Appliquées au Tourisme et aux Affaires",
            "Arts, Gestion et Administration Culturelle",
            "Etudes Arabophones et des Langues Orientales",
        ],
    ),
    (
        "sds",
        "UFR Sciences de la Santé",
        UFR,
        [
            "Médecine et Spécialités médicales",
            "Chirurgie et Spécialités Chirurgicales",
            "Gynécologie Obstétrique",
            "Pédiatrie",
            "Sciences Fondamentales et Mixtes",
            "Santé Publique",
            "Sciences Biologiques Appliquées",
            "Sciences Pharmaceutiques Appliquées",
            "Sciences fondamentales et Physico-Chimiques",
            "Medecine",
            "Pharmacie",
            "Chirurgie dentaire",
            "TSS",
        ],
    ),
    (
        "sea",
        "UFR Sciences Exactes et Appliquées",
        UFR,
        ["Physique", "Mathématique", "Chimie", "Informatique", "Tronc Commun SEA"],
    ),
    (
        "svt",
        "UFR Sciences de la Vie et de la Terre",
        UFR,
        [
            "Biochimie et microbiologie",
            "Biologie Animale Physiologie Animale",
            "Biologie Végétale Physiologie Végatle",
            "Sciences de la Terre",
            "Centre d'Etudes pour la Promotion, l'Aménagement et la Protection de l'Environnement",
            "Tron Commun Sciences et Technologies",
        ],
    ),
    (
        "ibam",
        "Institut Burkinabè des Arts et Métiers",
        INSTITUT,
        ["IBAM", "Gestion", "Technique Administrative", "Informatique Multimédia et Télécom"],
    ),
    (
        "issp",
        "Institut Supérieur des Sciences de la Population",
        INSTITUT,
        ["Statistique", "Démographie"],
    ),
    ("ifoad", "Institut de Formation Ouverte et À Distance", INSTITUT, ["IFOAD"]),
    (
        "issdh",
        "Institut des Sciences du Sport et du Développement Humain",
        INSTITUT,
        ["STAPS", "Sciences et Techniques des Activités Socio-Éducatives"],
    ),
    (
        "igedd",
        "Institut de Génie de l'Environnement et du Développement Durable",
        INSTITUT,
        [
            "Eau et Assainissement",
            "Qualité, Gestion des Risques Environnementaux",
            "Energie",
            "Ingénierie et Gestion des Ressources Naturelles",
        ],
    ),
    (
        "ipermic",
        "Institut Panafricain d'Étude et de Recherche sur les Médias, l'Information et la Communication",
        INSTITUT,
        ["IPERMIC"],
    ),
    ("edicc", "École Doctorale Informatique et Changement Climatique", ECOLE_DOCTORALE, ["Informatique et Changement Cimatique"]),
]


# ---------------------------------------------------------------------------
# Arbitrages rendus par la scolarité — NE PAS REVENIR DESSUS
# ---------------------------------------------------------------------------
# Plusieurs entrées ci-dessus ressemblent, pour un œil extérieur, à des
# doublons ou à des coquilles. Elles ont été soumises au porteur de projet
# le 2026-09-07 et tranchées : **ce sont des filières à part entière, aux
# contenus différents**, et la liste vient directement du responsable de la
# scolarité.
#
# Ce bloc existe pour une raison précise : sans lui, la prochaine personne —
# ou la prochaine session — qui relira ce fichier « repérera » les mêmes
# anomalies et les corrigera de bonne foi, fusionnant deux filières
# distinctes ou renommant un intitulé officiel. La question a été posée une
# fois ; la réponse est ici.
ARBITRAGES = [
    (
        "sh",
        ("Philosophie -Psychologie", "Pshychologie"),
        "Deux départements distincts, pas un doublon : les contenus diffèrent. "
        "Arbitrage scolarité du 2026-09-07.",
    ),
    (
        "sds",
        ("Médecine et Spécialités médicales", "Medecine"),
        "Deux départements distincts, pas un doublon : les contenus diffèrent. "
        "Arbitrage scolarité du 2026-09-07.",
    ),
]

# Intitulés dont l'orthographe surprend mais qui sont repris tels quels de la
# source officielle. Ils ne sont PAS des erreurs à corriger de notre côté :
# si la scolarité les rectifie un jour dans son document, la mise à jour se
# fera ici, en une ligne, à partir de la nouvelle version du document.
ORTHOGRAPHE_SOURCE = [
    ("svt", "Biologie Végétale Physiologie Végatle"),
    ("svt", "Tron Commun Sciences et Technologies"),
    ("edicc", "Informatique et Changement Cimatique"),
]

# Le seul point encore ouvert, et il vient de NOUS, pas de la source : les
# noms complets d'IBAM, ISSP, IFOAD et IPERMIC ne figuraient pas dans le
# document transmis (seul le sigle y était). Les dénominations retenues
# ci-dessus sont les usuelles de l'UJKZ, à faire confirmer. Idem pour
# "École Doctorale Informatique et Changement Climatique", dont le nom que
# nous avons composé écrit "Climatique" là où son département officiel
# écrit "Cimatique".
NOMS_COMPLETS_A_CONFIRMER = ["ibam", "issp", "ifoad", "ipermic", "edicc"]
