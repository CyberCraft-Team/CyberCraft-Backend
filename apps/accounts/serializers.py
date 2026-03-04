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
        ]


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "is_staff",
            "is_superuser",
            "is_whitelisted",
            "is_operator",
            "created_at",
        ]


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password_confirm = serializers.CharField(write_only=True)
    referral_code = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "password_confirm",
            "referral_code",
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
        return value

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Bu email allaqachon ro'yxatdan o'tgan")
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

        referrer = None
        if referral_code:
            referrer = User.objects.filter(referral_code=referral_code).first()

        user = User(**validated_data)
        if referrer:
            user.referred_by = referrer
        user.set_password(password)
        user.save()

        if referrer:
            from apps.rewards.models import CCTransaction

            referrer.cc_balance += 10
            referrer.save(update_fields=["cc_balance"])
            CCTransaction.objects.create(
                user=referrer,
                amount=10,
                transaction_type="referral_inviter",
                description=f"{user.username} ro'yxatdan o'tdi",
            )

            user.cc_balance += 5
            user.save(update_fields=["cc_balance"])
            CCTransaction.objects.create(
                user=user,
                amount=5,
                transaction_type="referral_invitee",
                description=f"{referrer.username} tomonidan taklif qilindi",
            )

        return user
