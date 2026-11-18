import os
from pathlib import Path

from dotenv import load_dotenv

# Lokasi folder utama proyek
BASE_DIR = Path(__file__).resolve().parent.parent

# Membaca file .env dari folder utama
load_dotenv(BASE_DIR / ".env")


def _wajib(nama: str) -> str:
    """Ambil variabel wajib dari .env. Tidak ada nilai bawaan agar
    rahasia tidak pernah tersimpan di dalam kode / GitHub."""
    nilai = os.getenv(nama, "").strip()
    if not nilai:
        raise RuntimeError(
            f"Variabel {nama} belum diisi. Salin .env.example menjadi .env "
            "lalu isi nilainya."
        )
    return nilai


# Konfigurasi server
PORT = int(os.getenv("PORT", "8000"))

# Konfigurasi Supabase
SUPABASE_URL = _wajib("SUPABASE_URL")
SUPABASE_SERVICE_KEY = _wajib("SUPABASE_SERVICE_KEY")

# Konfigurasi keamanan
JWT_SECRET = _wajib("JWT_SECRET")
ADMIN_KEY = os.getenv("ADMIN_KEY", "").strip()
DEVICE_KEY = os.getenv("DEVICE_KEY", "").strip()

# Konfigurasi WhatsApp OTP (kosong = mode demo, OTP tampil di layar & log)
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN", "").strip()

# Zona waktu (WIB = UTC+7)
TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "7"))
