from django.core.management.base import BaseCommand
from apps.rewards.models import Rank


class Command(BaseCommand):
    help = "Boshlang'ich ranklar yaratish"

    def handle(self, *args, **options):
        ranks_data = [
            {"name": "Player", "price": 0, "color_code": "§7", "priority": 0},
            {"name": "VIP", "price": 100, "color_code": "§a", "priority": 1},
            {"name": "MVP", "price": 500, "color_code": "§b", "priority": 2},
            {"name": "Elite", "price": 1500, "color_code": "§d", "priority": 3},
            {"name": "Legend", "price": 5000, "color_code": "§6", "priority": 4},
        ]

        for rank_data in ranks_data:
            rank, created = Rank.objects.get_or_create(
                name=rank_data["name"],
                defaults=rank_data,
            )
            if created:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✓ {rank.name} ranki yaratildi ({rank.price} CC)"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"⚠ {rank.name} ranki allaqachon mavjud")
                )

        self.stdout.write(self.style.SUCCESS("\nBarcha ranklar tayyor!"))
