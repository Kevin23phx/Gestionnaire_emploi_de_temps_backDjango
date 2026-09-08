from rest_framework import serializers

from referentiel.models import Departement, Groupe, Salle, UniteEnseignement


class GroupeSerializer(serializers.ModelSerializer):
    anneeAcademique = serializers.CharField(source="annee_academique")
    ufrId = serializers.CharField(source="ufr_id")

    class Meta:
        model = Groupe
        # [V3.1] "effectif" est une colonne du modèle : plus de
        # SerializerMethodField, plus de COUNT à recalculer.
        fields = ["id", "nom", "filiere", "niveau", "anneeAcademique", "ufrId", "effectif"]


class DepartementSerializer(serializers.ModelSerializer):
    ufrId = serializers.CharField(source="ufr_id")

    class Meta:
        model = Departement
        fields = ["id", "libelle", "ufrId"]


class SalleSerializer(serializers.ModelSerializer):
    structureGestionnaire = serializers.CharField(source="structure_gestionnaire")
    typeUsage = serializers.CharField(source="type_usage")
    ufrId = serializers.CharField(source="ufr_id", allow_null=True)

    class Meta:
        model = Salle
        fields = ["id", "nom", "batiment", "capacite", "structureGestionnaire", "ufrId", "typeUsage"]


class UniteEnseignementSerializer(serializers.ModelSerializer):
    ufrId = serializers.CharField(source="ufr_id")

    class Meta:
        model = UniteEnseignement
        fields = ["id", "code", "intitule", "niveau", "ufrId"]

