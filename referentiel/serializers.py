from rest_framework import serializers

from referentiel.models import Departement, Groupe, Salle, Specialite, UniteEnseignement


class GroupeSerializer(serializers.ModelSerializer):
    anneeAcademique = serializers.CharField(source="annee_academique")
    ufrId = serializers.CharField(source="ufr_id")
    # [V6] "aDejaEteSuccede" pilote l'affichage du bouton de passage côté
    # front : un groupe déjà promu ne doit pas pouvoir l'être une seconde
    # fois (le OneToOne l'empêcherait de toute façon en base, mais autant
    # ne pas proposer l'action).
    aDejaEteSuccede = serializers.SerializerMethodField()

    class Meta:
        model = Groupe
        # [V3.1] "effectif" est une colonne du modèle : plus de
        # SerializerMethodField, plus de COUNT à recalculer.
        # [V8] "specialite" : chaîne, vide quand le niveau n'en propose
        # aucune. Sérialisée telle quelle (pas d'objet imbriqué) parce que
        # c'est une chaîne dénormalisée en base, pas une relation — cf.
        # referentiel/models.py.
        fields = [
            "id",
            "nom",
            "departement",
            "niveau",
            "specialite",
            "anneeAcademique",
            "ufrId",
            "effectif",
            "aDejaEteSuccede",
        ]

    def get_aDejaEteSuccede(self, obj) -> bool:
        return hasattr(obj, "groupe_suivant")


class DepartementSerializer(serializers.ModelSerializer):
    ufrId = serializers.CharField(source="ufr_id")

    class Meta:
        model = Departement
        fields = ["id", "libelle", "ufrId"]


class SpecialiteSerializer(serializers.ModelSerializer):
    """[V8] Le libellé du département accompagne toujours la spécialité :
    l'écran de référentiel liste les spécialités de TOUT l'établissement, et
    « Informatique » ne veut rien dire sans le département qui l'ouvre. Le
    faire chercher par un second appel au front n'aurait rien économisé — la
    jointure est déjà faite par `select_related` côté service."""

    departementId = serializers.CharField(source="departement_id")
    departement = serializers.CharField(source="departement.libelle", read_only=True)
    ufrId = serializers.CharField(source="departement.ufr_id", read_only=True)

    class Meta:
        model = Specialite
        fields = ["id", "libelle", "niveau", "departementId", "departement", "ufrId"]


class SalleSerializer(serializers.ModelSerializer):
    typeUsage = serializers.CharField(source="type_usage")

    class Meta:
        model = Salle
        fields = ["id", "nom", "capacite", "typeUsage"]


class UniteEnseignementSerializer(serializers.ModelSerializer):
    ufrId = serializers.CharField(source="ufr_id")
    # [V3.3] Les départements accompagnent toujours le cours : c'est la
    # réponse à « qui suit ce cours ? », et elle n'a d'intérêt que si elle
    # s'affiche là où l'on cherche le cours — pas derrière un second appel.
    departements = DepartementSerializer(many=True, read_only=True)

    class Meta:
        model = UniteEnseignement
        fields = ["id", "code", "intitule", "ufrId", "departements"]

