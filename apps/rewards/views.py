from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.generics import ListAPIView
from django.db import transaction
from apps.launcher.authentication import LauncherTokenAuthentication
from apps.accounts.models import User
from .models import Rank, DailyBonus, CCTransaction
from .serializers import (
    RankSerializer,
    DailyBonusStatusSerializer,
    CCTransactionSerializer,
    RankPurchaseSerializer,
    UserRankResponseSerializer,
)


class RankListView(ListAPIView):
    """Barcha ranklar ro'yxati"""

    permission_classes = [AllowAny]
    authentication_classes = []
    queryset = Rank.objects.all().order_by("priority")
    serializer_class = RankSerializer


class DailyBonusStatusView(APIView):
    """Kunlik bonus holati"""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        daily_bonus, created = DailyBonus.objects.get_or_create(user=request.user)

        can_claim = daily_bonus.can_claim_today()
        if can_claim:
            if daily_bonus.last_claim:
                from django.utils import timezone

                days_diff = (timezone.now().date() - daily_bonus.last_claim).days
                if days_diff == 1:
                    next_bonus = min(daily_bonus.streak + 1, 7)
                else:
                    next_bonus = 1
            else:
                next_bonus = 1
        else:
            next_bonus = 0

        data = {
            "streak": daily_bonus.streak,
            "last_claim": daily_bonus.last_claim,
            "can_claim": can_claim,
            "next_bonus": next_bonus,
        }
        return Response(DailyBonusStatusSerializer(data).data)


class DailyBonusClaimView(APIView):
    """Kunlik bonus olish"""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        daily_bonus, created = DailyBonus.objects.get_or_create(user=request.user)

        if not daily_bonus.can_claim_today():
            return Response(
                {"error": "Bugun allaqachon bonus oldingiz. Ertaga qayta keling!"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            streak, amount = daily_bonus.claim()

            request.user.cc_balance += amount
            request.user.save(update_fields=["cc_balance"])

            CCTransaction.objects.create(
                user=request.user,
                amount=amount,
                transaction_type="daily_bonus",
                description=f"Kunlik bonus - {streak}-kun streak",
            )

        return Response(
            {
                "message": f"{amount} CC bonus olindi!",
                "amount": amount,
                "streak": streak,
                "new_balance": request.user.cc_balance,
            }
        )


class RankPurchaseView(APIView):
    """Rank sotib olish"""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RankPurchaseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        rank_id = serializer.validated_data["rank_id"]

        try:
            rank = Rank.objects.get(id=rank_id)
        except Rank.DoesNotExist:
            return Response(
                {"error": "Rank topilmadi"},
                status=status.HTTP_404_NOT_FOUND,
            )

        current_rank = Rank.objects.filter(name=request.user.rank).first()
        if current_rank and current_rank.priority >= rank.priority:
            return Response(
                {"error": "Sizda allaqachon bu rank yoki undan yuqorisi bor"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if request.user.cc_balance < rank.price:
            return Response(
                {
                    "error": f"Yetarli CC yo'q. Kerak: {rank.price} CC, Sizda: {request.user.cc_balance} CC"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            request.user.cc_balance -= rank.price
            request.user.rank = rank.name
            request.user.save(update_fields=["cc_balance", "rank"])

            CCTransaction.objects.create(
                user=request.user,
                amount=-rank.price,
                transaction_type="rank_purchase",
                description=f"{rank.name} ranki sotib olindi",
            )

        return Response(
            {
                "message": f"{rank.name} ranki muvaffaqiyatli sotib olindi!",
                "rank": rank.name,
                "new_balance": request.user.cc_balance,
            }
        )


class ReferralLinkView(APIView):
    """Foydalanuvchining referral linkini olish"""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if not user.referral_code:
            user.referral_code = User._generate_referral_code()
            user.save(update_fields=["referral_code"])

        referral_count = User.objects.filter(referred_by=user).count()

        return Response(
            {
                "referral_code": user.referral_code,
                "referral_link": f"https://cybercraft.uz/register?ref={user.referral_code}",
                "referral_count": referral_count,
                "bonus_per_invite": 10,
                "bonus_for_invitee": 5,
            }
        )


class CCTransactionHistoryView(ListAPIView):
    """CC tranzaksiyalari tarixi"""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = CCTransactionSerializer

    def get_queryset(self):
        return CCTransaction.objects.filter(user=self.request.user)[:50]


class PlayerRankView(APIView):
    """Mod uchun - player rankini olish"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        username = request.query_params.get("username")
        uuid = request.query_params.get("uuid")

        if not username and not uuid:
            return Response(
                {"error": "username yoki uuid kerak"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if uuid:
            user = User.objects.filter(minecraft_uuid=uuid).first()
        else:
            user = User.objects.filter(username=username).first()

        if not user:
            return Response(
                {"error": "Foydalanuvchi topilmadi"},
                status=status.HTTP_404_NOT_FOUND,
            )

        rank = Rank.objects.filter(name=user.rank).first()
        color_code = rank.color_code if rank else "§7"

        formatted = f"{color_code}[{user.rank}]§f {user.username}"

        data = {
            "username": user.username,
            "rank": user.rank,
            "color_code": color_code,
            "formatted": formatted,
        }
        return Response(UserRankResponseSerializer(data).data)


class BulkPlayerRanksView(APIView):
    """Mod uchun - bir nechta playerlarning ranklarini olish"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        usernames = request.data.get("usernames", [])

        if not usernames or not isinstance(usernames, list):
            return Response(
                {"error": "usernames list kerak"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        users = User.objects.filter(username__in=usernames)
        ranks = {r.name: r.color_code for r in Rank.objects.all()}

        result = {}
        for user in users:
            color_code = ranks.get(user.rank, "§7")
            result[user.username] = {
                "rank": user.rank,
                "color_code": color_code,
                "formatted": f"{color_code}[{user.rank}]§f {user.username}",
            }

        return Response(result)
