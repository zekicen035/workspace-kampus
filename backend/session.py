from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse
from postgrest.exceptions import APIError

from backend.database import get_supabase, first
from backend.deps import require_user

router = APIRouter()


@router.post("/api/checkin")
def checkin(body: dict = Body(...), user: dict = Depends(require_user)):
    db = get_supabase()

    code = str(body.get("code") or "").strip().upper()

    workspace = first(db.table("workspaces").select("id,code").eq("code", code))

    if not workspace:
        return JSONResponse(status_code=404, content={"error": "QR tidak dikenali"})

    try:
        db.table("sessions").insert(
            {"workspace_id": workspace["id"], "user_id": user["id"]}
        ).execute()

    except APIError as err:
        text = str(err)

        if "one_active_per_user" in text:
            message = "Kamu masih punya sesi aktif. Check-out dulu."
        elif getattr(err, "code", None) == "23505" or "duplicate" in text.lower():
            message = "Workspace ini sedang dipakai"
        else:
            raise  # error lain (bukan bentrok sesi) -> jadi 500, bukan salah label

        return JSONResponse(status_code=409, content={"error": message})

    return {"ok": True, "workspace": workspace["code"]}


@router.post("/api/checkout")
def checkout(user: dict = Depends(require_user)):
    get_supabase().table("sessions").update(
        {"ended_at": datetime.now(timezone.utc).isoformat()}
    ).eq("user_id", user["id"]).is_("ended_at", "null").execute()

    return {"ok": True}
