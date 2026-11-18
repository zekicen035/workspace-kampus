
import hashlib
import hmac
import secrets
import time
import jwt

from datetime import datetime, timedelta, timezone

from backend.config import JWT_SECRET


# ==============================
# PASSWORD SCRYPT
# ==============================

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)

    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=16384,
        r=8,
        p=1,
        dklen=64
    )

    return f"scrypt${salt.hex()}${key.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False

    try:
        algorithm, salt_hex, hash_hex = stored_hash.split("$")

        if algorithm != "scrypt":
            return False

        salt = bytes.fromhex(salt_hex)
        original_key = bytes.fromhex(hash_hex)

        key = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=16384,
            r=8,
            p=1,
            dklen=64
        )

        return (
            len(original_key) == len(key)
            and hmac.compare_digest(key, original_key)
        )

    except (ValueError, TypeError):
        return False


def password_ok(password: str) -> bool:
    return isinstance(password, str) and 8 <= len(password) <= 72


# ==============================
# OTP HASH
# ==============================

def hash_otp(code: str) -> str:
    return hashlib.sha256(
        (code + JWT_SECRET).encode("utf-8")
    ).hexdigest()


# ==============================
# NOMOR WHATSAPP
# ==============================

def phone_norm(phone: str) -> str:
    phone = "".join(
        char for char in str(phone or "")
        if char.isdigit()
    )

    if phone.startswith("0"):
        phone = "62" + phone[1:]

    return phone


# ==============================
# PEMBATAS PERCOBAAN LOGIN
# ==============================

fails = {}


def is_locked(nim: str) -> bool:
    data = fails.get(nim)

    return bool(
        data
        and data["count"] >= 5
        and time.time() - data["time"] < 900
    )


def record_failed_login(nim: str):
    data = fails.get(nim)

    if data and time.time() - data["time"] < 900:
        fails[nim] = {
            "count": data["count"] + 1,
            "time": data["time"]
        }
    else:
        fails[nim] = {
            "count": 1,
            "time": time.time()
        }


def clear_failed_login(nim: str):
    fails.pop(nim, None)


# ==============================
# JWT TOKEN
# ==============================

def create_user_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "id": user_id,
        "iat": now,
        "exp": now + timedelta(hours=12)
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm="HS256"
    )


def create_admin_token() -> str:
    now = datetime.now(timezone.utc)

    payload = {
        "admin": True,
        "iat": now,
        "exp": now + timedelta(hours=8)
    }

    return jwt.encode(
        payload,
        JWT_SECRET,
        algorithm="HS256"
    )


def decode_token(token: str):
    try:
        return jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"]
        )
    except jwt.InvalidTokenError:
        return None
