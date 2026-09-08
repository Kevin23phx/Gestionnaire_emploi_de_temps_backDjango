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

    # [V3] FR-REF-16/17 : période académique EN COURS de cette UFR. Portée
    # par l'UFR et non globalement, parce que les UFR de l'UJKZ ne rentrent
    # pas toutes le même jour (FR-REF-17). Deux consommateurs, et deux
    # seulement : la borne de fin de récurrence du flux calendrier
    # (sans quoi un cours se répéterait indéfiniment dans l'agenda du
    # visiteur), et la validation des dates d'annulation de séance
    # (INT-11 : on n'annule pas une séance jamais programmée).
    #
    # Volontairement des champs sur l'UFR plutôt qu'un modèle "Semestre"
    # historisé : FR-REF-16 ne demande que la période *en cours*, et rien
    # dans le système ne consulte une période passée. Le jour où l'archivage
    # inter-semestres deviendra un besoin réel, ce sera une extraction de
    # modèle, pas une réécriture.
    periode_libelle = models.CharField(max_length=64, null=True, blank=True)
    periode_debut = models.DateField(null=True, blank=True)
    periode_fin = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "ufr"
        ordering = ["nom"]
        constraints = [
            # Une période à moitié saisie ne veut rien dire : soit les deux
            # bornes, soit aucune. Et une fin avant le début produirait un
            # calendrier vide sans le moindre message d'erreur.
            models.CheckConstraint(
                condition=(
                    (models.Q(periode_debut__isnull=True) & models.Q(periode_fin__isnull=True))
                    | (
                        models.Q(periode_debut__isnull=False)
                        & models.Q(periode_fin__isnull=False)
                        & models.Q(periode_fin__gt=models.F("periode_debut"))
                    )
                ),
                name="ufr_periode_academique_coherente",
            ),
        ]

    def __str__(self) -> str:
        return self.nom

    @property
    def periode_definie(self) -> bool:
        return self.periode_debut is not None and self.periode_fin is not None

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
