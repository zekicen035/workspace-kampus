# Driver LCD 16x2 dengan backpack I2C PCF8574 (alamat 0x27), mode 4-bit.
from time import sleep_ms, sleep_us

_BL = 0x08
_EN = 0x04
_RS = 0x01


class LcdI2C:
    def __init__(self, i2c, addr=0x27, cols=16, rows=2):
        self.i2c = i2c
        self.addr = addr
        self.cols = cols
        self.rows = rows
        sleep_ms(50)
        for n, wait in ((3, 5), (3, 1), (3, 1), (2, 1)):   # masuk mode 4-bit
            self._nib(n, 0)
            sleep_ms(wait)
        self._send(0x28, 0)     # 4-bit, 2 baris, font 5x8
        self._send(0x0C, 0)     # layar nyala, kursor mati
        self._send(0x06, 0)     # kursor bergerak ke kanan
        self.clear()

    def _nib(self, nibble, rs):
        b = ((nibble & 0x0F) << 4) | _BL | rs
        self.i2c.writeto(self.addr, bytes([b | _EN]))
        sleep_us(1)
        self.i2c.writeto(self.addr, bytes([b]))
        sleep_us(50)

    def _send(self, value, rs):
        self._nib(value >> 4, rs)
        self._nib(value & 0x0F, rs)

    def clear(self):
        self._send(0x01, 0)
        sleep_ms(2)

    def move_to(self, col, row):
        self._send(0x80 | (col + (0x40 if row else 0x00)), 0)

    def putstr(self, text):
        for ch in text:
            self._send(ord(ch), _RS)

    def print_at(self, col, row, text):
        self.move_to(col, row)
        self.putstr(text)
