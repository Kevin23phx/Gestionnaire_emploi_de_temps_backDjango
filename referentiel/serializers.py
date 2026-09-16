from rest_framework import serializers

from referentiel.models import Departement, Groupe, Salle, UniteEnseignement


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
        fields = ["id", "nom", "departement", "niveau", "anneeAcademique", "ufrId", "effectif", "aDejaEteSuccede"]

    def get_aDejaEteSuccede(self, obj) -> bool:
        return hasattr(obj, "groupe_suivant")


class DepartementSerializer(serializers.ModelSerializer):
    ufrId = serializers.CharField(source="ufr_id")

    class Meta:
        model = Departement
        fields = ["id", "libelle", "ufrId"]


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

