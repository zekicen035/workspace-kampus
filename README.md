# Ruang Kita – Peta Workspace Kampus
Express + Supabase + ESP32 (Wokwi). Struktur: `server.js`, `public/index.html`, `schema.sql`, `wokwi/`.

## 1. Supabase
1. Buat project, buka **SQL Editor**, jalankan isi `schema.sql` (membuat tabel + data contoh NIM 2021001–2021003 dan 10 meja).
2. **Project Settings > API**: salin `Project URL` dan `service_role` key.

## 2. Jalankan lokal
`cp .env.example .env` (isi nilainya) → `npm install` → `npm start` → buka http://localhost:3000

## 3. Deploy ke Render
- Push ke GitHub → Render **New > Web Service** → Build: `npm install`, Start: `npm start`.
- Environment: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `JWT_SECRET`, `DEVICE_KEY`, `FONNTE_TOKEN`.

## 4. OTP WhatsApp
Daftar di fonnte.com, hubungkan nomor WA, salin token ke `FONNTE_TOKEN`. Tanpa token, server berjalan mode demo (OTP tampil di layar & log).

## 5. Wokwi
Buat project ESP32 baru, salin `sketch.ino`, `diagram.json`, `libraries.txt`. Ubah `SERVER_URL` ke URL Render dan `DEVICE_KEY`. Geser nilai jarak HC-SR04: di bawah 80 cm = ada orang → web menampilkan "Ada orang"; check-in via QR → "Dipakai". Render free tier tidur saat idle, request pertama bisa lambat.

## 6. Halaman admin
Buka `/admin.html`, masuk dengan nilai env `ADMIN_KEY` (tambahkan juga di Render). Isinya: pantauan real-time + paksa check-out, riwayat 100 sesi terakhir, tambah/hapus meja, dan cetak QR semua meja (tombol Cetak → simpan sebagai PDF).
