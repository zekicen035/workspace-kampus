from fastapi import APIRouter

from backend.database import get_supabase
from backend.utils import is_online

router = APIRouter()


@router.get("/api/workspaces")
def get_workspaces():
    db = get_supabase()

    workspaces = (
        db.table("workspaces").select("*").order("code").execute().data or []
    )

    sessions = (
        db.table("sessions")
        .select("workspace_id,started_at")
        .is_("ended_at", "null")
        .execute()
        .data
        or []
    )

    active = {str(s["workspace_id"]): s for s in sessions}

    output = []

    for w in workspaces:
        session = active.get(str(w["id"]))
        online = is_online(w.get("last_seen"))

        if session:
            state = "occupied"
        elif online and w.get("sensor_present"):
            state = "detected"
        else:
            state = "available"

        output.append({
            "code": w.get("code"),
            "name": w.get("name"),
            "zone": w.get("zone"),
            "map_x": w.get("map_x"),
            "map_y": w.get("map_y"),
            "map_w": w.get("map_w"),
            "map_h": w.get("map_h"),
            "online": online,
            "distance": w.get("distance_cm"),
            "since": session.get("started_at") if session else None,
            "state": state,
        })

    return output
