from accounts.auth_urls import urlpatterns as auth_urlpatterns
from accounts.urls import urlpatterns as accounts_urlpatterns
from audit.urls import urlpatterns as audit_urlpatterns
from core.urls import urlpatterns as core_urlpatterns
from dashboard.urls import urlpatterns as dashboard_urlpatterns
from planning.urls import urlpatterns as planning_urlpatterns
from public.urls import urlpatterns as public_urlpatterns
from referentiel.urls import urlpatterns as referentiel_urlpatterns
from sync.urls import urlpatterns as sync_urlpatterns
from ufr.urls import urlpatterns as ufr_urlpatterns

# Chaque app déclare ses routes complètes ("api/xxx", jamais un préfixe
# concaténé via include()) dans son propre urls.py — voir la note
# APPEND_SLASH dans settings.py pour pourquoi la concaténation de préfixes
# est évitée ici (le frontend appelle toujours des chemins sans slash final).
urlpatterns = (
    core_urlpatterns
    + auth_urlpatterns
    + accounts_urlpatterns
    + ufr_urlpatterns
    + referentiel_urlpatterns
    + planning_urlpatterns
    + audit_urlpatterns
    + dashboard_urlpatterns
    + sync_urlpatterns
    # [V3] En DERNIER, et volontairement : la surface publique est la seule
    # à ne pas exiger d'authentification (FR-AUTH-05). La lire en fin de
    # liste rappelle à chaque relecture qu'elle est l'exception, jamais la
    # règle — cf. 04_Exigence_Architecture ligne 19.
    + public_urlpatterns
)
