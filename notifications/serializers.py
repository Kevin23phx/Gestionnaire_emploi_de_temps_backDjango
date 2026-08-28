from rest_framework import serializers

from notifications.models import NotificationItem


class NotificationItemSerializer(serializers.ModelSerializer):
    dateHeure = serializers.DateTimeField(source="date_heure")

    class Meta:
        model = NotificationItem
        fields = ["id", "type", "titre", "description", "dateHeure", "lue"]
