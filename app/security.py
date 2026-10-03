import base64
import hashlib
import hmac
import json
import secrets
import time

from app.settings import load_settings

PASSWORD_ITERATIONS = 600_000
TOKEN_TTL_SECONDS = 3600


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_access_token(user_id: int) -> str:
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(
        json.dumps(
            {"sub": str(user_id), "exp": int(time.time()) + TOKEN_TTL_SECONDS},
            separators=(",", ":"),
        ).encode()
    )
    signing_input = f"{header}.{payload}"
    signature = hmac.new(
        load_settings().jwt_secret.encode(), signing_input.encode(), hashlib.sha256
    ).digest()
    return f"{signing_input}.{_b64(signature)}"


def parse_access_token(token: str) -> int | None:
    try:
        header, payload, signature = token.split(".")
        signing_input = f"{header}.{payload}"
        expected = hmac.new(
            load_settings().jwt_secret.encode(), signing_input.encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_unb64(signature), expected):
            return None
        if json.loads(_unb64(header)) != {"alg": "HS256", "typ": "JWT"}:
            return None
        claims = json.loads(_unb64(payload))
        if not isinstance(claims, dict) or not isinstance(claims.get("exp"), int):
            return None
        if claims["exp"] <= int(time.time()):
            return None
        user_id = int(claims["sub"])
        return user_id if user_id > 0 and str(user_id) == claims["sub"] else None
    except (ValueError, TypeError, KeyError, UnicodeDecodeError, base64.binascii.Error):
        return None
