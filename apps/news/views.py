from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from apps.accounts.authentication import AdminTokenAuthentication
from .models import News, NewsCategory
from .serializers import NewsSerializer, AdminNewsSerializer, NewsCategorySerializer


class PublicNewsListView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(cache_page(300))
    def get(self, request):
        news = News.objects.filter(is_published=True).select_related(
            "category", "author"
        )[:10]
        serializer = NewsSerializer(news, many=True, context={"request": request})
        return Response(serializer.data)


class PublicNewsDetailView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @method_decorator(cache_page(300))
    def get(self, request, pk):
        try:
            news = News.objects.select_related("category", "author").get(
                pk=pk, is_published=True
            )
        except News.DoesNotExist:
            return Response(
                {"error": "Yangilik topilmadi"}, status=status.HTTP_404_NOT_FOUND
            )

        serializer = NewsSerializer(news, context={"request": request})
        return Response(serializer.data)


class AdminNewsListCreateView(ListCreateAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]
    queryset = (
        News.objects.all().select_related("category", "author").order_by("-created_at")
    )
    serializer_class = AdminNewsSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)


class AdminNewsDetailView(RetrieveUpdateDestroyAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]
    queryset = News.objects.all().select_related("category", "author")
    serializer_class = AdminNewsSerializer


class NewsCategoriesView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        categories = NewsCategory.objects.all()
        serializer = NewsCategorySerializer(categories, many=True)
        return Response(serializer.data)
