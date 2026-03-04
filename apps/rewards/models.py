from django.db import models
from django.conf import settings
from django.utils import timezone
import secrets
import string


class Rank(models.Model):
    """Rank modeli - Player, VIP, MVP, Elite, Legend"""

    name = models.CharField(max_length=20, unique=True)
    price = models.IntegerField(default=0)
    color_code = models.CharField(max_length=10, default="§7")
    priority = models.IntegerField(default=0)

    class Meta:
        db_table = "ranks"
        ordering = ["priority"]

    def __str__(self):
        return f"{self.name} ({self.price} CC)"


class DailyBonus(models.Model):
    """Kunlik bonus tracking"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_bonus"
    )
    streak = models.IntegerField(default=0)
    last_claim = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "daily_bonuses"
        verbose_name = "Daily Bonus"
        verbose_name_plural = "Daily Bonuses"

    def can_claim_today(self):
        """Bugun claim qilish mumkinmi?"""
        if not self.last_claim:
            return True
        return self.last_claim < timezone.now().date()

    def claim(self):
        """Bonus olish va streak yangilash"""
        today = timezone.now().date()

        if not self.can_claim_today():
            return 0, self.streak

        if self.last_claim:
            days_diff = (today - self.last_claim).days
            if days_diff == 1:
                self.streak = min(self.streak + 1, 7)
            else:
                self.streak = 1
        else:
            self.streak = 1

        self.last_claim = today
        self.save()

        return self.streak, self.streak

    def __str__(self):
        return f"{self.user.username} - Streak: {self.streak}"


class CCTransaction(models.Model):
    """CC tranzaksiyalari tarixi"""

    TRANSACTION_TYPES = [
        ("referral_inviter", "Referral Bonus (Taklif qiluvchi)"),
        ("referral_invitee", "Referral Bonus (Taklif qilingan)"),
        ("daily_bonus", "Kunlik Bonus"),
        ("rank_purchase", "Rank Sotib Olish"),
        ("admin_add", "Admin tomonidan qo'shildi"),
        ("admin_remove", "Admin tomonidan olib tashlandi"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cc_transactions",
    )
    amount = models.IntegerField()
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "cc_transactions"
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.amount > 0 else ""
        return f"{self.user.username}: {sign}{self.amount} CC ({self.get_transaction_type_display()})"
