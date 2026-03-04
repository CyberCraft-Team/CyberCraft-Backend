from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from django.db.models import Count
from django.utils import timezone
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from datetime import timedelta
from apps.accounts.authentication import AdminTokenAuthentication
from apps.launcher.authentication import LauncherTokenAuthentication
from .models import VotingSite, Vote
from .serializers import VotingSiteSerializer, TopVoterSerializer

VOTE_COOLDOWN_HOURS = 12


class PublicVotingSitesView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(cache_page(300))
    def get(self, request):
        sites = VotingSite.objects.filter(is_active=True)
        serializer = VotingSiteSerializer(sites, many=True)
        return Response(serializer.data)


class PublicTopVotersView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(cache_page(300))
    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        top_voters = (
            Vote.objects.filter(voted_at__gte=month_start)
            .values("user__username")
            .annotate(vote_count=Count("id"))
            .order_by("-vote_count")[:10]
        )

        result = []
        for rank, voter in enumerate(top_voters, 1):
            username = voter["user__username"]
            avatar_url = f"https://mc-heads.net/avatar/{username}/40"

            result.append(
                {
                    "rank": rank,
                    "username": username,
                    "votes": voter["vote_count"],
                    "avatar_url": avatar_url,
                }
            )

        return Response(result)


class VoteSubmitView(APIView):
    """Vote qilish — cooldown bilan."""

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        site_id = request.data.get("site_id")

        if not site_id:
            return Response({"error": "site_id kerak"}, status=400)

        try:
            site = VotingSite.objects.get(id=site_id, is_active=True)
        except VotingSite.DoesNotExist:
            return Response({"error": "Voting sayt topilmadi"}, status=404)

        cooldown_cutoff = timezone.now() - timedelta(hours=VOTE_COOLDOWN_HOURS)
        recent_vote = Vote.objects.filter(
            user=request.user,
            site=site,
            voted_at__gte=cooldown_cutoff,
        ).first()

        if recent_vote:
            remaining = (
                recent_vote.voted_at
                + timedelta(hours=VOTE_COOLDOWN_HOURS)
                - timezone.now()
            )
            hours = int(remaining.total_seconds() // 3600)
            minutes = int((remaining.total_seconds() % 3600) // 60)
            return Response(
                {
                    "error": f"Bu saytga yana {hours} soat {minutes} daqiqadan keyin vote qilishingiz mumkin",
                    "cooldown_remaining_seconds": int(remaining.total_seconds()),
                },
                status=400,
            )

        Vote.objects.create(user=request.user, site=site)

        request.user.cc_balance += site.bonus
        request.user.save(update_fields=["cc_balance"])

        from apps.rewards.models import CCTransaction

        CCTransaction.objects.create(
            user=request.user,
            amount=site.bonus,
            transaction_type="daily_bonus",
            description=f"{site.name} saytida vote qilindi",
        )

        from apps.notifications.models import Notification

        Notification.send(
            user=request.user,
            title="Vote bonus!",
            message=f"{site.name} da vote qildingiz. +{site.bonus} CC!",
            notification_type="reward",
        )

        return Response(
            {
                "message": f"Vote muvaffaqiyatli! +{site.bonus} CC",
                "bonus": site.bonus,
                "new_balance": request.user.cc_balance,
            }
        )


class AdminVotingSitesListCreateView(ListCreateAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]
    queryset = VotingSite.objects.all().order_by("-id")
    serializer_class = VotingSiteSerializer


class AdminVotingSiteDetailView(RetrieveUpdateDestroyAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]
    queryset = VotingSite.objects.all()
    serializer_class = VotingSiteSerializer
