# Node ESP32 Wokwi – versi MicroPython

Pengganti `wokwi-layout/*/sketch.ino` (Arduino C++). Perilakunya sama:
tiap meja punya sensor jarak, lampu NeoPixel, dan layar TFT berisi QR kode meja;
data dikirim ke `POST /api/iot/telemetry` di backend Python.

```
utara/    6 meja  (WS-U01..U06)      selatan/  7 meja  (WS-S01..S07)
  main.py       program utama
  config.py     pin, zona, SERVER_URL, DEVICE_KEY   <- yang perlu kamu ubah
  diagram.json  rangkaian (sama dengan versi Arduino)
  qr.py  ili9341.py  lcd_i2c.py   library kecil buatan sendiri (tidak perlu install)
```

## Cara pakai di wokwi.com (ulangi untuk tiap zona)
1. Buka https://wokwi.com, **New Project**, pilih **ESP32** lalu template **MicroPython**.
2. Buka tab `diagram.json`, hapus isinya, tempel isi `diagram.json` dari folder zona.
3. Buat file baru (tombol panah di samping tab file) dan salin isi: `main.py`,
   `config.py`, `qr.py`, `ili9341.py`, `lcd_i2c.py`. Nama harus persis sama.
4. Di `config.py` ubah:
   - `SERVER_URL`  -> alamat backend (mis. `https://nama-app.onrender.com/api/iot/telemetry`)
   - `DEVICE_KEY`  -> sama dengan `DEVICE_KEY` di `.env` server
5. Tekan tombol Play. Di terminal Wokwi akan tampil satu baris per meja:
   `WS-U01 | 400.0 cm | HTTP 200 | {"state":"available"}`
6. Geser nilai jarak sensor HC-SR04: di bawah 80 cm = ada orang (kuning), lalu check-in
   lewat web = merah. Kuning lebih dari 10 detik = buzzer berbunyi.

Server lokal (`http://localhost:8000`) tidak bisa dijangkau dari Wokwi; pakai alamat Render
atau tunnel (mis. ngrok).

## Kalau ada masalah
- `gagal kirim: ... ALLOC_FAILED` / `ENOMEM`: memori ESP32 habis saat membuka koneksi HTTPS.
  Program tidak berhenti dan mencoba lagi di putaran berikutnya.
- `HTTP 403`: `DEVICE_KEY` tidak sama dengan di server.
- Render gratis tidur saat tidak dipakai, request pertama bisa lambat.
