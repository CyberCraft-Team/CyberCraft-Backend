from django.contrib import admin
from .models import Rank, DailyBonus, CCTransaction


@admin.register(Rank)
class RankAdmin(admin.ModelAdmin):
    list_display = ["name", "price", "color_code", "priority"]
    list_editable = ["price", "priority"]
    ordering = ["priority"]


@admin.register(DailyBonus)
class DailyBonusAdmin(admin.ModelAdmin):
    list_display = ["user", "streak", "last_claim"]
    list_filter = ["streak"]
    search_fields = ["user__username"]
    readonly_fields = ["user"]


@admin.register(CCTransaction)
class CCTransactionAdmin(admin.ModelAdmin):
    list_display = ["user", "amount", "transaction_type", "created_at"]
    list_filter = ["transaction_type", "created_at"]
    search_fields = ["user__username", "description"]
    readonly_fields = [
        "user",
        "amount",
        "transaction_type",
        "description",
        "created_at",
    ]
    date_hierarchy = "created_at"
