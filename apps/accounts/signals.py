"""Django signals for accounts app."""

import logging
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from apps.notifications.models import Notification

logger = logging.getLogger(__name__)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def on_user_created(sender, instance, created, **kwargs):
    """Yangi foydalanuvchi yaratilganda notification yuborish."""
    if created:
        Notification.send(
            user=instance,
            title="Xush kelibsiz!",
            message=f"CyberCraft'ga xush kelibsiz, {instance.username}! O'yindan rohatlaning.",
            notification_type="success",
        )
        logger.info("Welcome notification sent to new user: %s", instance.username)


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def on_referral_bonus(sender, instance, created, **kwargs):
    """Referral orqali ro'yxatdan o'tganda bonus berish."""
    if created and instance.referred_by:
        inviter = instance.referred_by

        from apps.rewards.models import CCTransaction

        inviter.cc_balance += 10
        inviter.save(update_fields=["cc_balance"])

        CCTransaction.objects.create(
            user=inviter,
            amount=10,
            transaction_type="referral_inviter",
            description=f"{instance.username} taklif orqali qo'shildi",
        )

        Notification.send(
            user=inviter,
            title="Referral bonus!",
            message=f"{instance.username} sizning havolangiz orqali qo'shildi. +10 CC!",
            notification_type="reward",
        )

        instance.cc_balance += 5
        instance.save(update_fields=["cc_balance"])

        CCTransaction.objects.create(
            user=instance,
            amount=5,
            transaction_type="referral_invitee",
            description=f"{inviter.username} tomonidan taklif qilindingiz",
        )

        logger.info(
            "Referral bonus: %s invited %s", inviter.username, instance.username
        )
