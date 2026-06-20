import uuid as uuid_module
from django.contrib.auth import authenticate
from django.http import JsonResponse, HttpResponse
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from apps.accounts.models import User
from apps.launcher.authentication import LauncherTokenAuthentication
from .models import YggdrasilToken, YggdrasilSession
from .utils import (
    uuid_to_unhyphenated,
    unhyphenated_to_uuid,
    get_user_textures,
    load_public_key_pem,
)


def yggdrasil_error(error_type, message, status=400):
    """Helper to return Yggdrasil specification compliant errors."""
    return JsonResponse(
        {
            "error": error_type,
            "errorMessage": message
        },
        status=status
    )


class YggdrasilMetadataView(APIView):
    """Metadata root endpoint. Required by authlib-injector client."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        public_key_pem = load_public_key_pem()
        return JsonResponse({
            "meta": {
                "implementationName": "CyberCraft Yggdrasil Auth",
                "implementationVersion": "1.0.0",
                "links": {
                    "homepage": "https://cybercraft.uz",
                    "register": "https://cybercraft.uz/register"
                }
            },
            "skinDomains": [
                "cybercraft.uz",
                "localhost",
                "127.0.0.1"
            ],
            "signaturePublickey": public_key_pem
        })


class YggdrasilAuthenticateView(APIView):
    """Authenticate player via username/email and password."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username_or_email = request.data.get("username")
        password = request.data.get("password")
        client_token = request.data.get("clientToken")
        request_user = request.data.get("requestUser", False)

        if not username_or_email or not password:
            return yggdrasil_error("IllegalArgumentException", "Username/Email va parolni kiriting.")

        # Resolve username if email is passed
        user = None
        if "@" in username_or_email:
            user = User.objects.filter(email=username_or_email).first()
        else:
            user = User.objects.filter(username=username_or_email).first()

        if not user:
            return yggdrasil_error("ForbiddenOperationException", "Foydalanuvchi topilmadi.")

        authenticated_user = authenticate(username=user.username, password=password)
        if not authenticated_user:
            return yggdrasil_error("ForbiddenOperationException", "Parol noto'g'ri.")

        if not authenticated_user.is_active:
            return yggdrasil_error("ForbiddenOperationException", "Foydalanuvchi akkaunti faol emas.")

        if authenticated_user.is_banned:
            return yggdrasil_error(
                "ForbiddenOperationException",
                f"Siz bloklangansiz. Sababi: {authenticated_user.ban_reason or 'Belgilanmagan'}"
            )

        # Generate a Yggdrasil token
        token = YggdrasilToken.objects.create(
            user=authenticated_user,
            client_token=client_token
        )

        profile = {
            "id": uuid_to_unhyphenated(authenticated_user.minecraft_uuid),
            "name": authenticated_user.username,
            "legacy": False
        }

        response_data = {
            "accessToken": token.access_token,
            "clientToken": token.client_token,
            "availableProfiles": [profile],
            "selectedProfile": profile
        }

        if request_user:
            response_data["user"] = {
                "id": str(authenticated_user.id),
                "properties": []
            }

        return JsonResponse(response_data)


class YggdrasilLauncherAuthenticateView(APIView):
    """Authenticate player using existing LauncherToken."""
    authentication_classes = [LauncherTokenAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if user.is_banned:
            return yggdrasil_error(
                "ForbiddenOperationException",
                f"Siz bloklangansiz. Sababi: {user.ban_reason or 'Belgilanmagan'}"
            )

        client_token = request.data.get("clientToken", uuid_module.uuid4().hex)

        # Generate a Yggdrasil token
        token = YggdrasilToken.objects.create(
            user=user,
            client_token=client_token
        )

        profile = {
            "id": uuid_to_unhyphenated(user.minecraft_uuid),
            "name": user.username,
            "legacy": False
        }

        return JsonResponse({
            "accessToken": token.access_token,
            "clientToken": token.client_token,
            "availableProfiles": [profile],
            "selectedProfile": profile
        })


class YggdrasilRefreshView(APIView):
    """Refresh accessToken using existing accessToken."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        access_token = request.data.get("accessToken")
        client_token = request.data.get("clientToken")

        token = YggdrasilToken.objects.filter(access_token=access_token).first()
        if not token or token.is_expired():
            return yggdrasil_error("ForbiddenOperationException", "Token eskirgan yoki noto'g'ri.")

        if client_token and token.client_token != client_token:
            return yggdrasil_error("ForbiddenOperationException", "ClientToken mos kelmadi.")

        user = token.user
        if user.is_banned:
            return yggdrasil_error(
                "ForbiddenOperationException",
                f"Siz bloklangansiz. Sababi: {user.ban_reason or 'Belgilanmagan'}"
            )

        # Remove old token and issue a fresh one
        token.delete()
        new_token = YggdrasilToken.objects.create(
            user=user,
            client_token=client_token or token.client_token
        )

        profile = {
            "id": uuid_to_unhyphenated(user.minecraft_uuid),
            "name": user.username,
            "legacy": False
        }

        return JsonResponse({
            "accessToken": new_token.access_token,
            "clientToken": new_token.client_token,
            "availableProfiles": [profile],
            "selectedProfile": profile
        })


class YggdrasilValidateView(APIView):
    """Validate if an accessToken is active."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        access_token = request.data.get("accessToken")
        token = YggdrasilToken.objects.filter(access_token=access_token).first()
        if not token or token.is_expired():
            return yggdrasil_error("ForbiddenOperationException", "Token eskirgan yoki faol emas.", status=403)
        return HttpResponse(status=204)


class YggdrasilInvalidateView(APIView):
    """Invalidate (delete) an accessToken."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        access_token = request.data.get("accessToken")
        YggdrasilToken.objects.filter(access_token=access_token).delete()
        return HttpResponse(status=204)


class YggdrasilSignoutView(APIView):
    """Signout user, invalidating all their tokens."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")

        user = User.objects.filter(username=username).first()
        if not user:
            user = User.objects.filter(email=username).first()

        if not user:
            return yggdrasil_error("ForbiddenOperationException", "Foydalanuvchi topilmadi.")

        authenticated_user = authenticate(username=user.username, password=password)
        if not authenticated_user:
            return yggdrasil_error("ForbiddenOperationException", "Parol noto'g'ri.")

        YggdrasilToken.objects.filter(user=authenticated_user).delete()
        return HttpResponse(status=204)


