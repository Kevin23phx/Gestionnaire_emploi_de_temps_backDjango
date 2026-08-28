#!/usr/bin/env bash
# Le seed vide entièrement les tables (y compris audit_entry/conflit_journal,
# append-only pour l'application elle-même) : il tourne donc avec le rôle
# superutilisateur (MIGRATE_DATABASE_URL), jamais le rôle restreint de
# l'application (DATABASE_URL).
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate

if [ ! -f .env ]; then
  echo "Erreur : .env introuvable (copiez .env.example puis remplissez-le)." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

: "${MIGRATE_DATABASE_URL:?MIGRATE_DATABASE_URL manquant dans .env}"

DATABASE_URL="$MIGRATE_DATABASE_URL" python manage.py seed
