from rest_framework import serializers
from .models import Rank, DailyBonus, CCTransaction


class RankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rank
        fields = ["id", "name", "price", "color_code", "priority"]


class DailyBonusStatusSerializer(serializers.Serializer):
    streak = serializers.IntegerField()
    last_claim = serializers.DateField(allow_null=True)
    can_claim = serializers.BooleanField()
    next_bonus = serializers.IntegerField()


class CCTransactionSerializer(serializers.ModelSerializer):
    transaction_type_display = serializers.CharField(
        source="get_transaction_type_display", read_only=True
    )

    class Meta:
        model = CCTransaction
        fields = [
            "id",
            "amount",
            "transaction_type",
            "transaction_type_display",
            "description",
            "created_at",
        ]


class RankPurchaseSerializer(serializers.Serializer):
    rank_id = serializers.IntegerField()


class UserRankResponseSerializer(serializers.Serializer):
    """Mod uchun player rank response"""

    username = serializers.CharField()
    rank = serializers.CharField()
    color_code = serializers.CharField()
    formatted = serializers.CharField()
