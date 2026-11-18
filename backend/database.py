from supabase import create_client, Client

from backend.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

supabase: Client | None = None


def connect_supabase() -> Client:
    global supabase

    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return supabase


def get_supabase() -> Client:
    if supabase is None:
        raise RuntimeError("Koneksi Supabase belum dibuat.")

    return supabase


def first(query):
    """Jalankan query dan kembalikan baris pertama, atau None bila kosong.

    Pengganti `.maybe_single().execute().data`. Pada banyak versi
    supabase-py, maybe_single().execute() mengembalikan None (bukan objek
    response) ketika tidak ada baris, sehingga `.data` memicu error 500.
    Memakai limit(1) berlaku sama di semua versi.
    """
    result = query.limit(1).execute()
    data = getattr(result, "data", None) or []
    return data[0] if data else None
