import re
from datetime import datetime, timedelta, timezone

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_MS_PER_HOUR = 3_600_000
_FRAKSI = re.compile(r"\.(\d+)")

# Perangkat dianggap online bila terakhir terlihat <= 30 detik lalu
ONLINE_WINDOW_SECONDS = 30


def parse_ts(value) -> datetime | None:
    """Ubah string timestamp (format Supabase/ISO) menjadi datetime berzona waktu.
    Mengembalikan None bila kosong atau tidak valid."""
    if not value or not isinstance(value, str):
        return None

    s = value.strip().replace(" ", "T", 1)
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"

    # Pecahan detik bisa 1..n digit; seragamkan menjadi 6 digit
    s = _FRAKSI.sub(lambda m: "." + m.group(1)[:6].ljust(6, "0"), s, count=1)

    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def is_online(last_seen, now: datetime | None = None) -> bool:
    ts = parse_ts(last_seen)
    if ts is None:
        return False

    now = now or datetime.now(timezone.utc)
    return (now - ts).total_seconds() <= ONLINE_WINDOW_SECONDS


def _to_ms(dt: datetime) -> int:
    return (dt - _EPOCH) // timedelta(milliseconds=1)


def compute_busy_hours(rows, now: datetime, tz_offset_hours: int):
    """Hitung jumlah sesi yang 'menyentuh' tiap jam (0-23, waktu lokal).
    Setiap sesi dihitung maksimal sekali per jam, menelusuri paling banyak 24 jam
    dari jam mulainya. Hasilnya identik dengan versi Node.
    Mengembalikan (hours[24], now_hour)."""
    now_ms = _to_ms(now)
    offset_ms = tz_offset_hours * _MS_PER_HOUR

    def hour_of(t_ms: int) -> int:
        return ((t_ms + offset_ms) // _MS_PER_HOUR) % 24

    hours = [0] * 24

    for r in rows:
        start = parse_ts(r.get("started_at"))
        if start is None:
            continue

        end_dt = parse_ts(r.get("ended_at"))
        end = _to_ms(end_dt) if end_dt else now_ms

        t = (_to_ms(start) // _MS_PER_HOUR) * _MS_PER_HOUR
        seen = set()
        i = 0
        while i < 24 and t <= end:
            h = hour_of(t)
            if h not in seen:
                seen.add(h)
                hours[h] += 1
            i += 1
            t += _MS_PER_HOUR

    return hours, hour_of(now_ms)