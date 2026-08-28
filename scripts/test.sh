#!/usr/bin/env bash
# Les tests tournent avec le rôle superutilisateur (comme le seed) : Django
# a besoin de créer/modifier la structure de la base de test à la demande,
# et un test vérifie explicitement les droits du rôle applicatif restreint
# via une connexion psycopg séparée (voir tests/test_audit_immutability.py).
set -euo pipefail
cd "$(dirname "$0")/.."
source venv/bin/activate

if [ ! -f .env.test ]; then
  echo "Erreur : .env.test introuvable." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env.test
set +a

: "${MIGRATE_DATABASE_URL:?MIGRATE_DATABASE_URL manquant dans .env.test}"

DATABASE_URL="$MIGRATE_DATABASE_URL" python manage.py test tests --keepdb "$@"
