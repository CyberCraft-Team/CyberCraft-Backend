from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.generics import ListAPIView, RetrieveUpdateDestroyAPIView
from django.contrib.auth import authenticate
from django.core.files.base import ContentFile
from django.conf import settings
from django.utils import timezone
from PIL import Image
import io
import os
import random
import logging
import hmac
import hashlib
import time
from apps.launcher.authentication import LauncherTokenAuthentication
from .models import AuthToken, User
from .serializers import (
    UserMinimalSerializer,
    AdminUserSerializer,
    UserRegisterSerializer,
)
from .authentication import AdminTokenAuthentication
from .permissions import IsTrustedMod
from google.oauth2 import id_token
from google.auth.transport import requests

logger = logging.getLogger(__name__)

MAX_SKIN_SIZE = 256 * 1024
MAX_CAPE_SIZE = 512 * 1024


def assign_random_skin(user):
    default_skins_dir = os.path.join(settings.MEDIA_ROOT, "default_skins")

    if os.path.exists(default_skins_dir):
        skin_files = [
            f
            for f in os.listdir(default_skins_dir)
            if f.endswith((".png", ".jpg", ".jpeg"))
        ]

        if skin_files:
            random_skin = random.choice(skin_files)
            skin_path = os.path.join(default_skins_dir, random_skin)

            try:
                with open(skin_path, "rb") as f:
                    skin_content = f.read()
                    user.skin_face.save(
                        f"{user.username}_face.png",
                        ContentFile(skin_content),
                        save=True,
                    )
                return True
            except Exception as e:
                logger.error("Random skin tayinlashda xatolik: %s", e)
                return False

    random_user = (
        User.objects.exclude(skin_face="")
        .exclude(skin_face__isnull=True)
        .exclude(id=user.id)
        .order_by("?")
        .first()
    )

    if random_user:
        try:
            with open(random_user.skin_face.path, "rb") as f:
                skin_content = f.read()
                user.skin_face.save(
                    f"{user.username}_face.png", ContentFile(skin_content), save=True
                )
            return True
        except Exception as e:
            logger.error("Mavjud foydalanuvchi skinidan nusxa olishda xatolik: %s", e)
            return False

    return False


