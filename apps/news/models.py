from django.db import models
from django.conf import settings


class NewsCategory(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True)
    color = models.CharField(max_length=50, default="var(--primary)")

    class Meta:
        db_table = "news_categories"
        verbose_name = "News Category"
        verbose_name_plural = "News Categories"

    def __str__(self):
        return self.name


class News(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    excerpt = models.TextField(max_length=500)
    content = models.TextField()
    category = models.ForeignKey(
        NewsCategory, on_delete=models.SET_NULL, null=True, related_name="news"
    )
    image = models.ImageField(upload_to="news_images/", blank=True, null=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="news_articles",
    )
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "news"
        verbose_name = "News Article"
        verbose_name_plural = "News Articles"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
