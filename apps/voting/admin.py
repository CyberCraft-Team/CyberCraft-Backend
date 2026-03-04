from django.contrib import admin
from .models import VotingSite, Vote


@admin.register(VotingSite)
class VotingSiteAdmin(admin.ModelAdmin):
    list_display = ["name", "url", "bonus", "is_active", "order"]
    list_filter = ["is_active"]
    list_editable = ["bonus", "is_active", "order"]


@admin.register(Vote)
class VoteAdmin(admin.ModelAdmin):
    list_display = ["user", "site", "voted_at"]
    list_filter = ["site", "voted_at"]
    date_hierarchy = "voted_at"
