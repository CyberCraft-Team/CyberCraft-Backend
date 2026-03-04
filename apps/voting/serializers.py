from rest_framework import serializers
from .models import VotingSite


class VotingSiteSerializer(serializers.ModelSerializer):
    class Meta:
        model = VotingSite
        fields = ["id", "name", "url", "bonus"]


class TopVoterSerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    username = serializers.CharField()
    votes = serializers.IntegerField()
    avatar_url = serializers.CharField(allow_null=True)
