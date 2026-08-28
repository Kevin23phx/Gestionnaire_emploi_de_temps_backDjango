"""
Campus Manager API — backend Django (remplace le backend NestJS de
`backend/`, dépôt distinct appartenant à un coéquipier — voir mémoire de
session). Contrat API strictement identique : mêmes routes /api/..., mêmes
formes JSON, même mécanisme de session par cookie opaque `cm_session`.

Ce projet n'utilise PAS le système d'auth/session natif de Django
(django.contrib.auth, django.contrib.sessions) : le modèle `Utilisateur`
(accounts/models.py) et le modèle `Session` (jeton opaque, hashé en base,
jamais stocké en clair) sont une traduction directe du schéma Prisma
existant, pour préserver exactement le même contrat et la même sémantique
de sécurité (cf. backend/prisma/schema.prisma).
"""

import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / (os.environ.get("ENV_FILE") or ".env"))

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-production")
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "corsheaders",
    "core",
    "accounts",
    "ufr",
    "referentiel",
    "planning",
    "conflict_engine",
    "audit",
    "demandes",
    "notifications",
    "dashboard",
    "sync",
]

# Pas de CsrfViewMiddleware ni de SessionMiddleware Django : l'authentification
# repose entièrement sur accounts.authentication.CookieSessionAuthentication
# (jeton opaque en cookie, jamais le framework de session Django) — exactement
# le même choix que le backend NestJS (pas de CSRF token requis par le
# frontend actuel, cf. web/src/lib/api.ts).
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def _database_from_url(url: str) -> dict:
    parsed = urlparse(url)
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": parsed.username,
        "PASSWORD": parsed.password,
        "HOST": parsed.hostname,
        "PORT": parsed.port,
    }


DATABASES = {
    "default": _database_from_url(
        os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5436/campus_manager_django")
    )
}
# Base de test PERSISTANTE (campus_manager_django_test), pas la base
# éphémère "test_<name>" que Django créerait par défaut — même approche que
# le backend NestJS de référence (campus_manager_test, déjà migrée une fois,
# réutilisée à chaque run via `manage.py test --keepdb`).
DATABASES["default"]["TEST"] = {"NAME": DATABASES["default"]["NAME"]}

USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "fr-fr"
USE_I18N = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Le frontend (web/src/lib/api.ts) appelle toujours des chemins SANS slash
# final (ex. "/api/ufrs", jamais "/api/ufrs/") — désactivé pour ne jamais
# dépendre d'une redirection 301/308 sur laquelle un client fetch() avec
# credentials/CORS ne se comporte pas toujours de façon fiable. Chaque route
# (config/urls.py + urls.py de chaque app) est donc déclarée en toutes
# lettres, sans jamais compter sur APPEND_SLASH pour combler un slash manquant.
APPEND_SLASH = False

# ---------------------------------------------------------------------------
# CORS — frontend (web/, localhost:3000) et backend sont deux origines
# distinctes : credentials (cookie cm_session) doivent être explicitement
# autorisés, comme app.enableCors({credentials: true}) côté NestJS.
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")]
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Session applicative (accounts.models.Session) — pas django.contrib.sessions.
# ---------------------------------------------------------------------------
SESSION_COOKIE_NAME = "cm_session"
SESSION_TTL = timedelta(hours=int(os.environ.get("SESSION_TTL_HOURS", "8")))
SESSION_COOKIE_SECURE = not DEBUG

# ---------------------------------------------------------------------------
# Django REST Framework — authentification et gestion d'erreurs qui
# reproduisent exactement le contrat NestJS ({erreur: "<message>"} partout,
# jamais {detail: ...} par défaut de DRF).
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.CookieSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["accounts.permissions.IsAuthenticatedCM"],
    "EXCEPTION_HANDLER": "core.exceptions.contrat_api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
}

NOTIFICATION_SENDER = os.environ.get("NOTIFICATION_SENDER", "console")
