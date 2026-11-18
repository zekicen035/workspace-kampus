# Node zona Wokwi (MicroPython): 1 ESP32 memantau beberapa meja.
# Port dari sketch.ino. Lampu per meja (NeoPixel) dan layar TFT per meja:
#   hijau = tersedia, merah = dipakai (sudah scan QR),
#   kuning = ada orang tapi belum scan. Kuning > GRACE_MS -> buzzer berbunyi.
import gc
import json
from time import sleep_ms, sleep_us, ticks_diff, ticks_ms

import neopixel
import network
from machine import I2C, PWM, SPI, Pin, time_pulse_us

try:
    import urequests as requests
except ImportError:
    import requests

import config as C
from ili9341 import ILI9341, BLACK, WHITE, RED, color565
from lcd_i2c import LcdI2C
from qr import matrix as qr_matrix

ST_AVAILABLE, ST_OCCUPIED, ST_DETECTED, ST_ERROR, ST_WAIT = range(5)

HEADER_BG = color565(25, 40, 90)
STATUS_STYLE = {
    ST_AVAILABLE: ("TERSEDIA", color565(0, 140, 60), WHITE),
    ST_OCCUPIED: ("DIPAKAI", color565(190, 25, 40), WHITE),
    ST_DETECTED: ("SCAN QR!", color565(235, 170, 0), BLACK),
    ST_WAIT: ("MENUNGGU", color565(90, 90, 90), WHITE),
    ST_ERROR: ("OFFLINE", color565(90, 90, 90), WHITE),
}


def pad(text, width=16):
    return text + " " * (width - len(text)) if len(text) < width else text[:width]


