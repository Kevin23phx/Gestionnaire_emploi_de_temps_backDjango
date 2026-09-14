# Campus Manager — backend Django

Remplace le backend NestJS (`../backend/`, dépôt distinct appartenant à un
coéquipier) suite à une décision de la hiérarchie du projet. **Contrat API
strictement identique** : mêmes routes `/api/...`, mêmes formes JSON, même
mécanisme de session par cookie opaque (`cm_session`) — le frontend
(`../web/`) fonctionne sans aucune modification.

## Stack

- Django 6.1 + Django REST Framework
- PostgreSQL (psycopg 3)
- Authentification par session applicative maison (`accounts.Session`,
  jeton opaque hashé en SHA-256) — **pas** `django.contrib.auth` ni
  `django.contrib.sessions` (voir `config/settings.py` en tête de fichier
  pour le pourquoi).

## Structure des apps

| App | Rôle |
|---|---|
| `core` | `Ufr` (dont la période académique, `[V3]`), utilitaires partagés (`ufr_scope.py`, gestion d'erreurs) |
| `accounts` | Utilisateur, Session, Enseignant, EnseignantUfr |
| `ufr` | Création UFR + compte Gestionnaire (réservé Admin), période académique |
| `referentiel` | Groupes (dont leur **effectif saisi**, `[V3.1]`), salles, cours |
| `planning` + `conflict_engine` | Créneaux, séances annulées `[V3]`, moteur de conflits |
| **`public` `[V3]`** | **Surface publique non authentifiée** : cascade de recherche, projection du programme, flux iCalendar, alertes Web Push |
| `audit`, `dashboard`, `sync` | Journal d'audit, statistiques, synchronisation |

### `[V3]` La frontière `public` (2026-09-07)

L'app `public` est la seule ouverte sans authentification (`AllowAny` écrit
explicitement sur chaque vue ; le défaut du projet reste
`IsAuthenticatedCM`). Elle **ne réutilise aucun sérialiseur** de `planning`
ou `referentiel`, alors que le résultat s'en rapproche beaucoup aujourd'hui.

C'est une contrainte volontaire, et il faut résister à l'envie de la lever :
le jour où un champ sera ajouté à un sérialiseur partagé — un effectif
nominatif, un identifiant d'étudiant, n'importe quoi — il partirait sur
Internet sans qu'aucune relecture ne l'attrape, parce que rien dans le code
n'aurait signalé que ce sérialiseur a un pied dehors. Ici, la liste des
champs publiés est écrite en toutes lettres dans `public/services.py`, à un
seul endroit (INV-12, INT-10, NFR-SEC-03).

### `[V4]` Le programme est publié semaine par semaine (2026-09-09)

**Le changement de modèle le plus important du projet.** Jusqu'ici, un
`Creneau` portait un *jour de semaine* et se répétait pour tout un semestre —
hypothèse héritée des universités à programme semestriel. À l'UJKZ, c'est
l'inverse : l'emploi du temps sort en fin de semaine pour la semaine à venir,
et son contenu change d'une semaine à l'autre.

Le défaut se voyait dès le premier abonnement à un agenda réel : un cours
répété à l'identique de la rentrée aux examens, **vacances comprises**, sans
aucun moyen d'y remédier.

`Creneau.date` est donc une **date réelle**. Le jour de semaine reste
disponible pour l'affichage mais il est **dérivé** (`Creneau.jour`), jamais
stocké : deux champs pour la même information finissent toujours par diverger.

Ce qui disparaît avec la récurrence, et c'est une simplification nette :

| Supprimé | Pourquoi |
|---|---|
| `RRULE` dans le flux iCalendar | Chaque séance est un événement daté autonome |
| Période académique (`Ufr.periode_*`) | Plus rien à borner — et ces dates « varient souvent », personne ne pouvait les tenir à jour pour 12 établissements |
| Modèle `SeanceAnnulee` | Annuler la séance du 14 = annuler le créneau du 14 |
| Congés à exclure | Une semaine sans cours est une semaine sans programme publié |

