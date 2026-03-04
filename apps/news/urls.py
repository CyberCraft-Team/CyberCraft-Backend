from django.urls import path
from .views import (
    PublicNewsListView,
    PublicNewsDetailView,
    AdminNewsListCreateView,
    AdminNewsDetailView,
    NewsCategoriesView,
)

urlpatterns = [
    path("public/news/", PublicNewsListView.as_view(), name="public-news"),
    path(
        "public/news/<int:pk>/",
        PublicNewsDetailView.as_view(),
        name="public-news-detail",
    ),
    path("admin/news/", AdminNewsListCreateView.as_view(), name="admin-news-list"),
    path(
        "admin/news/<int:pk>/",
        AdminNewsDetailView.as_view(),
        name="admin-news-detail",
    ),
    path("admin/categories/", NewsCategoriesView.as_view(), name="news-categories"),
]
