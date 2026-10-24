"""Password hashing and signed local dashboard sessions."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from config import AUTH_SECRET

PBKDF2_ITERATIONS = 600_000
SESSION_SECONDS = 8 * 60 * 60


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, rounds, salt_hex, digest_hex = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds))
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def hash_otp(challenge_id: str, email: str, code: str) -> str:
    message = f"{challenge_id}:{email}:{code}".encode("utf-8")
    return hmac.new(AUTH_SECRET.encode(), message, hashlib.sha256).hexdigest()


def issue_session(email: str) -> str:
    payload = {"sub": email, "exp": int(time.time()) + SESSION_SECONDS, "jti": secrets.token_urlsafe(12)}
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).rstrip(b"=")
    signature = hmac.new(AUTH_SECRET.encode(), body, hashlib.sha256).digest()
    return f"{body.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def read_session(token: str) -> str | None:
    try:
        body_part, signature_part = token.split(".", 1)
        body = body_part.encode()
        signature = base64.urlsafe_b64decode(signature_part + "=" * (-len(signature_part) % 4))
        expected = hmac.new(AUTH_SECRET.encode(), body, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload_bytes = base64.urlsafe_b64decode(body_part + "=" * (-len(body_part) % 4))
        payload = json.loads(payload_bytes)
        if int(payload.get("exp", 0)) <= int(time.time()):
            return None
        return str(payload.get("sub", "")) or None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