**Le point sensible de la migration** (`planning.0004_v4_creneau_date`) est la
contrainte PostgreSQL anti-double-réservation (INV-02) : elle portait sur
`jour`, une colonne supprimée. Elle est **reconstruite sur `date`**, et sa
portée change en conséquence — deux cours dans la même salle un lundi ne
s'excluent plus que s'il s'agit du même lundi. C'est correct sous le nouveau
modèle et ça l'aurait été faux sous l'ancien.

Le dimanche est refusé à la saisie (`_valider_date`) : il n'y a pas cours ce
jour-là, et l'accepter rangerait la séance dans une colonne que la grille
n'affiche pas.

### `[V3.2]` 12 établissements, pas 5 UFR (2026-09-07)

Le référentiel officiel de l'UJKZ, reçu le 2026-09-07, recense **12
établissements** — 5 UFR, 6 instituts (IBAM, ISSP, IFOAD, ISSDH, IGEDD,
IPERMIC) et 1 école doctorale (EDICC) — et **53 départements**. La V2 avait
délibérément restreint le périmètre aux 5 UFR ; c'est levé.

Les données de référence sont dans `core/donnees_ujkz.py`, reprises
**verbatim** du document émis par le responsable de la scolarité de l'UJKZ.
Elles ne doivent pas être « corrigées » depuis le code.

Deux paires d'intitulés ressemblent à des doublons — « Philosophie
-Psychologie » / « Pshychologie » (UFR/SH) et « Médecine et Spécialités
médicales » / « Medecine » (UFR/SDS). **Ce n'en sont pas** : ce sont des
filières à part entière, aux contenus différents (arbitrage de la scolarité
du 2026-09-07, consigné dans `ARBITRAGES`). Trois autres intitulés ont une
orthographe qui surprend et sont eux aussi repris tels quels
(`ORTHOGRAPHE_SOURCE`).

Ces deux listes existent pour une raison précise : sans elles, la prochaine
personne qui relira ce fichier « repérera » les mêmes anomalies et les
corrigera de bonne foi, fusionnant deux filières distinctes ou renommant un
intitulé officiel. Deux tests
(`test_les_filieres_proches_restent_distinctes`,
`test_l_orthographe_de_la_source_est_reprise_verbatim`) font échouer la
suite si quelqu'un s'y essaie.

Le seul point encore ouvert vient de **nous**, pas de la source : les noms
complets d'IBAM, ISSP, IFOAD et IPERMIC ne figuraient pas dans le document
(seul le sigle y était), les dénominations retenues sont les usuelles de
l'UJKZ et restent à confirmer (`NOMS_COMPLETS_A_CONFIRMER`, rappelé à
chaque seed).

**Le modèle s'appelle toujours `Ufr`, et sa table `ufr`**, alors qu'il
représente désormais un établissement de n'importe quel type. C'est un
compromis assumé : renommer traverserait les migrations, les quarante
fichiers qui manipulent `ufr_id`, la clause de cloisonnement INT-07 et le
contrat d'API que le frontend consomme — pour un gain purement lexical, au
milieu d'une série de changements fonctionnels. En revanche **toute chaîne
lue par un utilisateur dit « établissement »** : demander « votre UFR » à
un étudiant de l'IBAM n'aurait aucun sens, et c'est la première étape du
parcours public.

Le préfixe « UFR/ » n'est **jamais stocké** : il se dérive du type
(`Ufr.sigle_affiche` → « UFR/SH » mais « IBAM »). Un institut ne peut donc
pas se retrouver affiché « UFR/IBAM ».

Les départements alimentent la liste déroulante « Filière » du formulaire
de groupe, à la place de l'ancienne déduction depuis les groupes déjà
saisis. La différence est de fond : une liste déduite ne peut que se
dégrader — chaque faute de frappe y devient une filière de plus dans la
recherche publique — alors qu'un référentiel s'enrichit (l'option
« + Autre » enregistre le nouveau département, FR-REF-21).

