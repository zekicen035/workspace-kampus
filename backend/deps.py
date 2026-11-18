
from fastapi import Header, HTTPException

from backend.database import get_supabase, first
from backend.security import decode_token


def require_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Login diperlukan"
        )

    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)

    if not payload or not payload.get("id"):
        raise HTTPException(
            status_code=401,
            detail="Token tidak valid atau kedaluwarsa"
        )

    db = get_supabase()

    user = first(
        db.table("users")
        .select("*")
        .eq("id", payload["id"])
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Pengguna tidak ditemukan"
        )

    return user
