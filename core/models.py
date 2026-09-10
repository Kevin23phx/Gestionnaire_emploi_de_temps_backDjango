from django.db import models


class TypeEtablissement(models.TextChoices):
    """[V3.2] L'UJKZ ne compte pas que des UFR.

    La liste officielle transmise le 2026-09-07 recense 12 établissements :
    5 UFR, 6 instituts et 1 école doctorale. La V2 avait délibérément
    restreint le périmètre aux 5 UFR ; cette restriction est levée.
    """

    UFR = "ufr", "UFR"
    INSTITUT = "institut", "Institut"
    ECOLE_DOCTORALE = "ecole_doctorale", "École doctorale"


class Ufr(models.Model):
    """Un ÉTABLISSEMENT de l'UJKZ — UFR, institut ou école doctorale.

    [V3.2] Le modèle garde son nom historique `Ufr` (et sa table `ufr`)
    alors qu'il ne représente plus seulement des UFR. C'est un compromis
    assumé : renommer traverserait les migrations, les 40 fichiers qui
    manipulent `ufr_id`, la clause de cloisonnement INT-07 et le contrat
    d'API que le frontend consomme — pour un gain purement lexical. En
    revanche **tout ce que l'utilisateur lit dit « établissement »**, parce
    qu'un étudiant de l'IBAM à qui l'on demanderait « votre UFR » ne
    saurait pas quoi répondre.

    "sigle" est le code court en minuscules (sh, lac, ibam...) : il
    alimente l'identifiant du compte Gestionnaire (scolarite.<sigle>) et
    doit rester stable. Le libellé affiché se compose à partir du type
    (voir `sigle_affiche`).
    """

    id = models.CharField(primary_key=True, max_length=64)
    nom = models.CharField(max_length=255)
    sigle = models.CharField(max_length=32, unique=True)
    type = models.CharField(max_length=20, choices=TypeEtablissement.choices, default=TypeEtablissement.UFR)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ufr"
        ordering = ["nom"]

    def __str__(self) -> str:
        return self.nom

    @property
    def sigle_affiche(self) -> str:
        """"UFR/SH" pour une UFR, "IBAM" pour un institut.

        Les UFR de l'UJKZ se désignent toujours avec le préfixe "UFR/" dans
        les documents officiels, jamais les instituts ni l'école doctorale.
        Composé ici plutôt que stocké : le préfixe se déduit du type, et le
        dupliquer en base ouvrirait la porte à une incohérence entre les
        deux (un institut nommé "UFR/IBAM").
        """
        return f"UFR/{self.sigle.upper()}" if self.type == TypeEtablissement.UFR else self.sigle.upper()
