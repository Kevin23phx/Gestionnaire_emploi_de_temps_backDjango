"""[V8.8, 2026-09-23] Limitation de débit sur l'authentification.

## Pourquoi c'est la mesure la plus urgente du projet

`POST /api/auth/login` n'avait aucune limite. Or trois choses se combinent
ici pour rendre une attaque par force brute réaliste :

1. **Les identifiants sont publics et devinables.** FR-ADMIN-02 fixe la
   convention `scolarite.<sigle>`, et les douze sigles de l'UJKZ figurent
   dans la cascade publique (`GET /api/public/ufrs`, sans authentification).
   Un attaquant n'a donc rien à deviner côté identifiant : la liste complète
   des comptes lui est servie par le site lui-même.
2. **Le parc de comptes est minuscule** — une douzaine. Il suffit d'en
   casser un seul pour écrire dans le planning d'un établissement.
3. **Le mot de passe fait 8 caractères minimum** (NFR-SEC-06), ce qui est le
   plancher recommandé pour un secret humain, pas une garantie : sans
   limite de tentatives, il n'oppose que sa propre entropie à un automate.

C'est le point de la surface d'attaque où l'effort de l'attaquant est le
plus faible et le gain le plus élevé — A07 « Identification and
Authentication Failures » du Top 10 de l'OWASP, dont la première
contre-mesure citée est précisément de limiter les tentatives.

## Deux clés, et pourquoi il en faut deux

- **Par adresse IP** : arrête l'automate classique, qui essaie des milliers
  de mots de passe depuis une machine.
- **Par identifiant visé** : arrête l'attaque distribuée, qui change d'IP à
  chaque essai pour contourner la première. Sans elle, la limite par IP se
  contourne avec un carnet de proxys, et c'est le mode d'attaque courant
  contre un parc de comptes aussi réduit.

## Limite connue de cette implémentation

Le comptage s'appuie sur le cache Django, qui n'est pas configuré : c'est
donc `LocMemCache`, **propre à chaque processus**. Derrière un gunicorn à
plusieurs workers, la limite effective est multipliée par leur nombre.
C'est une atténuation, pas un verrou — un cache partagé (Redis) la rendrait
exacte, et c'est la première chose à faire si le projet passe à l'échelle.
Mieux vaut une limite approximative qu'aucune : elle fait passer une
attaque de quelques heures à plusieurs années.
"""

from rest_framework.throttling import SimpleRateThrottle


class ConnexionParIpThrottle(SimpleRateThrottle):
    """Tentatives de connexion depuis une même adresse."""

    scope = "connexion_ip"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class ConnexionParCompteThrottle(SimpleRateThrottle):
    """Tentatives de connexion VISANT un même compte, quelle que soit
    l'origine. C'est celle qui résiste à l'attaque distribuée.

    L'identifiant est normalisé (minuscules, espaces retirés) : sans quoi
    « Scolarite.SDS » et « scolarite.sds » compteraient séparément alors que
    la base les traite comme un seul compte, et alterner la casse suffirait
    à doubler le quota.
    """

    scope = "connexion_compte"

    def get_cache_key(self, request, view):
        identifiant = (request.data.get("identifiant") or "").strip().casefold()
        if not identifiant:
            # Rien à protéger : la requête sera de toute façon rejetée pour
            # champ manquant. On la laisse au quota par IP.
            return None
        return self.cache_format % {"scope": self.scope, "ident": identifiant}


class ParCompteConnecteThrottle(SimpleRateThrottle):
    """Limite une route AUTHENTIFIÉE, par compte connecté.

    `ScopedRateThrottle` de DRF ne convient pas ici : il construit sa clé
    avec `request.user.pk`, alors que ce projet n'utilise pas le modèle
    utilisateur de Django. `CookieSessionAuthentication` attache un
    `AuthenticatedUser` maison (accounts/authenticated_user.py), qui expose
    `id` et pas `pk` — d'où un `AttributeError` au premier appel, c'est-à-dire
    une route en panne au lieu d'une route protégée.

    Découvert par les tests de sécurité le 2026-09-23, avant mise en ligne.
    C'est le risque propre à ce genre de durcissement : une mesure ajoutée à
    la hâte peut casser ce qu'elle prétend protéger.
    """

    scope = "mot_de_passe"

    def get_cache_key(self, request, view):
        identifiant = getattr(request.user, "id", None)
        if not identifiant:
            # Non authentifié : la permission refusera de toute façon.
            return None
        return self.cache_format % {"scope": self.scope, "ident": identifiant}
