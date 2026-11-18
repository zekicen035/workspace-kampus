"""Perangkat tiruan ESP32/MicroPython agar main.py Wokwi bisa diuji di CPython."""
import sys, types, time, json
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---------------- jam palsu ----------------
class Clock:
    ms = 0
CLOCK = Clock()
time.sleep_ms = lambda n: setattr(CLOCK, "ms", CLOCK.ms + n)
time.sleep_us = lambda n: setattr(CLOCK, "ms", CLOCK.ms + n / 1000.0)
time.ticks_ms = lambda: int(CLOCK.ms)
time.ticks_diff = lambda a, b: a - b

# ---------------- perangkat keras tiruan ----------------
class LCD:
    def __init__(self):
        self.lines = [[" "] * 16, [" "] * 16]
        self.addr = (0, 0); self.nibs = []; self.four = False; self.prev = 0
    def write(self, b):
        if (self.prev & 4) and not (b & 4):            # EN turun = data terkunci
            self.latch(b >> 4, b & 1)
        self.prev = b
    def latch(self, nib, rs):
        if not self.four:
            if nib == 2: self.four = True
            return
        self.nibs.append(nib)
        if len(self.nibs) == 2:
            v = (self.nibs[0] << 4) | self.nibs[1]; self.nibs = []
            if rs:
                r, c = self.addr
                if c < 16: self.lines[r][c] = chr(v)
                self.addr = (r, c + 1)
            elif v == 0x01: self.lines = [[" "] * 16, [" "] * 16]; self.addr = (0, 0)
            elif v & 0x80:
                a = v & 0x7F; self.addr = (1, a - 0x40) if a >= 0x40 else (0, a)
    def text(self): return ["".join(l) for l in self.lines]

class Panel:
    def __init__(self):
        self.img = np.zeros((320, 240, 3), np.uint8)
        self.cmd = None; self.buf = bytearray(); self.x0 = self.x1 = self.y0 = self.y1 = 0
        self.pos = 0; self.left = b""; self.bytes_in = 0; self.cmds = []
    def feed(self, dc, data):
        self.bytes_in += len(data)
        if dc == 0:
            for b in data:
                self.cmd = b; self.buf = bytearray(); self.cmds.append(b)
                if b == 0x2C: self.pos = 0; self.left = b""
            return
        if self.cmd in (0x2A, 0x2B):
            self.buf += data
            if len(self.buf) >= 4:
                a = (self.buf[0] << 8) | self.buf[1]; z = (self.buf[2] << 8) | self.buf[3]
                if self.cmd == 0x2A: self.x0, self.x1 = a, z
                else: self.y0, self.y1 = a, z
        elif self.cmd == 0x2C:
            raw = self.left + bytes(data)
            n = len(raw) // 2; self.left = raw[2 * n:]
            if not n: return
            v = np.frombuffer(raw[:2 * n], dtype=">u2").astype(np.uint32)
            w = self.x1 - self.x0 + 1
            idx = self.pos + np.arange(n); self.pos += n
            y = self.y0 + idx // w; x = self.x0 + idx % w
            ok = (x < 240) & (y < 320)
            rgb = np.stack([((v >> 11) & 31) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3], 1).astype(np.uint8)
            self.img[y[ok], x[ok]] = rgb[ok]

class HW:
    pin_state = {}
    sensors = {}       # gpio ECHO -> cm
    panels = {}        # gpio CS -> Panel
    lcd = LCD()
    beeps = []
    strip_snapshots = []
    pixels = None

def reset_hw(echo_pins, cs_pins):
    HW.pin_state = {}; HW.sensors = {p: 400.0 for p in echo_pins}
    HW.panels = {p: Panel() for p in cs_pins}; HW.lcd = LCD(); HW.beeps = []
    HW.strip_snapshots = []; HW.pixels = None; CLOCK.ms = 0

