from django.core.management.base import BaseCommand
from apps.news.models import NewsCategory


class Command(BaseCommand):
    help = "Create default news categories"

    def handle(self, *args, **options):
        categories = [
            {
                "name": "Yangiliklar",
                "slug": "yangiliklar",
                "color": "#3b82f6",  # Blue
            },
            {
                "name": "Yangilanishlar",
                "slug": "yangilanishlar",
                "color": "#10b981",  # Green
            },
            {
                "name": "E'lonlar",
                "slug": "elonlar",
                "color": "#f59e0b",  # Orange
            },
            {
                "name": "Voqealar",
                "slug": "voqealar",
                "color": "#8b5cf6",  # Purple
            },
            {
                "name": "Sayohat",
                "slug": "sayohat",
                "color": "#ec4899",  # Pink
            },
        ]

        created_count = 0
        for category_data in categories:
            category, created = NewsCategory.objects.get_or_create(
                slug=category_data["slug"],
                defaults={
                    "name": category_data["name"],
                    "color": category_data["color"],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Created category: {category_data['name']}")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"- Category already exists: {category_data['name']}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(f"\nTotal categories created: {created_count}")
        )
