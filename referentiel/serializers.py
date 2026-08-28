from rest_framework import serializers

from referentiel.models import Etudiant, Groupe, Salle, UniteEnseignement


class GroupeSerializer(serializers.ModelSerializer):
    anneeAcademique = serializers.CharField(source="annee_academique")
    ufrId = serializers.CharField(source="ufr_id")
    effectif = serializers.SerializerMethodField()

    class Meta:
        model = Groupe
        fields = ["id", "nom", "filiere", "niveau", "anneeAcademique", "ufrId", "effectif"]

    def get_effectif(self, obj) -> int:
        # Annoté par la queryset du service (annotate(effectif=Count(...)))
        # quand disponible ; recalculé sinon (ex. juste après une création).
        return getattr(obj, "effectif", None) if getattr(obj, "effectif", None) is not None else obj.etudiants.count()


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


class EtudiantSerializer(serializers.ModelSerializer):
    anneeAcademique = serializers.CharField(source="annee_academique")
    ufrId = serializers.CharField(source="ufr_id")
    groupeId = serializers.CharField(source="groupe_id", allow_null=True)

    class Meta:
        model = Etudiant
        fields = ["id", "ine", "nom", "prenom", "filiere", "niveau", "anneeAcademique", "ufrId", "groupeId"]