class PlayerSkinView(APIView):
    """Username bo'yicha o'yinchining skinini qaytaradi (public, auth kerak emas).

    GET /api/player/<username>/skin/ -> skin PNG fayli
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, username):
        from django.http import FileResponse, Http404

        try:
            user = User.objects.only("skin").get(username__iexact=username)
        except User.DoesNotExist:
            raise Http404("O'yinchi topilmadi")

        if not user.skin:
            raise Http404("O'yinchida skin mavjud emas")

        try:
            return FileResponse(
                user.skin.open("rb"),
                content_type="image/png",
                as_attachment=False,
            )
        except FileNotFoundError:
            raise Http404("Skin fayli topilmadi")


class UserRegisterView(APIView):
    throttle_scope = "sensitive"
    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data, context={"request": request})

        if serializer.is_valid():
            user = serializer.save()

            return Response(
                {
                    "message": "Ro'yxatdan muvaffaqiyatli o'tdingiz! Endi launcherdan kirishingiz mumkin.",
                    "user": {
                        "id": user.id,
                        "username": user.username,
                        "email": user.email,
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {"errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )


class LauncherLoginView(APIView):
    throttle_scope = "sensitive"
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        if not username or not password:
            return Response(
                {"error": "Username va password talab qilinadi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(username=username, password=password)

        if not user:
            return Response(
                {"error": "Username yoki password noto'g'ri"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": "Akkaunt faol emas"}, status=status.HTTP_403_FORBIDDEN
            )

        # Faqat eskirgan (expired) tokenlarni o'chirish va yangi yaratish
        AuthToken.objects.filter(user=user, scope=AuthToken.Scope.LAUNCHER).expired().delete()
        token = AuthToken.issue(user, AuthToken.Scope.LAUNCHER)

        return Response(
            {
                "token": token.key,
                "user": UserMinimalSerializer(user, context={"request": request}).data,
            }
        )


class LauncherLogoutView(APIView):
    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        AuthToken.objects.filter(user=request.user, scope=AuthToken.Scope.LAUNCHER).delete()
        return Response({"message": "Muvaffaqiyatli chiqildi"})


class LauncherMeView(APIView):
    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "user": UserMinimalSerializer(
                    request.user, context={"request": request}
                ).data
            }
        )


class SkinUploadView(APIView):
    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        skin_file = request.FILES.get("skin")

        if not skin_file:
            return Response(
                {"error": "Skin fayli yuklanmadi"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not skin_file.name.lower().endswith(".png"):
            return Response(
                {"error": "Faqat PNG formatdagi fayllar qabul qilinadi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if skin_file.size > MAX_SKIN_SIZE:
            return Response(
                {"error": "Skin fayl hajmi 256KB dan oshmasligi kerak"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            img = Image.open(skin_file)

            if img.size not in [(64, 64), (64, 32)]:
                return Response(
                    {"error": "Skin o'lchami 64x64 yoki 64x32 bo'lishi kerak"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if request.user.skin:
                request.user.skin.delete(save=False)
            if request.user.skin_face:
                request.user.skin_face.delete(save=False)

            face = img.crop((8, 8, 16, 16))

            face_scaled = face.resize((64, 64), Image.NEAREST)

            face_io = io.BytesIO()
            face_scaled.save(face_io, format="PNG")
            face_io.seek(0)

            skin_file.seek(0)
            request.user.skin.save(
                f"{request.user.username}_skin.png",
                ContentFile(skin_file.read()),
                save=False,
            )

            request.user.skin_face.save(
                f"{request.user.username}_face.png",
                ContentFile(face_io.read()),
                save=True,
            )

            return Response(
                {
                    "message": "Skin muvaffaqiyatli yuklandi",
                    "skin_face_url": (
                        request.build_absolute_uri(request.user.skin_face.url)
                        if request.user.skin_face
                        else None
                    ),
                }
            )

        except Exception as e:
            return Response(
                {"error": f"Skin yuklashda xatolik: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class CapeUploadView(APIView):
    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        cape_file = request.FILES.get("cape")

        if not cape_file:
            return Response(
                {"error": "Plash fayli yuklanmadi"}, status=status.HTTP_400_BAD_REQUEST
            )

        if not cape_file.name.lower().endswith(".png"):
            return Response(
                {"error": "Faqat PNG formatdagi fayllar qabul qilinadi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if cape_file.size > MAX_CAPE_SIZE:
            return Response(
                {"error": "Plash fayl hajmi 512KB dan oshmasligi kerak"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            img = Image.open(cape_file)
            w, h = img.size

            valid_sizes = [
                (64, 32),
                (22, 17),
                (46, 22),
                (1024, 512),
                (128, 64),
                (256, 128),
                (512, 256),
            ]
            if (w, h) not in valid_sizes and not (w == h * 2):
                return Response(
                    {
                        "error": f"Plash o'lchami noto'g'ri. Yuborilgan: {w}x{h}. Qabul qilinadigan o'lchamlar: 64x32, 22x17 va h.k."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if request.user.cape:
                request.user.cape.delete(save=False)

            cape_file.seek(0)
            request.user.cape.save(
                f"{request.user.username}_cape.png",
                ContentFile(cape_file.read()),
                save=True,
            )

            return Response(
                {
                    "message": "Plash muvaffaqiyatli yuklandi",
                    "cape_url": (
                        request.build_absolute_uri(request.user.cape.url)
                        if request.user.cape
                        else None
                    ),
                }
            )

        except Exception as e:
            return Response(
                {"error": f"Plash yuklashda xatolik: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class AdminLoginView(APIView):
    throttle_scope = "sensitive"
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        logger.info(f"Admin login so'rovi: username={username}")

        if not username or not password:
            return Response(
                {"error": "Username va password talab qilinadi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(username=username, password=password)

        if not user:
            logger.warning(f"Autentifikatsiya muvaffaqiyatsiz: username={username}")
            return Response(
                {"error": "Username yoki password noto'g'ri"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            logger.warning(f"Foydalanuvchi faol emas: username={username}")
            return Response(
                {"error": "Akkaunt faol emas"}, status=status.HTTP_403_FORBIDDEN
            )

        if not user.is_staff and not user.is_superuser:
            logger.warning(f"Admin huquqi yo'q: username={username}")
            return Response(
                {"error": "Admin paneliga kirish huquqi yo'q"},
                status=status.HTTP_403_FORBIDDEN,
            )

        logger.info(f"Admin muvaffaqiyatli kirdi: username={username}")
        token = AuthToken.issue(user, AuthToken.Scope.ADMIN)

        return Response(
            {
                "token": token.key,
                "user": AdminUserSerializer(user, context={"request": request}).data,
            }
        )


class AdminLogoutView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        AuthToken.objects.filter(user=request.user, scope=AuthToken.Scope.ADMIN).delete()
        return Response({"message": "Muvaffaqiyatli chiqildi"})


class AdminMeView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff and not request.user.is_superuser:
            return Response(
                {"error": "Admin paneliga kirish huquqi yo'q"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({"user": AdminUserSerializer(request.user, context={"request": request}).data})



class AdminUsersListView(ListAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]
    queryset = User.objects.all().order_by("-date_joined")
    serializer_class = AdminUserSerializer


class AdminUserDetailView(RetrieveUpdateDestroyAPIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]
    queryset = User.objects.all()
    serializer_class = AdminUserSerializer


class AdminUserWhitelistView(APIView):
    """User ni whitelist ga qo'shish yoki olib tashlash."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        value = request.data.get("is_whitelisted")
        if value is None:
            # Toggle — hozirgi qiymatni teskari qilish
            value = not user.is_whitelisted

        user.is_whitelisted = bool(value)
        user.save(update_fields=["is_whitelisted"])
        logger.info(f"Admin {request.user.username}: user {user.username} whitelist={user.is_whitelisted}")
        return Response({"is_whitelisted": user.is_whitelisted, "message": "Muvaffaqiyatli saqlandi"})