### `[V3.1]` Le référentiel des étudiants a été supprimé (2026-09-07)

`Groupe.effectif` était un `COUNT(Etudiant)` : tenir cette valeur à jour
supposait d'importer et de maintenir la liste nominative des inscrits de
chaque groupe (INE, affectations, promotions d'une année sur l'autre). Or le
système n'en consommait **qu'une seule chose** : le nombre, comparé à la
capacité d'une salle (RM-02). Le porteur de projet a tranché — l'effectif
est désormais une **colonne saisie** par le Gestionnaire.

Ce qui disparaît avec : l'app-service `referentiel/services/etudiants.py`,
le modèle `Etudiant`, les routes `/api/etudiants*`, le canevas d'import
.xlsx, et le transfert d'étudiant entre UFR (FR-ADMIN-05, décision V2
annulée en connaissance de cause).

**Le point à comprendre**, et il est documenté dans `03_Contrat` (INV-16) :
une garantie du système devient une déclaration de son utilisateur. Le
moteur de conflits ne peut plus détecter qu'un effectif est faux ; il peut
seulement constater qu'il vaut zéro, auquel cas aucune alerte de capacité
ne sera jamais émise pour ce groupe. L'interface le signale explicitement
(ERR-10) plutôt que de laisser la découverte se faire devant un
amphithéâtre trop petit.

La migration `referentiel.0002_v31_effectif_saisi_suppression_etudiants`
**reprend l'effectif depuis le comptage existant avant** de supprimer la
table — sans quoi tous les groupes déjà en base repartiraient à zéro et la
détection de capacité s'éteindrait en silence.

### `[V3]` Apps supprimées

`demandes` et `notifications` ont été supprimées le 2026-09-07 :

- **`demandes`** : le circuit de signalement enseignant sort du périmètre
  (décision des responsables UJKZ — l'enseignant téléphone, le Gestionnaire
  corrige directement le programme). Voir `02_SRS` §2.7.
- **`notifications`** : ses destinataires étaient les comptes Étudiant et
  Enseignant, qui n'existent plus. Sa fonction de diffusion est reprise par
  `public/diffusion.py` (alerte Web Push, sans compte).

Leurs tables sont supprimées par la migration
`core.0002_v3_periode_academique_et_apps_retirees` — dans `core` et non dans
leur propre app, puisque celles-ci n'existent plus et que Django ne pourrait
donc plus exécuter une migration qui leur appartiendrait.

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # adapter si besoin

docker compose up -d
docker exec campus_manager_django_db psql -U postgres -c "CREATE DATABASE campus_manager_django_test;"

set -a; source .env; set +a
DATABASE_URL="$MIGRATE_DATABASE_URL" python manage.py migrate
bash scripts/bootstrap-db-roles.sh   # fixe le mot de passe du rôle applicatif restreint

set -a; source .env.test; set +a
DATABASE_URL="$MIGRATE_DATABASE_URL" ENV_FILE=.env.test python manage.py migrate
bash scripts/bootstrap-db-roles.sh
```

## Lancer le serveur

```bash
source venv/bin/activate
python manage.py runserver 0.0.0.0:3001
```

Le frontend (`../web/`, `NEXT_PUBLIC_API_URL=http://localhost:3001/api`) s'y
connecte sans configuration supplémentaire.

## Données

`scripts/seed.sh` a été retiré (2026-09-14) : la commande `manage.py seed`
qu'il appelait vide entièrement les tables avant de recréer un jeu de
démonstration — incompatible avec des données réelles saisies à la main en
cours de développement. La commande `seed` (`core/management/commands/`)
reste dans le code, mais uniquement comme fixture interne d'un test de
non-régression (`CoherenceSeedTests`, qui la rejoue contre la base de test
jetable pour vérifier que chaque département de groupe reste un département
officiel) — **elle ne doit plus être exécutée contre la base de
développement.**

## Tests

