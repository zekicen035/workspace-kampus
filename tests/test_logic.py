"""Uji logika murni (tanpa jaringan). Jalankan: python -m unittest -v"""
import json
import os
import random
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils import parse_ts, is_online, compute_busy_hours  # noqa: E402

JS = r"""
const rows=JSON.parse(process.argv[1]),NOW=+process.argv[2],TZ=7;
const hourOf=t=>new Date(t+TZ*36e5).getUTCHours();
const hours=Array(24).fill(0);
rows.forEach(r=>{const end=r.ended_at?new Date(r.ended_at).getTime():NOW,seen=new Set();
 for(let i=0,t=Math.floor(new Date(r.started_at).getTime()/36e5)*36e5;i<24&&t<=end;i++,t+=36e5){const h=hourOf(t);if(!seen.has(h)){seen.add(h);hours[h]++}}});
console.log(JSON.stringify({hours,nowHour:hourOf(NOW)}));
"""


class FakeResult:
    def __init__(self, data):
        self.data = data


class FakeQuery:
    def __init__(self, rows):
        self.rows, self.n = rows, None

    def limit(self, n):
        self.n = n
        return self

    def execute(self):
        return FakeResult(self.rows[: self.n])


class Tests(unittest.TestCase):
    def test_parse_ts_variasi_pecahan_detik(self):
        for v in ["2026-11-17T06:00:00Z", "2026-11-17T06:00:00.12345+00:00",
                  "2026-11-17 06:00:00.1+00:00", "2026-11-17T06:00:00.123456+00:00"]:
            self.assertIsNotNone(parse_ts(v), v)
        self.assertIsNone(parse_ts(None))
        self.assertIsNone(parse_ts("bukan tanggal"))

    def test_online_30_detik(self):
        now = datetime(2026, 11, 17, 6, 0, 0, tzinfo=timezone.utc)
        self.assertTrue(is_online((now - timedelta(seconds=10)).isoformat(), now))
        self.assertFalse(is_online((now - timedelta(seconds=45)).isoformat(), now))
        self.assertFalse(is_online(None, now))

    def test_first_aman_saat_kosong(self):
        try:
            from backend.database import first
        except ModuleNotFoundError:
            self.skipTest("paket supabase belum terpasang")
        self.assertIsNone(first(FakeQuery([])))
        self.assertEqual(first(FakeQuery([{"a": 1}, {"a": 2}])), {"a": 1})

    def test_statistik_sama_dengan_versi_node(self):
        random.seed(7)
        now = datetime(2026, 11, 17, 9, 30, tzinfo=timezone.utc)
        rows = []
        for _ in range(300):
            s = now - timedelta(minutes=random.randint(1, 60 * 24 * 7))
            e = None if random.random() < 0.1 else s + timedelta(minutes=random.randint(1, 60 * 30))
            rows.append({"started_at": s.isoformat(),
                         "ended_at": e.isoformat() if e else None})
        out = subprocess.run(
            ["node", "-e", JS, json.dumps(rows), str(int(now.timestamp() * 1000))],
            capture_output=True, text=True, check=True).stdout
        ref = json.loads(out)
        hours, now_hour = compute_busy_hours(rows, now, 7)
        self.assertEqual(hours, ref["hours"])
        self.assertEqual(now_hour, ref["nowHour"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
