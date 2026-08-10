from rest_framework import serializers
from .models import User


class MediaUrlMixin:
    """Shared mixin for generating absolute media URLs."""

    def _get_media_url(self, obj, field_name):
        field = getattr(obj, field_name, None)
        if field:
            request = self.context.get("request")
            return request.build_absolute_uri(field.url) if request else field.url
        return None

    def get_skin_url(self, obj):
        return self._get_media_url(obj, "skin")

    def get_skin_face_url(self, obj):
        return self._get_media_url(obj, "skin_face")

    def get_cape_url(self, obj):
        return self._get_media_url(obj, "cape")


class UserSerializer(MediaUrlMixin, serializers.ModelSerializer):
    skin_url = serializers.SerializerMethodField()
    skin_face_url = serializers.SerializerMethodField()
    cape_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "minecraft_uuid",
            "skin_url",
            "skin_face_url",
            "cape_url",
            "is_whitelisted",
            "is_operator",
            "is_staff",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class UserMinimalSerializer(MediaUrlMixin, serializers.ModelSerializer):
    skin_url = serializers.SerializerMethodField()
    skin_face_url = serializers.SerializerMethodField()
    cape_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "skin_url",
            "skin_face_url",
            "cape_url",
            "is_whitelisted",
            "is_operator",
            "is_staff",
            "is_superuser",
            "cc_balance",
            "rank",
            "referral_code",
            "is_email_verified",
        ]


class AdminUserSerializer(MediaUrlMixin, serializers.ModelSerializer):
    skin_face_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "minecraft_uuid",
            "skin_face_url",
            "is_staff",
            "is_superuser",
            "is_whitelisted",
            "is_operator",
            "is_banned",
            "ban_reason",
            "banned_until",
            "is_email_verified",
            "cc_balance",
            "rank",
            "referral_code",
            "last_login",
            "created_at",
        ]


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True)
    referral_code = serializers.CharField(required=False, allow_blank=True)
    skin = serializers.ImageField(write_only=True, required=True)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password_confirm",
            "referral_code",
            "skin",
        ]

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Bu username allaqachon mavjud")
        if len(value) < 3:
            raise serializers.ValidationError(
                "Username kamida 3 ta belgi bo'lishi kerak"
            )
        if len(value) > 16:
            raise serializers.ValidationError(
                "Username 16 ta belgidan oshmasligi kerak"
            )
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', value):
            raise serializers.ValidationError(
                "Username faqat harflar, raqamlar va pastki chiziqdan (_) iborat bo'lishi kerak"
            )
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Bu email allaqachon ro'yxatdan o'tgan")
        return value

    def validate_skin(self, value):
        if not value:
            raise serializers.ValidationError("Skin fayli yuklanishi shart")

        if not value.name.lower().endswith(".png"):
            raise serializers.ValidationError("Faqat PNG formatdagi fayllar qabul qilinadi")

        if value.size > 256 * 1024:
            raise serializers.ValidationError("Skin fayl hajmi 256KB dan oshmasligi kerak")

        try:
            from PIL import Image
            img = Image.open(value)
            if img.size not in [(64, 64), (64, 32)]:
                raise serializers.ValidationError("Skin o'lchami 64x64 yoki 64x32 bo'lishi kerak")
        except Exception as e:
            raise serializers.ValidationError(f"Skin faylini tekshirishda xatolik: {str(e)}")

        return value

    def validate(self, data):
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Parollar mos kelmadi"}
            )
        return data

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        referral_code = validated_data.pop("referral_code", None)
        skin_file = validated_data.pop("skin")

        referrer = None
        if referral_code:
            referrer = User.objects.filter(referral_code=referral_code).first()

        user = User(**validated_data)
        if referrer:
            user.referred_by = referrer
        user.set_password(password)
        user.save()

        from .utils import process_and_save_skin
        process_and_save_skin(user, skin_file)

        # The referral bonus is awarded by the on_referral_bonus post_save
        # receiver in signals.py, which fired during user.save() above --
        # referred_by was already set at that point. Awarding it here too is
        # what gave the inviter 20 CC instead of 10 and wrote four
        # CCTransaction rows per signup. The signal is the single place: it
        # covers the Google and Telegram registration paths as well, which
        # never went through this serializer.
        user.refresh_from_db(fields=["cc_balance"])

        return user

