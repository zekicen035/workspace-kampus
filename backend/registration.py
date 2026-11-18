import re
from datetime import datetime, timezone

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from backend.database import get_supabase, first
from backend.security import phone_norm, password_ok, hash_password, hash_otp

router = APIRouter()


def error(status: int, message: str):
    return JSONResponse(status_code=status, content={"error": message})


@router.post("/api/register/verify")
def verify_registration(body: dict = Body(...)):
    db = get_supabase()

    nim = str(body.get("nim") or "").strip()
    name = str(body.get("name") or "").strip()
    major = str(body.get("major") or "").strip()[:80]
    phone = phone_norm(body.get("phone"))
    password = str(body.get("password") or "")
    code = str(body.get("code") or "")

    if not re.fullmatch(r"[A-Za-z0-9./-]{5,25}", nim) or len(name) < 3 or len(major) < 2:
        return error(400, "Isi nama, NIM, dan program studi dengan benar")

    if not password_ok(password):
        return error(400, "Sandi minimal 8 karakter")

    if not re.fullmatch(r"62\d{8,13}", phone):
        return error(400, "Nomor WhatsApp tidak valid")

    if first(db.table("students").select("nim").eq("nim", nim)):
        return error(409, "NIM ini sudah terdaftar, silakan langsung login.")

    rg = first(db.table("registrations").select("status").eq("nim", nim))

    if rg and rg.get("status") == "pending":
        return error(409, "Pendaftaran NIM ini sudah menunggu persetujuan admin.")

    # Periksa OTP
    otp = first(
        db.table("otp_codes")
        .select("*")
        .eq("phone", phone)
        .eq("used", False)
        .gt("expires_at", datetime.now(timezone.utc).isoformat())
        .order("created_at", desc=True)
    )

    if not otp or otp.get("code_hash") != hash_otp(code):
        return error(400, "OTP salah atau sudah kedaluwarsa")

    db.table("otp_codes").update({"used": True}).eq("id", otp["id"]).execute()

    # Simpan pendaftaran untuk persetujuan admin (daftar ulang setelah
    # ditolak juga masuk sini: waktu dibuat diperbarui, keputusan direset)
    db.table("registrations").upsert(
        {
            "nim": nim,
            "name": name,
            "major": major,
            "phone": phone,
            "password_hash": hash_password(password),
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "decided_at": None,
        },
        on_conflict="nim",
    ).execute()

    return {
        "ok": True,
        "message": "Pendaftaran terkirim. Tunggu persetujuan admin, lalu login dengan NIM.",
    }
