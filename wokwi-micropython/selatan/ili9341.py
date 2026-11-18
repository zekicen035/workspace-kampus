# Driver layar TFT ILI9341 240x320 lewat SPI (RGB565), dengan CS per layar.
# Beberapa layar boleh berbagi SCK/MOSI/DC; yang dibedakan hanya pin CS.
import framebuf
from machine import Pin
from time import sleep_ms

WIDTH = 240
HEIGHT = 320


def color565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


BLACK = 0x0000
WHITE = 0xFFFF
RED = 0xF800

_INIT = (
    (0xEF, b"\x03\x80\x02"),
    (0xCF, b"\x00\xC1\x30"),
    (0xED, b"\x64\x03\x12\x81"),
    (0xE8, b"\x85\x00\x78"),
    (0xCB, b"\x39\x2C\x00\x34\x02"),
    (0xF7, b"\x20"),
    (0xEA, b"\x00\x00"),
    (0xC0, b"\x23"),
    (0xC1, b"\x10"),
    (0xC5, b"\x3E\x28"),
    (0xC7, b"\x86"),
    (0x36, b"\x48"),                    # rotasi 0, urutan warna BGR
    (0x37, b"\x00"),
    (0x3A, b"\x55"),                    # 16 bit per piksel
    (0xB1, b"\x00\x18"),
    (0xB6, b"\x08\x82\x27"),
    (0xF2, b"\x00"),
    (0x26, b"\x01"),
    (0xE0, b"\x0F\x31\x2B\x0C\x0E\x08\x4E\xF1\x37\x07\x10\x03\x0E\x09\x00"),
    (0xE1, b"\x00\x0E\x14\x03\x11\x07\x31\xC1\x48\x08\x0F\x0C\x31\x36\x0F"),
)


class ILI9341:
    def __init__(self, spi, cs, dc):
        self.spi = spi
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.dc = dc
        for cmd, data in _INIT:
            self._cmd(cmd, data)
        self._cmd(0x11)
        sleep_ms(120)
        self._cmd(0x29)
        sleep_ms(20)

    # ---------- level rendah ----------
    def _cmd(self, cmd, data=b""):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([cmd]))
        if data:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def _begin(self, x0, y0, x1, y1):
        self._cmd(0x2A, bytes([x0 >> 8, x0 & 255, x1 >> 8, x1 & 255]))
        self._cmd(0x2B, bytes([y0 >> 8, y0 & 255, y1 >> 8, y1 & 255]))
        self.cs(0)
        self.dc(0)
        self.spi.write(b"\x2C")
        self.dc(1)

    def _end(self):
        self.cs(1)

    # ---------- menggambar ----------
    def fill_rect(self, x, y, w, h, color):
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        w = min(w, WIDTH - x)
        h = min(h, HEIGHT - y)
        if w <= 0 or h <= 0:
            return
        px = bytes([color >> 8, color & 255])
        self._begin(x, y, x + w - 1, y + h - 1)
        total = w * h
        chunk = px * 256
        while total >= 256:
            self.spi.write(chunk)
            total -= 256
        if total:
            self.spi.write(px * total)
        self._end()

    def fill(self, color):
        self.fill_rect(0, 0, WIDTH, HEIGHT, color)

    def text(self, x, y, s, size, fg, bg):
        """Teks font 8x8 diperbesar `size` kali, dengan latar `bg`."""
        n = len(s)
        w = n * 8
        fb = framebuf.FrameBuffer(bytearray(w), w, 8, framebuf.MONO_HLSB)
        fb.fill(0)
        fb.text(s, 0, 0, 1)
        fgb = bytes([fg >> 8, fg & 255])
        bgb = bytes([bg >> 8, bg & 255])
        step = 2 * size
        line = bytearray(w * step)
        self._begin(x, y, x + w * size - 1, y + 8 * size - 1)
        for r in range(8):
            o = 0
            for px in range(w):
                line[o:o + step] = (fgb if fb.pixel(px, r) else bgb) * size
                o += step
            for _ in range(size):
                self.spi.write(line)
        self._end()

    def text_center(self, s, y, size, fg, bg):
        # perkecil otomatis bila teks tidak muat selebar layar
        while size > 1 and len(s) * 8 * size > WIDTH:
            size -= 1
        x = max(0, (WIDTH - len(s) * 8 * size) // 2)
        self.text(x, y, s, size, fg, bg)

    def draw_matrix(self, x0, y0, m, scale, quiet, dark, light):
        """Gambar matriks QR (list of list bool) dengan zona tenang `quiet` piksel."""
        n = len(m)
        box = n * scale + 2 * quiet
        db = bytes([dark >> 8, dark & 255])
        lb = bytes([light >> 8, light & 255])
        blank = lb * box
        self._begin(x0, y0, x0 + box - 1, y0 + box - 1)
        for _ in range(quiet):
            self.spi.write(blank)
        for row in m:
            line = bytearray(blank)
            o = 2 * quiet
            for v in row:
                if v:
                    line[o:o + 2 * scale] = db * scale
                o += 2 * scale
            for _ in range(scale):
                self.spi.write(line)
        for _ in range(quiet):
            self.spi.write(blank)
        self._end()
