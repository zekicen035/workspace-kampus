from backend.database import connect_supabase

try:
    db = connect_supabase()
    db.table("workspaces").select("*").limit(1).execute()
    print("KONEKSI SUPABASE BERHASIL!")
except Exception as error:
    print("KONEKSI SUPABASE GAGAL!")
    print(error)