```bash
bash scripts/test.sh
```

96 tests (`tests/`) couvrant l'authentification, le RBAC par rôle, le
cloisonnement multi-UFR (création d'UFR/Gestionnaire, isolation du
référentiel/planning/audit entre UFR, affectation automatique d'un
enseignant jamais bloquante), le moteur de détection de conflits (salle,
enseignant, groupe, capacité, pauses fixes) et l'import/promotion
d'étudiants. Tourne avec le rôle superutilisateur car un test vérifie
explicitement les droits du rôle applicatif restreint via une connexion
séparée.

`[V3]` Deux fichiers portent les garanties nouvelles, et ce sont les plus
importants de la suite :

- `tests/test_public_surface.py` — ce que la surface publique doit montrer,
  et surtout ce qu'elle ne doit jamais laisser passer. Une erreur de
  périmètre n'expose plus une donnée au mauvais utilisateur connecté : elle
  l'expose à Internet.
- `tests/test_calendrier_ics.py` — le flux iCalendar, qu'on ne peut pas
  observer en local : une fois l'URL donnée au visiteur, c'est Google ou
  Apple qui la relit, et un détail de format faux ne produit aucune erreur
  visible. L'abonnement aurait simplement l'air de fonctionner sans jamais
  transmettre les changements.

`tests/test_seance_annulee.py` couvre l'annulation d'une séance datée
(FR-EDT-07/INV-14), devenue le geste le plus fréquent côté gestion, et
`tests/test_etablissements_departements.py` le référentiel officiel des
12 établissements et 53 départements (`[V3.2]`), y compris les garde-fous
qui empêchent de « corriger » les intitulés officiels.

## Invariants de sécurité au niveau base de données

Comme le backend NestJS de référence, deux garanties ne dépendent pas du
code applicatif :

- **Anti-double-réservation** (INV-02) : contrainte `EXCLUDE USING gist` sur
  `creneau` (migration `planning.0002_creneau_exclude_constraint`).
- **Audit immuable** (INV-04) : le rôle applicatif restreint
  (`campus_manager_django_app`) n'a physiquement pas les droits
  UPDATE/DELETE sur `audit_entry`/`conflit_journal` (migration
  `audit.0002_audit_and_journal_grants`) — les migrations elles-mêmes
  tournent toujours avec le rôle superutilisateur (`MIGRATE_DATABASE_URL`),
  jamais le rôle applicatif.

## `[V3]` Alertes Web Push (FR-PUB-08)

Le canal immédiat qui reste depuis la disparition des comptes. Optionnel :
sans clés VAPID configurées, tout le système fonctionne — programme public,
favoris, abonnement agenda — et les alertes sont simplement journalisées
(`PUSH_SENDER=console`, valeur par défaut).

```bash
venv/bin/vapid --gen          # génère une paire de clés (py-vapid)
# puis, dans .env :
#   PUSH_SENDER=webpush
#   VAPID_PUBLIC_KEY=...
#   VAPID_PRIVATE_KEY=...
```

Pourquoi ce canal existe alors que l'agenda est déjà abonné : Google Agenda
ne relit une URL iCalendar externe que toutes les 8 à 24 heures et ignore
largement `REFRESH-INTERVAL` (Apple et Outlook, eux, le respectent). Une
annulation annoncée le matin même n'y parviendrait donc pas à temps, ce qui
ferait perdre à lui seul l'exigence FR-NOTIF-01 (« moins d'une minute »).
C'est documenté comme tel dans `02_SRS` (FR-NOTIF-05) plutôt que passé sous
silence.

## Non repris de l'implémentation NestJS (limitation assumée)

Le mécanisme `LISTEN/NOTIFY` PostgreSQL + un "sender" de notification
console (`PgListenService` côté NestJS) n'a jamais eu de portée observable
pour le frontend (aucun canal temps réel réellement consommé) — non
ré-implémenté. `[V3]` Devenu sans objet depuis la suppression de l'app
`notifications`.
