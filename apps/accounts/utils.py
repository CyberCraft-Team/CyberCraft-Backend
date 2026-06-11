"""Email utility functions."""

import logging
from django.core.mail import send_mail
from django.conf import settings

logger = logging.getLogger(__name__)


def send_verification_email(user, token):
    """Email tasdiqlash xabarini yuborish."""
    verify_url = f"{settings.SITE_URL}/verify-email?token={token.token}"

    subject = "CyberCraft — Emailingizni tasdiqlang"
    message = (
        f"Salom, {user.username}!\n\n"
        f"CyberCraft'ga ro'yxatdan o'tganingiz uchun rahmat.\n"
        f"Emailingizni tasdiqlash uchun quyidagi havolaga bosing:\n\n"
        f"{verify_url}\n\n"
        f"Havola 24 soat amal qiladi.\n\n"
        f"Agar siz ro'yxatdan o'tmagan bo'lsangiz, bu xabarni e'tiborsiz qoldiring."
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Verification email sent to %s", user.email)
        return True
    except Exception as e:
        logger.error("Failed to send verification email to %s: %s", user.email, e)
        return False


def send_password_reset_email(user, token):
    """Parol tiklash xabarini yuborish."""
    reset_url = f"{settings.SITE_URL}/reset-password?token={token.token}"

    subject = "CyberCraft — Parolni tiklash"
    message = (
        f"Salom, {user.username}!\n\n"
        f"Parolingizni tiklash uchun quyidagi havolaga bosing:\n\n"
        f"{reset_url}\n\n"
        f"Havola 1 soat amal qiladi.\n\n"
        f"Agar siz parolni tiklamagan bo'lsangiz, bu xabarni e'tiborsiz qoldiring."
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Password reset email sent to %s", user.email)
        return True
    except Exception as e:
        logger.error("Failed to send password reset email to %s: %s", user.email, e)
        return False


def process_and_save_skin(user, skin_file):
    """Yuklangan skin faylini qayta ishlaydi va foydalanuvchiga biriktiradi.
    Yuz qismini (face) avtomatik kesib oladi.
    """
    from PIL import Image
    import io
    from django.core.files.base import ContentFile

    img = Image.open(skin_file)

    # Esda tuting: skin o'lchamlari validator orqali tekshirilgan.
    # User skin va skin_face larini tozalash (agar mavjud bo'lsa)
    if user.skin:
        user.skin.delete(save=False)
    if user.skin_face:
        user.skin_face.delete(save=False)

    # Face kesib olish (8, 8, 16, 16)
    face = img.crop((8, 8, 16, 16))
    face_scaled = face.resize((64, 64), Image.NEAREST)

    face_io = io.BytesIO()
    face_scaled.save(face_io, format="PNG")
    face_io.seek(0)

    skin_file.seek(0)
    user.skin.save(
        f"{user.username}_skin.png",
        ContentFile(skin_file.read()),
        save=False,
    )

    user.skin_face.save(
        f"{user.username}_face.png",
        ContentFile(face_io.read()),
        save=True,
    )

