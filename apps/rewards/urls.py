from django.urls import path
from .views import (
    RankListView,
    DailyBonusStatusView,
    DailyBonusClaimView,
    RankPurchaseView,
    ReferralLinkView,
    CCTransactionHistoryView,
    PlayerRankView,
    BulkPlayerRanksView,
)

urlpatterns = [
    path("ranks/", RankListView.as_view(), name="rank-list"),
    path("daily-bonus/", DailyBonusClaimView.as_view(), name="daily-bonus-claim"),
    path(
        "daily-bonus/status/", DailyBonusStatusView.as_view(), name="daily-bonus-status"
    ),
    path("ranks/purchase/", RankPurchaseView.as_view(), name="rank-purchase"),
    path("referral/", ReferralLinkView.as_view(), name="referral-link"),
    path("transactions/", CCTransactionHistoryView.as_view(), name="cc-transactions"),
    path("player-rank/", PlayerRankView.as_view(), name="player-rank"),
    path("player-ranks/", BulkPlayerRanksView.as_view(), name="bulk-player-ranks"),
]
