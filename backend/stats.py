from datetime import datetime, timedelta, timezone

from fastapi import APIRouter

from backend.config import TZ_OFFSET_HOURS
from backend.database import get_supabase
from backend.utils import compute_busy_hours

router = APIRouter()


# Statistik publik (agregat, tanpa data pribadi).
# Bentuk respons HARUS {days, hours[24], nowHour} karena dipakai
# grafik keramaian di public/index.html.
@router.get("/api/stats/busy")
def get_busy_stats(days: str | None = None):
    try:
        n = int(days)
    except (TypeError, ValueError):
        n = 7

    n = min(30, max(1, n or 7))

    now = datetime.now(timezone.utc)

    rows = (
        get_supabase()
        .table("sessions")
        .select("started_at,ended_at")
        .gte("started_at", (now - timedelta(days=n)).isoformat())
        .limit(2000)
        .execute()
        .data
        or []
    )

    hours, now_hour = compute_busy_hours(rows, now, TZ_OFFSET_HOURS)

    return {"days": n, "hours": hours, "nowHour": now_hour}
