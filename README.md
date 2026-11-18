# Ruang Kita – Peta Workspace Kampus
FastAPI (Python) + Supabase + ESP32 (Wokwi). Frontend di `public/` tidak berubah dari versi Node.

## Jalankan lokal
```
python -m venv .venv
.venv\Scripts\activate        # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env        # lalu isi nilainya (Mac/Linux: cp)
python test_connection.py     # cek koneksi Supabase
python main.py                # atau: uvicorn main:app --reload --port 8000
```
Buka http://localhost:8000 (admin: /admin.html, dokumentasi API: /docs).

## Deploy ke Render
Build: `pip install -r requirements.txt`
Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
Isi Environment sama seperti `.env`.

## Uji logika
`python -m unittest discover -s tests -v`

## Wokwi
Ubah `SERVER_URL` ke URL Render dan `DEVICE_KEY` di sketch.ino (sama dengan `DEVICE_KEY` di .env).
