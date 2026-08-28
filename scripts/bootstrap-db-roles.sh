#!/usr/bin/env bash
# Fixe le mot de passe du rôle applicatif restreint (campus_manager_django_app),
# créé par la migration audit.0002_audit_and_journal_grants (LOGIN, sans mot
# de passe défini au moment de sa création). Lit APP_DB_PASSWORD dans .env,
# jamais commité — même schéma que le backend NestJS de référence
# (backend/scripts/bootstrap-db-roles.sh).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "Erreur : .env introuvable (copiez .env.example puis remplissez-le)." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${MIGRATE_DATABASE_URL:?MIGRATE_DATABASE_URL manquant dans .env}"
: "${APP_DB_PASSWORD:?APP_DB_PASSWORD manquant dans .env}"

psql "$MIGRATE_DATABASE_URL" -v ON_ERROR_STOP=1 -c \
  "ALTER ROLE campus_manager_django_app WITH LOGIN PASSWORD '${APP_DB_PASSWORD}';"

echo "Rôle campus_manager_django_app configuré."
