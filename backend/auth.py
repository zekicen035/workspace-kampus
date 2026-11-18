import re
import secrets
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from backend.config import FONNTE_TOKEN
from backend.database import get_supabase, first
from backend.deps import require_user
from backend.security import (
    verify_password,
    create_user_token,
    is_locked,
    record_failed_login,
    clear_failed_login,
    hash_otp,
    phone_norm,
)

router = APIRouter()


def error(status: int, message: str, **extra):
    return JSONResponse(status_code=status, content={"error": message, **extra})


# ---------- LOGIN NIM + SANDI ----------
@router.post("/api/auth/nim")
def login_nim(body: dict = Body(...)):
    db = get_supabase()

    nim = str(body.get("nim") or "").strip()
    password = str(body.get("password") or "")

    student = first(db.table("students").select("*").eq("nim", nim))

    # Jika NIM belum jadi mahasiswa, periksa status pendaftarannya
    if not student:
        rg = first(db.table("registrations").select("status").eq("nim", nim))
        status = rg.get("status") if rg else None

        if status == "pending":
            message = "Pendaftaran kamu masih menunggu persetujuan admin."
        elif status == "rejected":
            message = "Pendaftaran ditolak. Hubungi admin atau daftar ulang."
        else:
            message = "NIM belum terdaftar. Silakan daftar dulu."

        return error(404, message, canRegister=(not rg or status == "rejected"))

    if is_locked(nim):
        return error(429, "Terlalu banyak percobaan. Coba lagi 15 menit lagi.")

    if not student.get("password_hash"):
        return error(
            403, "Akun ini belum punya sandi. Hubungi admin untuk mengatur sandi."
        )

    if not verify_password(password, student["password_hash"]):
        record_failed_login(nim)
        return error(401, "NIM atau sandi salah")

    clear_failed_login(nim)

    # Buat akun pengguna jika belum ada
    user = first(db.table("users").select("*").eq("nim", nim))

    if not user:
        user = db.table("users").insert(
            {"nim": nim, "name": student["name"], "role": "student"}
        ).execute().data[0]

    return {"token": create_user_token(str(user["id"])), "user": user}


# ---------- OTP WHATSAPP (tamu) ----------
@router.post("/api/auth/otp/request")
def request_otp(body: dict = Body(...)):
    db = get_supabase()

    phone = phone_norm(body.get("phone"))

    if not re.fullmatch(r"62\d{8,13}", phone):
        return error(400, "Nomor WhatsApp tidak valid")

    now = datetime.now(timezone.utc)

    # Maksimal satu OTP per 60 detik
    recent = first(
        db.table("otp_codes")
        .select("id")
        .eq("phone", phone)
        .gt("created_at", (now - timedelta(seconds=60)).isoformat())
    )

    if recent:
        return error(429, "Tunggu 60 detik sebelum meminta OTP lagi")

    code = str(secrets.randbelow(900000) + 100000)

    db.table("otp_codes").insert({
        "phone": phone,
        "code_hash": hash_otp(code),
        "expires_at": (now + timedelta(minutes=5)).isoformat(),
    }).execute()

    message = (
        f"Kode OTP Workspace Kampus: {code}. "
        "Berlaku 5 menit. Jangan bagikan ke siapa pun."
    )

    if FONNTE_TOKEN:
        response = httpx.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": FONNTE_TOKEN},
            data={"target": phone, "message": message},
            timeout=30,
        )

        try:
            result = response.json()
        except ValueError:
            result = {}

        if not response.is_success or result.get("status") is False:
            reason = result.get("reason") or response.status_code
            print("[FONNTE]", reason)
            return error(
                502,
                "Gagal mengirim WhatsApp: "
                + str(result.get("reason") or "periksa perangkat Fonnte"),
            )

        return {"ok": True}

    # Mode demo: tanpa FONNTE_TOKEN, kode ditampilkan di layar & log
    print("[DEV OTP]", phone, code)
    return {"ok": True, "devCode": code}


@router.post("/api/auth/otp/verify")
def verify_otp(body: dict = Body(...)):
    db = get_supabase()

    phone = phone_norm(body.get("phone"))
    code = str(body.get("code") or "")
    name = str(body.get("name") or "").strip() or "Tamu"

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

    user = first(db.table("users").select("*").eq("phone", phone))

    if not user:
        user = db.table("users").insert(
            {"phone": phone, "name": name, "role": "guest"}
        ).execute().data[0]

    return {"token": create_user_token(str(user["id"])), "user": user}


# ---------- PROFIL ----------
@router.get("/api/me")
def get_me(user: dict = Depends(require_user)):
    db = get_supabase()

    session = first(
        db.table("sessions")
        .select("started_at,workspaces(code,name,zone)")
        .eq("user_id", user["id"])
        .is_("ended_at", "null")
    )

    major = None

    if user.get("nim"):
        student = first(
            db.table("students").select("major").eq("nim", user["nim"])
        )
        major = student.get("major") if student else None

    return {"user": {**user, "major": major}, "session": session}