class YggdrasilJoinView(APIView):
    """Called by client to initialize joining a Minecraft server."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        access_token = request.data.get("accessToken")
        selected_profile = request.data.get("selectedProfile")
        server_id = request.data.get("serverId")

        if not access_token or not selected_profile or not server_id:
            return yggdrasil_error("IllegalArgumentException", "Parametrlar yetarli emas.")

        token = YggdrasilToken.objects.filter(access_token=access_token).first()
        if not token or token.is_expired():
            return yggdrasil_error("ForbiddenOperationException", "Token topilmadi yoki muddati o'tgan.", status=403)

        user = token.user
        if uuid_to_unhyphenated(user.minecraft_uuid) != selected_profile.lower():
            return yggdrasil_error("ForbiddenOperationException", "Profil mos kelmadi.", status=403)

        if user.is_banned:
            return yggdrasil_error(
                "ForbiddenOperationException",
                f"Akkauntingiz bloklangan. Sababi: {user.ban_reason or 'Belgilanmagan'}",
                status=403
            )

        if not user.is_whitelisted:
            return yggdrasil_error("ForbiddenOperationException", "Siz whitelist ro'yxatida emassiz.", status=403)

        # Clear existing sessions for the user and clean up expired ones
        YggdrasilSession.objects.filter(user=user).delete()
        YggdrasilSession.cleanup_expired()

        # Create new join session
        YggdrasilSession.objects.create(
            user=user,
            access_token=access_token,
            server_id=server_id
        )

        return HttpResponse(status=204)


class YggdrasilHasJoinedView(APIView):
    """Called by Minecraft server to verify player's credentials."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        username = request.GET.get("username")
        server_id = request.GET.get("serverId")

        if not username or not server_id:
            return HttpResponse(status=204)

        # Clear expired sessions first
        YggdrasilSession.cleanup_expired()

        session = YggdrasilSession.objects.filter(
            user__username__iexact=username,
            server_id=server_id
        ).select_related("user").first()

        if not session or session.is_expired():
            return HttpResponse(status=204)

        user = session.user
        if user.is_banned:
            return HttpResponse(status=204)

        # Consume session (one-time check)
        session.delete()

        # Create signed texture payload
        textures_data = get_user_textures(user, request)

        response_data = {
            "id": uuid_to_unhyphenated(user.minecraft_uuid),
            "name": user.username,
            "properties": [
                {
                    "name": "textures",
                    "value": textures_data["value"],
                    "signature": textures_data["signature"]
                }
            ]
        }

        return JsonResponse(response_data)


class YggdrasilProfileView(APIView):
    """Get player profile by UUID with signed textures."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, uuid):
        standard_uuid = unhyphenated_to_uuid(uuid)
        user = User.objects.filter(minecraft_uuid=standard_uuid).first()
        if not user:
            return JsonResponse(
                {"error": "ProfileNotFoundException", "errorMessage": "Profil topilmadi."},
                status=404
            )

        unsigned = request.GET.get("unsigned", "false").lower() == "true"
        textures_data = get_user_textures(user, request)

        prop = {
            "name": "textures",
            "value": textures_data["value"]
        }
        if not unsigned:
            prop["signature"] = textures_data["signature"]

        response_data = {
            "id": uuid_to_unhyphenated(user.minecraft_uuid),
            "name": user.username,
            "properties": [prop]
        }

        return JsonResponse(response_data)


class YggdrasilProfileLookupView(APIView):
    """Lookup profiles by a list of names."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        usernames = request.data
        if not isinstance(usernames, list):
            return yggdrasil_error("IllegalArgumentException", "Usernames massiv formatida bo'lishi kerak.")

        users = User.objects.filter(username__in=usernames)
        profiles = []
        for u in users:
            profiles.append({
                "id": uuid_to_unhyphenated(u.minecraft_uuid),
                "name": u.username
            })
        return JsonResponse(profiles, safe=False)

    def get(self, request):
        username = request.GET.get("name")
        if not username:
            return JsonResponse([], safe=False)

        user = User.objects.filter(username=username).first()
        if not user:
            return JsonResponse([], safe=False)

        return JsonResponse([{
            "id": uuid_to_unhyphenated(user.minecraft_uuid),
            "name": user.username
        }], safe=False)
