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
    "public",
    "conflict_engine",
    "audit",
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
# Liste séparée par des virgules — voir ALLOWED_ORIGIN dans .env. C'est la
# seule source d'origines autorisées EN PRODUCTION.
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000").split(",") if o.strip()]
CORS_ALLOW_CREDENTIALS = True

# EN DÉVELOPPEMENT UNIQUEMENT : accepte en plus n'importe quelle origine du
# réseau local (10.x, 172.16-31.x, 192.168.x) sur le port du frontend.
#
# Motif : l'IP d'un poste sur un réseau local est attribuée par DHCP et change
# de box en box, du campus au domicile. Une liste figée dans .env fonctionne le
# jour où on l'écrit et casse la semaine suivante, avec pour seul symptôme des
# 401 en cascade après une connexion pourtant réussie — un diagnostic coûteux
# pour une cause triviale.
#
# Ces plages sont non routables sur Internet : une origine qui les emprunte est
# nécessairement sur le même réseau physique que le serveur de développement.
# Le garde-fou reste `if DEBUG` — en production, seule la liste explicite
# ci-dessus s'applique.
if DEBUG:
    CORS_ALLOWED_ORIGIN_REGEXES = [
        r"^http://localhost:\d+$",
        r"^http://127\.0\.0\.1:\d+$",
        r"^http://10\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+$",
        r"^http://172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}:\d+$",
        r"^http://192\.168\.\d{1,3}\.\d{1,3}:\d+$",
    ]

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

# [V3] Canal d'alerte Web Push (FR-PUB-08). "console" par défaut : sans
# clés VAPID configurées, tout le système fonctionne — programme public,
# favoris, abonnement agenda — et les alertes sont simplement journalisées.
# Générer une paire : `venv/bin/vapid --gen` (py-vapid, installé avec
# pywebpush), puis renseigner les deux variables ci-dessous.
# ---------------------------------------------------------------------------
# Journalisation
# ---------------------------------------------------------------------------
# Sans cette configuration, les messages de nos propres modules ne remontent
# que par le "handler de dernier recours" de Python : sur stderr, sans
# horodatage ni niveau, indistinguables du bruit du serveur de dev.
#
# Ça compte surtout pour un cas précis : `public.diffusion` avale
# volontairement les erreurs d'envoi d'alerte, pour qu'un service de push
# indisponible ne fasse jamais échouer l'enregistrement d'une annulation
# pourtant valide. La contrepartie est qu'une alerte perdue ne se voit
# nulle part ailleurs que dans ce journal — un Gestionnaire croirait avoir
# prévenu les étudiants sans que rien ne le détrompe.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "campus": {"format": "[{asctime}] {levelname} {name} — {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "campus"},
    },
    "loggers": {
        # Nos applications : INFO et au-dessus, horodaté et nommé.
        "public": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "planning": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "referentiel": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "accounts": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}

PUSH_SENDER = os.environ.get("PUSH_SENDER", "console")
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:scolarite@ujkz.bf")
