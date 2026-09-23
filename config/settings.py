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

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / (os.environ.get("ENV_FILE") or ".env"))

# [V8.8] OWASP A05 « Security Misconfiguration » — les trois réglages
# ci-dessous avaient des défauts commodes en développement et dangereux en
# production. Un déploiement se fait toujours dans la précipitation, et un
# oubli de variable d'environnement ne doit JAMAIS ouvrir le système : le
# défaut est donc désormais le réglage sûr, et c'est le développement qui
# doit s'annoncer explicitement.
# Toutes les valeurs d'amorçage connues, pas seulement celle du code : le
# gabarit `.env.example` en propose une autre, et c'est précisément celle
# qu'un déploiement pressé recopie sans la changer.
SECRETS_D_EXEMPLE = {"dev-only-not-for-production", "change-me-in-production", ""}
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-not-for-production")

# Défaut "false" et non "true" : DEBUG=true en production expose la trace
# complète des exceptions, le contenu des réglages et les requêtes SQL à
# quiconque provoque une erreur. Oublier la variable donne maintenant un
# serveur muet, pas un serveur bavard.
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"

# Le serveur refuse de démarrer en production avec la clé d'exemple. Un
# avertissement n'aurait rien changé : personne ne lit les logs de
# démarrage d'un déploiement qui a réussi.
if not DEBUG and SECRET_KEY.strip() in SECRETS_D_EXEMPLE:
    raise ImproperlyConfigured(
        "SECRET_KEY n'est pas défini alors que DEBUG=false. Renseignez une valeur "
        "secrète et unique avant de démarrer en production."
    )

# ALLOWED_HOSTS ouvert en développement seulement — l'appareil qui teste
# depuis le réseau local a une IP attribuée par DHCP, impossible à figer
# (même raison que pour CORS, plus bas). En production, la liste vient de
# l'environnement : un `Host:` forgé ne peut alors plus servir à empoisonner
# un lien de réinitialisation ou un cache.
def _nom_d_hote(valeur: str) -> str:
    """Extrait un nom d'hôte de ce qui a été saisi, URL comprise.

    ALLOWED_HOSTS attend un hôte NU (« exemple.onrender.com ») tandis que
    ALLOWED_ORIGIN, juste à côté dans la même page de configuration, attend
    une URL COMPLÈTE (« https://exemple.pages.dev »). Confondre les deux est
    l'erreur naturelle, et elle est particulièrement traître : le démarrage
    réussit — la liste n'est pas vide — puis Django rejette *toutes* les
    requêtes avec « Invalid HTTP_HOST header », parce qu'un navigateur
    n'envoie jamais le schéma dans l'en-tête `Host`.

    On normalise donc au lieu de refuser : l'intention est sans ambiguïté, et
    un déploiement ne doit pas échouer sur une subtilité de format. Le port
    est retiré aussi — Django compare l'hôte seul.
    """
    hote = valeur.strip()
    if "//" in hote:
        hote = hote.split("//", 1)[1]
    hote = hote.split("/", 1)[0]
    # IPv6 littéral entre crochets : garder les crochets, ne pas couper sur
    # les deux-points qui séparent ses groupes.
    if not hote.startswith("[") and ":" in hote:
        hote = hote.rsplit(":", 1)[0]
    return hote


ALLOWED_HOSTS = (
    ["*"]
    if DEBUG
    else [h for h in (_nom_d_hote(v) for v in os.environ.get("ALLOWED_HOSTS", "").split(",")) if h]
)
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "ALLOWED_HOSTS est vide alors que DEBUG=false. Renseignez les domaines servis "
        "(séparés par des virgules), par exemple « campus.ujkz.bf »."
    )

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
    # [V8.8] SecurityMiddleware manquait : sans lui, AUCUN des réglages
    # `SECURE_*` ci-dessous n'a d'effet — ils sont posés par ce middleware
    # et par personne d'autre. Placé en premier pour que ses en-têtes
    # accompagnent aussi les réponses court-circuitées par CORS.
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    # [V8.8] X_FRAME_OPTIONS n'est PAS posé par SecurityMiddleware — il a son
    # propre middleware, et sans lui le réglage ne produit aucun en-tête.
    # Constaté par les tests : le réglage était là, l'en-tête absent.
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
# [V8.8] En-têtes de sécurité HTTP (OWASP A05).
# ---------------------------------------------------------------------------
# L'API ne sert que du JSON, ce qui limite la portée de certains en-têtes —
# mais pas leur utilité : une réponse JSON interprétée comme du HTML par un
# navigateur trop serviable reste un vecteur de XSS, et une API encadrable
# reste un vecteur de clickjacking pour qui sait s'en servir.

