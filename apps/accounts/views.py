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
from PIL import Image
import io
import os
import random
import logging
from apps.launcher.models import LauncherToken
from apps.launcher.authentication import LauncherTokenAuthentication
from .models import AdminToken, User
from .serializers import (
    UserMinimalSerializer,
    AdminUserSerializer,
    UserRegisterSerializer,
)
from .authentication import AdminTokenAuthentication

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


class UserRegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = UserRegisterSerializer(data=request.data)

        if serializer.is_valid():
            user = serializer.save()

            assign_random_skin(user)

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

        token, created = LauncherToken.objects.get_or_create(user=user)

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
        LauncherToken.objects.filter(user=request.user).delete()
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

        if not user.is_staff:
            return Response(
                {"error": "Admin paneliga kirish huquqi yo'q"},
                status=status.HTTP_403_FORBIDDEN,
            )

        AdminToken.objects.filter(user=user).delete()
        token = AdminToken.objects.create(user=user)

        return Response({"token": token.key, "user": AdminUserSerializer(user).data})


class AdminLogoutView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        AdminToken.objects.filter(user=request.user).delete()
        return Response({"message": "Muvaffaqiyatli chiqildi"})


class AdminMeView(APIView):
    authentication_classes = [AdminTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_staff:
            return Response(
                {"error": "Admin paneliga kirish huquqi yo'q"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response({"user": AdminUserSerializer(request.user).data})


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


@api_view(["POST"])
@permission_classes([AllowAny])
def minecraft_auth(request):
    username = request.data.get("username")
    uuid = request.data.get("uuid")

    if not username or not uuid:
        return Response(status=400)

    user = User.objects.filter(username=username).first()

    if not user:
        return Response(status=403)

    if user.minecraft_uuid != uuid:
        user.minecraft_uuid = uuid
        user.save(update_fields=["minecraft_uuid"])

    if not user.is_whitelisted:
        return Response(status=403)

    return Response(status=200)


class MinecraftVerifyView(APIView):

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        uuid = request.data.get("uuid")
        token = request.data.get("token")

        if not token:
            return Response(
                {
                    "allowed": False,
                    "reason": "Token topilmadi. Faqat CyberCraft launcher orqali kiring.",
                    "kick_message": "§c§lKirish rad etildi!\n\n§eSiz faqat CyberCraft launcher orqali kira olasiz.\n§7Launcher: §bcybercraft.uz/download",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if not uuid:
            return Response(
                {
                    "allowed": False,
                    "reason": "UUID topilmadi.",
                    "kick_message": "§c§lKirish rad etildi!\n\n§ePlayer UUID topilmadi.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            launcher_token = LauncherToken.objects.select_related("user").get(key=token)
        except LauncherToken.DoesNotExist:
            return Response(
                {
                    "allowed": False,
                    "reason": "Token noto'g'ri yoki muddati tugagan.",
                    "kick_message": "§c§lKirish rad etildi!\n\n§eToken noto'g'ri yoki muddati tugagan.\n§7Iltimos, launcherda qayta login qiling.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        user = launcher_token.user

        if not user.is_active:
            return Response(
                {
                    "allowed": False,
                    "reason": "Akkaunt faol emas.",
                    "kick_message": "§c§lKirish rad etildi!\n\n§eAkkauntingiz bloklangan.\n§7Yordam: §bcybercraft.uz/support",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        import uuid as uuid_module

        expected_uuid = str(
            uuid_module.uuid3(
                uuid_module.NAMESPACE_DNS, f"OfflinePlayer:{user.username}"
            )
        )

        uuid_clean = uuid.replace("-", "").lower()
        expected_uuid_clean = expected_uuid.replace("-", "").lower()

        if uuid_clean != expected_uuid_clean:
            return Response(
                {
                    "allowed": False,
                    "reason": "UUID mos kelmadi. Username bilan kiring.",
                    "kick_message": "§c§lKirish rad etildi!\n\n§eUsername mos kelmadi.\n§7Launcherdagi username bilan kiring.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if user.minecraft_uuid != expected_uuid:
            user.minecraft_uuid = expected_uuid
            user.save(update_fields=["minecraft_uuid"])

        return Response(
            {
                "allowed": True,
                "username": user.username,
                "uuid": expected_uuid,
                "is_operator": user.is_operator,
                "is_whitelisted": user.is_whitelisted,
            },
            status=status.HTTP_200_OK,
        )


class SendVerificationEmailView(APIView):
    """Email tasdiqlash xabarini yuborish."""

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