# ---------------- modul machine ----------------
class Pin:
    IN, OUT = 0, 1
    def __init__(self, n, mode=None, value=None):
        self.n = n
        if value is not None: HW.pin_state[n] = value
        else: HW.pin_state.setdefault(n, 0)
    def __call__(self, v=None):
        if v is None: return HW.pin_state[self.n]
        HW.pin_state[self.n] = v
    def value(self, v=None): return self(v)
    def init(self, mode=None, value=None):
        if value is not None: HW.pin_state[self.n] = value

class SPI:
    def __init__(self, id, **kw): self.kw = kw
    def write(self, data):
        dc = HW.pin_state.get(17, 1)
        for cs, panel in HW.panels.items():
            if HW.pin_state.get(cs, 1) == 0: panel.feed(dc, data)

class I2C:
    def __init__(self, id, **kw): self.kw = kw
    def writeto(self, addr, data):
        assert addr == 0x27, "alamat LCD harus 0x27"
        for b in data: HW.lcd.write(b)

class PWM:
    def __init__(self, pin, freq=0, duty_u16=0):
        self.freq, self.duty = freq, duty_u16; HW.beeps.append((freq, duty_u16))
    def deinit(self): pass

def time_pulse_us(pin, level, timeout):
    cm = HW.sensors.get(pin.n, 400.0)
    return int(cm * 2 / 0.0343) if cm < 400 else -2

class NeoPixel:
    def __init__(self, pin, n): self.pin, self.n = pin, n; self.px = [(0, 0, 0)] * n; HW.pixels = self
    def __setitem__(self, i, c): self.px[i] = tuple(c)
    def __getitem__(self, i): return self.px[i]
    def write(self): HW.strip_snapshots.append(list(self.px))

class WLAN:
    def __init__(self, i): self.t = 0
    def active(self, v=None): pass
    def connect(self, ssid, key): self.ssid, self.key = ssid, key
    def isconnected(self): self.t += 1; return self.t > 2

class FrameBuffer:
    MONO_HLSB = 3
    _font = ImageFont.load_default()
    def __init__(self, buf, w, h, fmt): self.w, self.h = w, h; self.im = Image.new("1", (w, h), 0)
    def fill(self, c): self.im = Image.new("1", (self.w, self.h), c)
    def text(self, s, x, y, c=1):
        d = ImageDraw.Draw(self.im)
        for k, ch in enumerate(s): d.text((x + 8 * k, y - 2), ch, fill=c, font=self._font)
    def pixel(self, x, y): return 1 if self.im.getpixel((x, y)) else 0

# ---------------- server tiruan ----------------
class Server:
    def __init__(self): self.occupied = set(); self.requests = []; self.mode = "normal"
    def post(self, url, data=None, headers=None):
        body = json.loads(data); self.requests.append((url, body, dict(headers or {})))
        if self.mode == "boom": raise OSError("MBEDTLS_ERR_SSL_ALLOC_FAILED")
        if self.mode == "forbidden":
            return Resp(403, '{"error":"forbidden"}')
        code, present = body["code"], body["present"]
        st = "occupied" if code in self.occupied else ("detected" if present else "available")
        return Resp(200, json.dumps({"state": st}))
class Resp:
    def __init__(self, status, text): self.status_code, self.text = status, text
    def close(self): pass
SERVER = Server()

def install():
    m = types.ModuleType("machine")
    m.Pin, m.SPI, m.I2C, m.PWM, m.time_pulse_us = Pin, SPI, I2C, PWM, time_pulse_us
    sys.modules["machine"] = m
    n = types.ModuleType("neopixel"); n.NeoPixel = NeoPixel; sys.modules["neopixel"] = n
    w = types.ModuleType("network"); w.WLAN = WLAN; w.STA_IF = 0; sys.modules["network"] = w
    f = types.ModuleType("framebuf"); f.FrameBuffer = FrameBuffer; f.MONO_HLSB = 3; sys.modules["framebuf"] = f
    u = types.ModuleType("urequests"); u.post = SERVER.post; sys.modules["urequests"] = u