# Empêche le navigateur de « deviner » un type différent de celui déclaré.
SECURE_CONTENT_TYPE_NOSNIFF = True

# Aucune page de ce backend n'a vocation à être affichée dans un cadre.
X_FRAME_OPTIONS = "DENY"

# Ne fuiter l'adresse complète d'origine qu'à nous-mêmes : un lien sortant
# ne doit pas emporter les paramètres de la page consultée.
SECURE_REFERRER_POLICY = "same-origin"

# HSTS : uniquement en production, et jamais en développement où il
# rendrait `http://localhost` inaccessible pour des mois dans le navigateur
# du développeur — un dégât difficile à diagnostiquer et pénible à défaire.
#
# `includeSubDomains` sans `preload` : la préinscription est irréversible à
# court terme, elle se décide, elle ne se subit pas au détour d'un réglage.
if not DEBUG:
    SECURE_HSTS_SECONDS = int(os.environ.get("HSTS_SECONDS", 60 * 60 * 24 * 365))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False
    # Render/Cloudflare terminent TLS en amont et transmettent le protocole
    # d'origine dans cet en-tête ; sans ce réglage, Django croit recevoir du
    # HTTP en clair et redirigerait en boucle.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = os.environ.get("SSL_REDIRECT", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Session applicative (accounts.models.Session) — pas django.contrib.sessions.
# ---------------------------------------------------------------------------
SESSION_COOKIE_NAME = "cm_session"
SESSION_TTL = timedelta(hours=int(os.environ.get("SESSION_TTL_HOURS", "8")))
SESSION_COOKIE_SECURE = not DEBUG
# "Lax" suffit en dev (front et back sur localhost, ports différents mais
# même site). En production, front (Cloudflare) et back (Render) sont deux
# domaines distincts : "Lax" y bloquerait purement et simplement l'envoi du
# cookie sur les appels cross-site, "None" est donc nécessaire — valide
# uniquement combiné à Secure (garanti ci-dessus dès que DEBUG=false, jamais
# l'un sans l'autre).
SESSION_COOKIE_SAMESITE = "Lax" if DEBUG else "None"

# ---------------------------------------------------------------------------
# [V8.8] Limitation de débit sur l'authentification (OWASP A07).
# ---------------------------------------------------------------------------
# Les quotas sont volontairement bas : un humain qui se connecte tape son
# mot de passe une à trois fois, pas dix. Les valeurs restent réglables par
# variable d'environnement pour qu'un incident en production puisse être
# absorbé sans redéploiement — jamais pour les désactiver.
#
# Voir accounts/throttling.py pour le raisonnement complet et la limite
# connue (cache par processus).
THROTTLE_CONNEXION_IP = os.environ.get("THROTTLE_CONNEXION_IP", "10/min")
THROTTLE_CONNEXION_COMPTE = os.environ.get("THROTTLE_CONNEXION_COMPTE", "5/min")
THROTTLE_ACTIVATION = os.environ.get("THROTTLE_ACTIVATION", "5/min")
THROTTLE_MOT_DE_PASSE = os.environ.get("THROTTLE_MOT_DE_PASSE", "5/min")

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
    # [V8.8] Aucune limite PAR DÉFAUT : l'immense majorité des routes est
    # déjà fermée par `IsAuthenticatedCM`, et brider un Gestionnaire qui
    # saisit un emploi du temps à la chaîne ferait plus de mal que de bien.
    # Les limites sont déclarées vue par vue, là où elles protègent quelque
    # chose — les portes d'entrée (accounts/auth_views.py).
    "DEFAULT_THROTTLE_RATES": {
        "connexion_ip": THROTTLE_CONNEXION_IP,
        "connexion_compte": THROTTLE_CONNEXION_COMPTE,
        "activation": THROTTLE_ACTIVATION,
        "mot_de_passe": THROTTLE_MOT_DE_PASSE,
    },
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
