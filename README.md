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

Chaque app Django reprend un module du backend NestJS d'origine :

| App | Équivalent NestJS |
|---|---|
| `core` | `Ufr` (modèle), utilitaires partagés (`ufr_scope.py`, gestion d'erreurs) |
| `accounts` | `auth/` + `accounts/` (Utilisateur, Session, Enseignant, EnseignantUfr) |
| `ufr` | `ufr/` (création UFR + compte Gestionnaire, réservé Admin) |
| `referentiel` | `referentiel/{groupes,salles,cours,etudiants}/` |
| `planning` + `conflict_engine` | `planning/` + `conflict-engine/` |
| `audit`, `demandes`, `notifications`, `dashboard`, `sync` | modules éponymes |

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

## Données de démonstration

```bash
bash scripts/seed.sh
```

Comptes créés (mot de passe `password` pour tous) : voir la sortie du script
— un admin (`scolarite.general`), un Gestionnaire par UFR
(`scolarite.sh/sds/svt/sea/lac`), un étudiant et un enseignant de démo.

## Tests

```bash
bash scripts/test.sh
```

55 tests (`tests/`) couvrant l'authentification, le RBAC par rôle, le
cloisonnement multi-UFR (création d'UFR/Gestionnaire, isolation du
référentiel/planning/audit entre UFR, affectation automatique d'un
enseignant jamais bloquante), le moteur de détection de conflits (salle,
enseignant, groupe, capacité, pauses fixes), l'import/promotion d'étudiants,
et le circuit de validation des demandes enseignant. Tourne avec le rôle
superutilisateur (comme `scripts/seed.sh`) car un test vérifie explicitement
les droits du rôle applicatif restreint via une connexion séparée.

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

## Non repris de l'implémentation NestJS (limitation assumée)

Le mécanisme `LISTEN/NOTIFY` PostgreSQL + un "sender" de notification
console (`PgListenService` côté NestJS) n'a pas de portée observable pour le
frontend actuel (aucun canal temps réel réellement consommé, `GET
/notifications` suffit) — non ré-implémenté ici. Les `NotificationItem`
elles-mêmes sont bien créées, dans la même transaction que le créneau
(INV-06), exactement comme avant.
