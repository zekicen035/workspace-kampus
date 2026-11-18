from fastapi import Header, HTTPException

from backend.database import get_supabase, first
from backend.security import decode_token


def _ambil_payload(authorization: str | None, pesan_login: str) -> dict:
    """Ambil & verifikasi token JWT dari header 'Authorization: Bearer <token>'."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail=pesan_login)

    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)

    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid atau kedaluwarsa",
        )

    return payload


def require_user(authorization: str | None = Header(default=None)):
    payload = _ambil_payload(authorization, "Login diperlukan")

    if not payload.get("id"):
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid atau kedaluwarsa",
        )

    db = get_supabase()

    user = first(
        db.table("users")
        .select("*")
        .eq("id", payload["id"])
    )

    if not user:
        raise HTTPException(status_code=401, detail="Pengguna tidak ditemukan")

    return user


def require_admin(authorization: str | None = Header(default=None)):
    """Token admin dibuat oleh create_admin_token() (payload {"admin": True})."""
    payload = _ambil_payload(authorization, "Login admin diperlukan")

    if payload.get("admin") is not True:
        raise HTTPException(status_code=401, detail="Akses admin ditolak")

    return payload