class AdminUserOperatorView(APIView):
    """User ni operator qilish yoki olib tashlash."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        value = request.data.get("is_operator")
        if value is None:
            value = not user.is_operator

        user.is_operator = bool(value)
        user.save(update_fields=["is_operator"])
        logger.info(f"Admin {request.user.username}: user {user.username} operator={user.is_operator}")
        return Response({"is_operator": user.is_operator, "message": "Muvaffaqiyatli saqlandi"})


class AdminUserStaffView(APIView):
    """User ni staff (admin) qilish yoki olib tashlash. Faqat superuser amalga oshira oladi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        if not request.user.is_superuser:
            return Response(
                {"error": "Staff huquqini faqat superuser o'zgartira oladi"},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        if user.pk == request.user.pk:
            return Response({"error": "O'z huquqingizni o'zgartira olmaysiz"}, status=status.HTTP_400_BAD_REQUEST)

        value = request.data.get("is_staff")
        if value is None:
            value = not user.is_staff

        user.is_staff = bool(value)
        user.save(update_fields=["is_staff"])
        logger.info(f"Admin {request.user.username}: user {user.username} staff={user.is_staff}")
        return Response({"is_staff": user.is_staff, "message": "Muvaffaqiyatli saqlandi"})


class AdminUserBanView(APIView):
    """User ni ban qilish yoki ban dan chiqarish."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        if user.pk == request.user.pk:
            return Response({"error": "O'zingizni ban qila olmaysiz"}, status=status.HTTP_400_BAD_REQUEST)

        action = request.data.get("action")  # "ban" yoki "unban"

        if action == "unban" or (action is None and user.is_banned):
            # Ban dan chiqarish
            user.is_banned = False
            user.ban_reason = ""
            user.banned_until = None
            user.is_active = True
            user.save(update_fields=["is_banned", "ban_reason", "banned_until", "is_active"])
            logger.info(f"Admin {request.user.username}: user {user.username} UNBAN qilindi")
            return Response({"is_banned": False, "message": f"{user.username} ban dan chiqarildi"})
        else:
            # Ban qilish
            reason = request.data.get("reason", "Admin tomonidan ban qilindi")
            banned_until = request.data.get("banned_until", None)  # ISO format yoki null

            user.is_banned = True
            user.ban_reason = reason
            user.is_active = False
            if banned_until:
                from django.utils.dateparse import parse_datetime
                user.banned_until = parse_datetime(banned_until)
            else:
                user.banned_until = None  # Doimiy ban
            user.save(update_fields=["is_banned", "ban_reason", "banned_until", "is_active"])
            logger.info(f"Admin {request.user.username}: user {user.username} BAN qilindi. Sabab: {reason}")
            return Response({"is_banned": True, "message": f"{user.username} ban qilindi"})


class AdminUserSuperuserView(APIView):
    """User ni superuser qilish yoki superuserlikdan chiqarish.
    Faqat mavjud superuserlar (is_superuser=True) amalga oshira oladi."""
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAdminUser]

    def post(self, request, pk):
        # Faqat superuser bu amalni bajara oladi
        if not request.user.is_superuser:
            return Response(
                {"error": "Superuser huquqini faqat superuser o'zgartira oladi"},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"error": "Foydalanuvchi topilmadi"}, status=status.HTTP_404_NOT_FOUND)

        # O'zini superuserlikdan chiqarib qo'yishining oldini olish
        if user.pk == request.user.pk:
            return Response(
                {"error": "O'z superuser huquqingizni o'zgartira olmaysiz"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        value = request.data.get("is_superuser")
        if value is None:
            value = not user.is_superuser

        user.is_superuser = bool(value)
        # Superuser bo'lsa, staff ham bo'lishi kerak
        if user.is_superuser:
            user.is_staff = True
            user.save(update_fields=["is_superuser", "is_staff"])
        else:
            user.save(update_fields=["is_superuser"])

        action_str = "SUPERUSER qilindi" if user.is_superuser else "Superuserlikdan chiqarildi"
        logger.info(f"Admin {request.user.username}: user {user.username} {action_str}")
        return Response({
            "is_superuser": user.is_superuser,
            "is_staff": user.is_staff,
            "message": f"{user.username} {action_str.lower()}",
        })


class MinecraftSessionCreateView(APIView):
    """Launcher serverga ulanishdan oldin session yaratadi.

    Launcher bu endpointni chaqiradi, keyin player serverga ulanadi.
    Server mod player join bo'lganda MinecraftVerifyView orqali tekshiradi.
    """

    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .models import MinecraftSession

        user = request.user

        if not user.is_active:
            return Response(
                {"error": "Akkaunt faol emas"},
                status=status.HTTP_403_FORBIDDEN,
            )

        import uuid as uuid_module

        expected_uuid = str(
            uuid_module.uuid3(
                uuid_module.NAMESPACE_DNS, f"OfflinePlayer:{user.username}"
            )
        )

        # Eski sessionlarni tozalash
        MinecraftSession.cleanup_expired()

        # Bu user uchun mavjud sessionlarni o'chirish
        MinecraftSession.objects.filter(user=user).delete()

        # Yangi session yaratish
        session = MinecraftSession.objects.create(
            user=user,
            username=user.username,
            uuid=expected_uuid,
        )

        # minecraft_uuid ni yangilash
        if user.minecraft_uuid != expected_uuid:
            user.minecraft_uuid = expected_uuid
            user.save(update_fields=["minecraft_uuid"])

        return Response(
            {
                "success": True,
                "username": user.username,
                "uuid": expected_uuid,
                "expires_in": MinecraftSession.SESSION_LIFETIME_SECONDS,
            },
            status=status.HTTP_200_OK,
        )


class MinecraftVerifyView(APIView):
    """Server mod player join bo'lganda chaqiradi.

    Session mavjudligini tekshiradi — agar launcher session yaratgan bo'lsa,
    player kirishga ruxsat beriladi.
    """

    permission_classes = [IsTrustedMod]
    authentication_classes = []

    def post(self, request):
        from .models import MinecraftSession

        username = request.data.get("username")
        uuid = request.data.get("uuid")

        if not username:
            return Response(
                {
                    "allowed": False,
                    "reason": "Username topilmadi.",
                    "kick_message": "§c§lKirish rad etildi!\n\n§ePlayer username topilmadi.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Eskirgan sessionlarni tozalash
        MinecraftSession.cleanup_expired()

        # Session qidirish — username bo'yicha
        session = MinecraftSession.objects.select_related("user").filter(
            username__iexact=username,
            expires_at__gt=timezone.now(),
        ).first()

        if not session:
            return Response(
                {
                    "allowed": False,
                    "reason": "Session topilmadi. Faqat CyberCraft launcher orqali kiring.",
                    "kick_message": "§c§lKirish rad etildi!\n\n§eSiz faqat CyberCraft Launcher orqali kira olasiz.\n§7Launcher yuklab olish: §bcybercraft.uz/download",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user = session.user

        if not user.is_active:
            session.delete()
            return Response(
                {
                    "allowed": False,
                    "reason": "Akkaunt faol emas.",
                    "kick_message": "§c§lKirish rad etildi!\n\n§eAkkauntingiz bloklangan.\n§7Yordam: §bcybercraft.uz/support",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # UUID tekshirish (agar yuborilgan bo'lsa)
        if uuid:
            uuid_clean = uuid.replace("-", "").lower()
            expected_clean = session.uuid.replace("-", "").lower()
            if uuid_clean != expected_clean:
                session.delete()
                return Response(
                    {
                        "allowed": False,
                        "reason": "UUID mos kelmadi.",
                        "kick_message": "§c§lKirish rad etildi!\n\n§eUsername mos kelmadi.\n§7Launcherdagi username bilan kiring.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        # Session ishlatildi — o'chirish
        session.delete()

        return Response(
            {
                "allowed": True,
                "username": user.username,
                "uuid": session.uuid,
                "is_operator": user.is_operator,
                "is_whitelisted": user.is_whitelisted,
            },
            status=status.HTTP_200_OK,
        )


class SendVerificationEmailView(APIView):
    """Email tasdiqlash xabarini yuborish."""

    throttle_scope = "sensitive"
    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.is_email_verified:
            return Response(
                {"message": "Email allaqachon tasdiqlangan"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.email:
            return Response(
                {"error": "Email manzil kiritilmagan"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import EmailVerificationToken

        EmailVerificationToken.objects.filter(user=user).delete()

        token = EmailVerificationToken.objects.create(user=user)

        from .utils import send_verification_email

        send_verification_email(user, token)

        return Response({"message": "Tasdiqlash xabari emailingizga yuborildi"})


class VerifyEmailView(APIView):
    """Email tokenini tasdiqlash."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        token_str = request.data.get("token")

        if not token_str:
            return Response(
                {"error": "Token kiritilmagan"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import EmailVerificationToken

        try:
            token = EmailVerificationToken.objects.select_related("user").get(
                token=token_str
            )
        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"error": "Noto'g'ri yoki muddati o'tgan token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token.is_expired():
            token.delete()
            return Response(
                {"error": "Token muddati tugagan. Yangi xabar yuborish kerak."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token.user
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

        EmailVerificationToken.objects.filter(user=user).delete()

        return Response({"message": "Email muvaffaqiyatli tasdiqlandi!"})


class RequestPasswordResetView(APIView):
    """Parol tiklash so'rovi."""

    throttle_scope = "sensitive"
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response(
                {"error": "Email kiritilmagan"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email=email)

            from .models import PasswordResetToken

            PasswordResetToken.objects.filter(user=user).delete()

            token = PasswordResetToken.objects.create(user=user)

            from .utils import send_password_reset_email

            send_password_reset_email(user, token)
        except User.DoesNotExist:
            pass

        return Response(
            {"message": "Agar email ro'yxatda bo'lsa, tiklash xabari yuborildi"}
        )


class ConfirmPasswordResetView(APIView):
    """Yangi parol o'rnatish."""

    throttle_scope = "sensitive"
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        token_str = request.data.get("token")
        new_password = request.data.get("new_password")

        if not token_str or not new_password:
            return Response(
                {"error": "Token va yangi parol kiritilishi kerak"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_password) < 6:
            return Response(
                {"error": "Parol kamida 6 ta belgidan iborat bo'lishi kerak"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from .models import PasswordResetToken

        try:
            token = PasswordResetToken.objects.select_related("user").get(
                token=token_str, is_used=False
            )
        except PasswordResetToken.DoesNotExist:
            return Response(
                {"error": "Noto'g'ri yoki ishlatilgan token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if token.is_expired():
            token.delete()
            return Response(
                {"error": "Token muddati tugagan. Yangi so'rov yuboring."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = token.user
        user.set_password(new_password)
        user.save(update_fields=["password"])

        token.is_used = True
        token.save(update_fields=["is_used"])

        return Response({"message": "Parol muvaffaqiyatli o'zgartirildi!"})


class GoogleLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        id_token_str = request.data.get("id_token")
        logger.info("Google login so'rovi qabul qilindi")

        if not id_token_str:
            logger.warning("Google ID token yuborilmadi")
            return Response(
                {"error": "Google ID token talab qilinadi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Google ID tokenni tekshirish
            logger.info("Google tokenini tekshirish boshlandi...")
            idinfo = id_token.verify_oauth2_token(
                id_token_str, requests.Request(), settings.GOOGLE_CLIENT_ID,
                # 60 sekund tolerans — server va Google vaqti farqi uchun.
                # Xatolikda 40 sekund farq bor edi: '1781060430 < 1781060470'
                clock_skew_in_seconds=60
            )

            if idinfo["iss"] not in [
                "accounts.google.com",
                "https://accounts.google.com",
            ]:
                logger.error(f"Noto'g'ri issuer: {idinfo['iss']}")
                raise ValueError("Wrong issuer.")

            email = idinfo.get("email")
            full_name = idinfo.get("name", "")
            logger.info(f"Token tekshirildi. Email: {email}")

            if not email:
                logger.warning("Email topilmadi")
                return Response(
                    {"error": "Google hisobida email topilmadi"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Foydalanuvchini qidirish yoki yaratish
            user = User.objects.filter(email=email).first()
            is_new_user = False

            if not user:
                # Yangi foydalanuvchi — username kiritilishi shart
                username = request.data.get("username")
                if not username:
                    logger.info(f"Google login: yangi foydalanuvchi uchun username talab qilinadi: {email}")
                    return Response(
                        {
                            "needs_username": True,
                            "email": email,
                            "is_new_user": True
                        },
                        status=status.HTTP_200_OK
                    )

                username = username.strip()
                if not username:
                    return Response(
                        {"error": "Username kiritilishi shart"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if len(username) < 3:
                    return Response(
                        {"error": "Username kamida 3 ta belgi bo'lishi kerak"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if len(username) > 16:
                    return Response(
                        {"error": "Username 16 ta belgidan oshmasligi kerak"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                import re
                if not re.match(r'^[a-zA-Z0-9_]+$', username):
                    return Response(
                        {"error": "Username faqat harflar, raqamlar va pastki chiziqdan (_) iborat bo'lishi kerak"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if User.objects.filter(username__iexact=username).exists():
                    return Response(
                        {"error": "Bu username allaqachon mavjud"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                logger.info(f"Yangi foydalanuvchi yaratish (Google): {email} -> {username}")
                is_new_user = True
                user = User.objects.create_user(
                    username=username,
                    email=email,
                    first_name=full_name.split(" ")[0] if " " in full_name else full_name,
                    last_name=full_name.split(" ")[1] if " " in full_name else "",
                )
                user.is_email_verified = True
                user.save()
                logger.info(f"Foydalanuvchi yaratildi: {username}")

                # Tasodifiy skin tayinlash
                assign_random_skin(user)
                logger.info("Random skin tayinlandi")
            else:
                if not user.is_email_verified:
                    user.is_email_verified = True
                    user.save(update_fields=["is_email_verified"])
                    logger.info(f"Mavjud foydalanuvchining emaili Google orqali tasdiqlandi: {user.username}")

            if not user.is_active:
                logger.warning(f"Foydalanuvchi faol emas: {user.username}")
                return Response(
                    {"error": "Akkaunt faol emas"}, status=status.HTTP_403_FORBIDDEN
                )

            # LauncherToken yaratish (vebsayt va launcher uchun, faqat eskirganlarini o'chirish)
            AuthToken.objects.filter(user=user, scope=AuthToken.Scope.LAUNCHER).expired().delete()
            token = AuthToken.issue(user, AuthToken.Scope.LAUNCHER)
            logger.info(f"Token yaratildi: {user.username}")

            return Response(
                {
                    "token": token.key,
                    "user": UserMinimalSerializer(user, context={"request": request}).data,
                    "is_new_user": is_new_user,
                }
            )

        except ValueError as e:
            logger.error(f"Google tokeni yaroqsiz: {str(e)}")
            return Response(
                {"error": f"Google tokeni yaroqsiz: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as e:
            logger.exception("Google login jarayonida kutilmagan xatolik yuz berdi")
            return Response(
                {"error": "Tizimda xatolik yuz berdi"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

class TelegramLoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        
        # Support both wrapped and direct payloads for backward compatibility
        if "auth_data" in data:
            auth_data = data.get("auth_data")
            chosen_username = data.get("username")
            use_needs_username_flow = True
        else:
            auth_data = data
            chosen_username = None
            use_needs_username_flow = False

        if not auth_data:
            return Response(
                {"error": "Telegram ma'lumotlari talab qilinadi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        check_hash = auth_data.get("hash")
        if not check_hash:
            return Response(
                {"error": "Telegram hash talab qilinadi"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Telegram ma'lumotlarini tekshirish
        if not self.verify_telegram_auth(auth_data):
            return Response(
                {"error": "Telegram ma'lumotlari haqiqiy emas"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # auth_date tekshirish (1 kun ichida bo'lishi kerak)
        auth_date = int(auth_data.get("auth_date", 0))
        if time.time() - auth_date > 86400:
            return Response(
                {"error": "Avtorizatsiya muddati tugagan"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        telegram_id = auth_data.get("id")
        first_name = auth_data.get("first_name", "")
        last_name = auth_data.get("last_name", "")

        # Foydalanuvchini qidirish (email yo'q bo'lsa telegram_id orqali)
        user = User.objects.filter(telegram_id=telegram_id).first()
        is_new_user = False

        if not user:
            if not use_needs_username_flow:
                # Old auto-generation flow
                telegram_username = auth_data.get("username")
                if not telegram_username:
                    username_to_use = f"tg_{telegram_id}"
                else:
                    username_to_use = telegram_username
                
                # Check for valid characters and length for old flow just in case
                import re
                username_to_use = re.sub(r'[^a-zA-Z0-9_]', '_', username_to_use)
                if len(username_to_use) < 3:
                    username_to_use = f"tg_{telegram_id}"
                elif len(username_to_use) > 16:
                    username_to_use = username_to_use[:16]

                base_username = username_to_use
                counter = 1
                while User.objects.filter(username=username_to_use).exists():
                    username_to_use = f"{base_username}{counter}"
                    if len(username_to_use) > 16:
                        username_to_use = f"{base_username[:10]}{counter}"
                    counter += 1
            else:
                # New username prompt flow
                if not chosen_username:
                    return Response(
                        {
                            "needs_username": True,
                            "is_new_user": True
                        },
                        status=status.HTTP_200_OK
                    )
                
                chosen_username = chosen_username.strip()
                if not chosen_username:
                    return Response(
                        {"error": "Username kiritilishi shart"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if len(chosen_username) < 3:
                    return Response(
                        {"error": "Username kamida 3 ta belgi bo'lishi kerak"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if len(chosen_username) > 16:
                    return Response(
                        {"error": "Username 16 ta belgidan oshmasligi kerak"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                import re
                if not re.match(r'^[a-zA-Z0-9_]+$', chosen_username):
                    return Response(
                        {"error": "Username faqat harflar, raqamlar va pastki chiziqdan (_) iborat bo'lishi kerak"},
                        status=status.HTTP_400_BAD_REQUEST
                    )

                if User.objects.filter(username__iexact=chosen_username).exists():
                    return Response(
                        {"error": "Bu username allaqachon mavjud"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                username_to_use = chosen_username

            user = User.objects.create_user(
                username=username_to_use,
                first_name=first_name,
                last_name=last_name,
                telegram_id=telegram_id
            )
            user.is_email_verified = True # Telegram orqali kirganlar tasdiqlangan deb hisoblanadi
            user.save()
            is_new_user = True
            
            # Skin tayinlash
            assign_random_skin(user)

        # Token yaratish (faqat eskirganlarini o'chirish)
        AuthToken.objects.filter(user=user, scope=AuthToken.Scope.LAUNCHER).expired().delete()
        token = AuthToken.issue(user, AuthToken.Scope.LAUNCHER)

        return Response({
            "token": token.key,
            "user": UserMinimalSerializer(user, context={"request": request}).data,
            "is_new_user": is_new_user
        })

    def verify_telegram_auth(self, auth_data):
        # Hashni olib tashlash
        check_data = auth_data.copy()
        telegram_hash = check_data.pop("hash", None)
        
        # Alfavit tartibida saralash
        data_check_list = []
        for key, value in sorted(check_data.items()):
            if value is not None:
                data_check_list.append(f"{key}={value}")
        
        data_check_string = "\n".join(data_check_list)
        
        # Bot tokenidan foydalanib secret key yaratish
        bot_token = settings.TELEGRAM_BOT_TOKEN
        secret_key = hashlib.sha256(bot_token.encode()).digest()
        
        # Hashni hisoblash
        calculated_hash = hmac.new(
            secret_key, 
            data_check_string.encode(), 
            hashlib.sha256
        ).hexdigest()
        
        return calculated_hash == telegram_hash