class Node:
    def __init__(self):
        self.trig = Pin(C.TRIG_PIN, Pin.OUT, value=0)
        self.echo = [Pin(p, Pin.IN) for p in C.ECHO]
        self.buzzer_pin = Pin(C.BUZZER, Pin.OUT, value=0)
        self.strip = neopixel.NeoPixel(Pin(C.PIXPIN, Pin.OUT), C.N)
        self.since = [None] * C.N
        self.shown = [None] * C.N

        self.lcd = LcdI2C(I2C(0, scl=Pin(22), sda=Pin(21), freq=100000))
        self.lcd.print_at(0, 0, pad("Zona " + C.ZONA))
        self.lcd.print_at(0, 1, pad("Gambar QR..."))

        spi = SPI(2, baudrate=20000000, polarity=0, phase=0,
                  sck=Pin(18), mosi=Pin(23), miso=Pin(19))
        dc = Pin(C.TFT_DC, Pin.OUT, value=1)
        for cs in C.TFT_CS:                       # semua layar nonaktif dulu
            Pin(cs, Pin.OUT, value=1)
        self.tft = [ILI9341(spi, cs, dc) for cs in C.TFT_CS]
        for i in range(C.N):
            self.draw_table(i)
            self.show_status(i, ST_WAIT)

    # ---------- layar per meja ----------
    def draw_table(self, i):
        d = self.tft[i]
        d.fill(BLACK)
        d.fill_rect(0, 0, 240, 36, HEADER_BG)
        d.text_center("MEJA " + C.CODE[i][3:], 8, 3, WHITE, HEADER_BG)
        try:
            m = qr_matrix(C.QR_BASE + C.CODE[i], C.QR_MAX_VERSION)
            size = len(m)
            sc = max(1, C.QR_AREA // size)
            box = size * sc + 2 * C.QR_QUIET
            d.draw_matrix((240 - box) // 2, 42, m, sc, C.QR_QUIET, BLACK, WHITE)
        except ValueError:
            d.text_center("QR terlalu panjang", 120, 2, RED, BLACK)
        d.text_center(C.CODE[i] + " " + C.ZONA, 246, 2, WHITE, BLACK)
        self.shown[i] = None

    def show_status(self, i, st):
        if self.shown[i] == st:              # gambar ulang hanya jika berubah
            return
        self.shown[i] = st
        txt, bg, fg = STATUS_STYLE[st]
        d = self.tft[i]
        d.fill_rect(0, 268, 240, 52, bg)
        d.text_center(txt, 282, 3, fg, bg)

    # ---------- sensor, lampu, buzzer ----------
    def read_cm(self, i):
        self.trig(0)
        sleep_us(2)
        self.trig(1)
        sleep_us(10)
        self.trig(0)
        d = time_pulse_us(self.echo[i], 1, 30000)
        return d * 0.0343 / 2 if d > 0 else 400.0

    def lamp(self, i, r, g, b):
        # kecerahan 80/255 seperti setBrightness(80) di versi Arduino
        self.strip[C.PIX[i]] = ((r * 81) >> 8, (g * 81) >> 8, (b * 81) >> 8)

    def beep(self, ms):
        pwm = PWM(self.buzzer_pin, freq=1000, duty_u16=32768)
        sleep_ms(ms)
        pwm.deinit()
        self.buzzer_pin.init(Pin.OUT, value=0)

    # ---------- server ----------
    def post(self, i, cm):
        body = json.dumps({
            "code": C.CODE[i],
            "present": cm < C.THRESHOLD_CM,
            "distance": round(cm, 1),
        })
        status, res = -1, ""
        try:
            gc.collect()
            r = requests.post(
                C.SERVER_URL,
                data=body,
                headers={"Content-Type": "application/json",
                         "x-device-key": C.DEVICE_KEY},
            )
            status, res = r.status_code, r.text
            r.close()
        except Exception as e:                # jaringan putus, memori TLS, dll.
            print(C.CODE[i], "| gagal kirim:", e)
            return "error"
        print(C.CODE[i], "|", round(cm, 1), "cm | HTTP", status, "|", res)
        for name in ("occupied", "detected", "available"):
            if '"%s"' % name in res:
                return name
        return "error"

    # ---------- satu putaran ----------
    def step(self):
        kosong, alarm, who = 0, False, ""
        for i in range(C.N):
            st = self.post(i, self.read_cm(i))
            if st == "detected":
                if self.since[i] is None:
                    self.since[i] = ticks_ms()
                self.lamp(i, 200, 140, 0)
                self.show_status(i, ST_DETECTED)
                if ticks_diff(ticks_ms(), self.since[i]) > C.GRACE_MS:
                    alarm, who = True, C.CODE[i][3:]
            else:
                self.since[i] = None
                if st == "occupied":
                    self.lamp(i, 200, 20, 30)
                    self.show_status(i, ST_OCCUPIED)
                elif st == "available":
                    self.lamp(i, 0, 120, 40)
                    self.show_status(i, ST_AVAILABLE)
                    kosong += 1
                else:
                    self.lamp(i, 0, 0, 0)
                    self.show_status(i, ST_ERROR)
        self.strip.write()
        self.lcd.print_at(0, 0, pad("%s %d/%d kosong" % (C.ZONA[:3], kosong, C.N)))
        self.lcd.print_at(0, 1, pad(("SCAN QR: " + who) if alarm else "Semua aman"))
        if alarm:
            for _ in range(3):
                self.beep(150)
                sleep_ms(100)
        sleep_ms(1000)


def connect_wifi(lcd, timeout_s=30):
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    percobaan = 0
    while not sta.isconnected():
        percobaan += 1
        lcd.print_at(0, 1, pad("Konek WiFi #%d" % percobaan))
        print("Konek WiFi, percobaan", percobaan)
        try:
            sta.disconnect()
        except Exception:
            pass
        sta.connect("Wokwi-GUEST", "")
        t0 = ticks_ms()
        while not sta.isconnected() and ticks_diff(ticks_ms(), t0) < timeout_s * 1000:
            sleep_ms(300)
            print(".", end="")
        print("\nstatus:", sta.status())
    print("WiFi OK", sta.ifconfig())

def run(max_loops=None):
    node = Node()
    connect_wifi(node.lcd)
    n = 0
    while max_loops is None or n < max_loops:
        node.step()
        n += 1


if __name__ == "__main__":
    run()