"""
SQLite database backup management command.
Usage: python manage.py backup_db
"""

import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "SQLite ma'lumotlar bazasini zaxiralash"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            type=str,
            default=None,
            help="Zaxira faylni saqlash papkasi (default: Backend/backups/)",
        )

    def handle(self, *args, **options):
        db_path = Path(settings.DATABASES["default"]["NAME"])

        if not db_path.exists():
            self.stderr.write(self.style.ERROR(f"DB fayl topilmadi: {db_path}"))
            return

        output_dir = options.get("output_dir")
        if output_dir:
            backup_dir = Path(output_dir)
        else:
            backup_dir = settings.BASE_DIR / "backups"

        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"db_backup_{timestamp}.sqlite3"
        backup_path = backup_dir / backup_name

        try:
            shutil.copy2(str(db_path), str(backup_path))
            size_mb = backup_path.stat().st_size / (1024 * 1024)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Zaxira muvaffaqiyatli yaratildi: {backup_path} ({size_mb:.2f} MB)"
                )
            )

            self._cleanup_old_backups(backup_dir, keep=5)

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"Zaxiralashda xatolik: {e}"))

    def _cleanup_old_backups(self, backup_dir, keep=5):
        """Eng eski zaxiralarni o'chirish, faqat oxirgi N tasini saqlash."""
        backups = sorted(
            backup_dir.glob("db_backup_*.sqlite3"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        for old_backup in backups[keep:]:
            old_backup.unlink()
            self.stdout.write(f"Eski zaxira o'chirildi: {old_backup.name}")
