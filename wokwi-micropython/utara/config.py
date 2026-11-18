# Konfigurasi node zona Utara (6 meja). Pin sesuai diagram.json.
ZONA = "Utara"
SERVER_URL = "https://workspace-kampus.onrender.com/api/iot/telemetry"
DEVICE_KEY = "ISI_DEVICE_KEY_KAMU"      # samakan dengan DEVICE_KEY di server

# Isi QR = QR_BASE + kode meja. Server /api/checkin membaca kode meja saja.
QR_BASE = ""

CODE = ("WS-U01", "WS-U02", "WS-U03", "WS-U04", "WS-U05", "WS-U06")
ECHO = (34, 35, 36, 39, 32, 33)         # pin ECHO tiap sensor
TFT_CS = (25, 26, 27, 14, 12, 15)       # pin CS tiap layar
PIX = (0, 5, 2, 3, 1, 4)                # urutan lampu pada rantai NeoPixel

N = len(CODE)
TRIG_PIN = 5          # satu pin TRIG dipakai bersama semua sensor
TFT_DC = 17           # SCK=18, MOSI=23 (SPI), RST layar disambung ke 3V3
BUZZER = 13
PIXPIN = 4
THRESHOLD_CM = 80     # jarak < 80 cm = ada orang
GRACE_MS = 10000      # waktu untuk scan QR sebelum alarm
QR_MAX_VERSION = 6
QR_AREA = 170         # lebar maksimum area modul QR (piksel)
QR_QUIET = 16         # area putih di sekeliling QR (piksel)
