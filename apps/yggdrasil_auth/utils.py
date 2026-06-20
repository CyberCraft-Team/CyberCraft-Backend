import os
import time
import base64
import json
import uuid as uuid_module
from django.conf import settings
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

KEYS_DIR = os.path.join(settings.BASE_DIR, "config", "yggdrasil_keys")
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "private.pem")
PUBLIC_KEY_PATH = os.path.join(KEYS_DIR, "public.pem")


def ensure_keys():
    """Ensure RSA key pair exists, generating one if not present."""
    if not os.path.exists(KEYS_DIR):
        os.makedirs(KEYS_DIR)
    if not os.path.exists(PRIVATE_KEY_PATH) or not os.path.exists(PUBLIC_KEY_PATH):
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
        )
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        with open(PRIVATE_KEY_PATH, "wb") as f:
            f.write(private_pem)
        with open(PUBLIC_KEY_PATH, "wb") as f:
            f.write(public_pem)


def load_private_key():
    """Load the private key from the filesystem."""
    ensure_keys()
    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def load_public_key_pem():
    """Load the public key as a PEM encoded string."""
    ensure_keys()
    with open(PUBLIC_KEY_PATH, "r") as f:
        return f.read()


def sign_data(data_str: str) -> str:
    """Sign data using SHA1withRSA and return base64 encoded signature."""
    private_key = load_private_key()
    data_bytes = data_str.encode("utf-8")
    signature_bytes = private_key.sign(
        data_bytes,
        padding.PKCS1v15(),
        hashes.SHA1()
    )
    return base64.b64encode(signature_bytes).decode("utf-8")


def uuid_to_unhyphenated(uuid_str: str) -> str:
    """Convert standard UUID with hyphens to Yggdrasil unhyphenated hex string."""
    if not uuid_str:
        return ""
    return uuid_str.replace("-", "").lower()


def unhyphenated_to_uuid(uuid_str: str) -> str:
    """Convert unhyphenated hex string to standard UUID with hyphens."""
    if not uuid_str:
        return ""
    uuid_str = uuid_str.replace("-", "").lower()
    if len(uuid_str) != 32:
        return uuid_str
    return f"{uuid_str[:8]}-{uuid_str[8:12]}-{uuid_str[12:16]}-{uuid_str[16:20]}-{uuid_str[20:]}"


def get_user_textures(user, request=None):
    """Generate and sign player skin/cape textures in Yggdrasil property format."""
    # Construct base URL for skins/capes
    base_url = getattr(settings, "SITE_URL", "http://localhost:8000")
    if request:
        # Get host and protocol from request
        base_url = request.build_absolute_uri('/')[:-1]

    textures = {}
    if user.skin:
        textures["SKIN"] = {
            "url": f"{base_url}{user.skin.url}"
        }
    if user.cape:
        textures["CAPE"] = {
            "url": f"{base_url}{user.cape.url}"
        }

    textures_json = {
        "timestamp": int(time.time() * 1000),
        "profileId": uuid_to_unhyphenated(user.minecraft_uuid),
        "profileName": user.username,
        "textures": textures
    }

    # Base64 encode texture meta payload
    json_bytes = json.dumps(textures_json).encode("utf-8")
    value = base64.b64encode(json_bytes).decode("utf-8")

    # Cryptographically sign the payload
    signature = sign_data(value)

    return {
        "value": value,
        "signature": signature
    }
