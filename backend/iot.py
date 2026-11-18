import hmac
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Header
from fastapi.responses import JSONResponse

from backend.config import DEVICE_KEY
from backend.database import get_supabase, first

router = APIRouter()


@router.post("/api/iot/telemetry")
def receive_telemetry(
    body: dict = Body(...),
    x_device_key: str | None = Header(default=None),
):
    # Validasi kunci perangkat ESP32
    if not DEVICE_KEY or not hmac.compare_digest(
        (x_device_key or "").encode(), DEVICE_KEY.encode()
    ):
        return JSONResponse(status_code=403, content={"error": "forbidden"})

    db = get_supabase()

    code = str(body.get("code") or "").strip().upper()
    present = bool(body.get("present", False))
    distance = body.get("distance")

    updated = (
        db.table("workspaces")
        .update({
            "sensor_present": present,
            "distance_cm": distance,
            "last_seen": datetime.now(timezone.utc).isoformat(),
        })
        .eq("code", code)
        .execute()
        .data
    )

    if not updated:
        return JSONResponse(
            status_code=404, content={"error": "workspace tidak ditemukan"}
        )

    active = first(
        db.table("sessions")
        .select("id")
        .eq("workspace_id", updated[0]["id"])
        .is_("ended_at", "null")
    )

    state = "occupied" if active else ("detected" if present else "available")

    return {"state": state}
