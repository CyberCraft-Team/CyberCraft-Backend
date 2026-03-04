from django.urls import path
from .views import (
    PublicVotingSitesView,
    PublicTopVotersView,
    VoteSubmitView,
    AdminVotingSitesListCreateView,
    AdminVotingSiteDetailView,
)

urlpatterns = [
    path(
        "public/voting/sites/",
        PublicVotingSitesView.as_view(),
        name="public-voting-sites",
    ),
    path("public/voting/top/", PublicTopVotersView.as_view(), name="public-top-voters"),
    path("voting/submit/", VoteSubmitView.as_view(), name="vote-submit"),
    path(
        "admin/voting/sites/",
        AdminVotingSitesListCreateView.as_view(),
        name="admin-voting-sites-list",
    ),
    path(
        "admin/voting/sites/<int:pk>/",
        AdminVotingSiteDetailView.as_view(),
        name="admin-voting-site-detail",
    ),
]
