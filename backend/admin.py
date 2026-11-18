import hmac
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

from backend.config import ADMIN_KEY, FONNTE_TOKEN
from backend.database import get_supabase, first
from backend.deps import require_admin
from backend.security import (
    create_admin_token,
    hash_otp,
    password_ok,
    hash_password,
    clear_failed_login,
)
from backend.utils import is_online

router = APIRouter()


def error(status: int, message: str):
    return JSONResponse(status_code=status, content={"error": message})


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def kirim_wa(phone: str, message: str):
    """Notifikasi WhatsApp best-effort: gagal tidak menggagalkan proses."""
    if not FONNTE_TOKEN or not phone:
        return

    try:
        httpx.post(
            "https://api.fonnte.com/send",
            headers={"Authorization": FONNTE_TOKEN},
            data={"target": phone, "message": message},
            timeout=15,
        )
    except Exception as err:
        print("[WA]", err)


# ---------- LOGIN ----------
@router.post("/api/admin/login")
def admin_login(body: dict = Body(...)):
    key = str(body.get("key") or "")

    if not ADMIN_KEY or not hmac.compare_digest(hash_otp(key), hash_otp(ADMIN_KEY)):
        return error(401, "Kunci admin salah")

    return {"token": create_admin_token()}


# ---------- PANTAUAN & RIWAYAT ----------
@router.get("/api/admin/data", dependencies=[Depends(require_admin)])
def admin_data():
    db = get_supabase()

    workspaces = db.table("workspaces").select("*").order("code").execute().data or []

    active = (
        db.table("sessions")
        .select("workspace_id,started_at,users(name,nim,phone,role)")
        .is_("ended_at", "null")
        .execute()
        .data
        or []
    )

    history = (
        db.table("sessions")
        .select("started_at,ended_at,workspaces(code,name),users(name,nim,phone,role)")
        .order("started_at", desc=True)
        .limit(500)
        .execute()
        .data
        or []
    )

    by_ws = {str(s["workspace_id"]): s for s in active}

    return {
        "workspaces": [
            {
                "code": w.get("code"),
                "name": w.get("name"),
                "zone": w.get("zone"),
                "distance": w.get("distance_cm"),
                "present": w.get("sensor_present"),
                "online": is_online(w.get("last_seen")),
                "session": by_ws.get(str(w["id"])),
            }
            for w in workspaces
        ],
        "history": history,
    }


@router.post("/api/admin/checkout", dependencies=[Depends(require_admin)])
def admin_checkout(body: dict = Body(...)):
    db = get_supabase()

    code = str(body.get("code") or "").strip().upper()
    workspace = first(db.table("workspaces").select("id").eq("code", code))

    if workspace:
        db.table("sessions").update({"ended_at": now_iso()}).eq(
            "workspace_id", workspace["id"]
        ).is_("ended_at", "null").execute()

    return {"ok": True}


# ---------- KELOLA MEJA ----------
@router.post("/api/admin/workspaces", dependencies=[Depends(require_admin)])
def add_workspace(body: dict = Body(...)):
    code = str(body.get("code") or "").strip().upper()
    name = str(body.get("name") or "").strip()
    zone = str(body.get("zone") or "").strip()

    if not code or not name or not zone:
        return error(400, "Kode, nama, dan zona wajib diisi")

    try:
        get_supabase().table("workspaces").insert(
            {"code": code, "name": name, "zone": zone}
        ).execute()
    except APIError as err:
        if getattr(err, "code", None) == "23505" or "duplicate" in str(err).lower():
            return error(409, "Kode meja sudah dipakai")
        raise

    return {"ok": True}


@router.delete("/api/admin/workspaces/{code}", dependencies=[Depends(require_admin)])
def delete_workspace(code: str):
    db = get_supabase()

    workspace = first(db.table("workspaces").select("id").eq("code", code))

    if workspace:
        if first(db.table("sessions").select("id").eq("workspace_id", workspace["id"])):
            return error(409, "Meja ini punya riwayat sesi, tidak bisa dihapus")

        db.table("workspaces").delete().eq("id", workspace["id"]).execute()

    return {"ok": True}


# ---------- SANDI MAHASISWA ----------
@router.post("/api/admin/students/{nim:path}/password", dependencies=[Depends(require_admin)])
def reset_student_password(nim: str, body: dict = Body(...)):
    db = get_supabase()

    password = str(body.get("password") or "")

    if not password_ok(password):
        return error(400, "Sandi minimal 8 karakter")

    if not first(db.table("students").select("nim").eq("nim", nim)):
        return error(404, "NIM tidak ditemukan di daftar mahasiswa")

    db.table("students").update(
        {"password_hash": hash_password(password)}
    ).eq("nim", nim).execute()

    clear_failed_login(nim)

    return {"ok": True}


# ---------- PENDAFTARAN ----------
@router.get("/api/admin/registrations", dependencies=[Depends(require_admin)])
def get_registrations():
    rows = (
        get_supabase()
        .table("registrations")
        .select("nim,name,major,phone,status,created_at,decided_at")
        .order("created_at", desc=True)
        .limit(200)
        .execute()
        .data
        or []
    )

    # Yang masih pending tampil paling atas; urutan terbaru dipertahankan
    rows.sort(key=lambda r: r.get("status") != "pending")

    return rows


@router.post(
    "/api/admin/registrations/{nim:path}/{act}", dependencies=[Depends(require_admin)]
)
def manage_registration(nim: str, act: str):
    if act not in ("approve", "reject"):
        return error(400, "Aksi tidak valid")

    db = get_supabase()

    reg = first(db.table("registrations").select("*").eq("nim", nim))

    if not reg:
        return error(404, "Pendaftaran tidak ditemukan")

    if act == "approve":
        student = {
            "nim": reg["nim"],
            "name": reg["name"],
            "major": reg["major"],
            "phone": reg["phone"],
        }

        # Jangan menimpa sandi lama dengan kosong
        if reg.get("password_hash"):
            student["password_hash"] = reg["password_hash"]

        db.table("students").upsert(student, on_conflict="nim").execute()

    db.table("registrations").update({
        "status": "approved" if act == "approve" else "rejected",
        "decided_at": now_iso(),
        "password_hash": None,
    }).eq("nim", nim).execute()

    kirim_wa(
        reg.get("phone"),
        f"Pendaftaran NIM {reg['nim']} di Ruang Kita disetujui. Silakan login dengan NIM kamu."
        if act == "approve"
        else f"Pendaftaran NIM {reg['nim']} di Ruang Kita ditolak. Hubungi admin untuk info lebih lanjut.",
    )

    return {"ok": True}
