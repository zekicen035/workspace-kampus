# Generator QR code ringkas untuk MicroPython.
# Mode byte, koreksi error level L, versi 1-6 (cukup untuk kode meja pendek).
# Pemakaian:  m = matrix("WS-U01")   ->  m[y][x] bernilai True jika modul gelap.

# versi: (total codeword, codeword EC per blok, jumlah blok)
_SPEC = {
    1: (26, 7, 1),
    2: (44, 10, 1),
    3: (70, 15, 1),
    4: (100, 20, 1),
    5: (134, 26, 1),
    6: (172, 18, 2),
}

_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _rs_remainder(data, deg):
    gen = [1]
    for i in range(deg):
        ng = [0] * (len(gen) + 1)
        for j in range(len(gen)):
            ng[j] ^= gen[j]
            ng[j + 1] ^= _mul(gen[j], _EXP[i])
        gen = ng
    rem = [0] * deg
    for b in data:
        factor = b ^ rem.pop(0)
        rem.append(0)
        for i in range(deg):
            rem[i] ^= _mul(gen[i + 1], factor)
    return rem


def _data_capacity(version):
    total, ec, blocks = _SPEC[version]
    return total - ec * blocks


def _codewords(data, version):
    cap = _data_capacity(version)
    bits = []

    def put(value, n):
        for k in range(n - 1, -1, -1):
            bits.append((value >> k) & 1)

    put(0b0100, 4)          # mode byte
    put(len(data), 8)       # jumlah karakter (versi 1-9 = 8 bit)
    for b in data:
        put(b, 8)
    put(0, min(4, cap * 8 - len(bits)))   # terminator
    while len(bits) % 8:
        bits.append(0)
    out = [int("".join(str(v) for v in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(out) < cap:
        out.append(pad)
        pad = 0x11 if pad == 0xEC else 0xEC
    return out


def _interleave(data, version):
    total, ec, nblocks = _SPEC[version]
    per = len(data) // nblocks
    blocks = [data[i * per:(i + 1) * per] for i in range(nblocks)]
    ecs = [_rs_remainder(b, ec) for b in blocks]
    out = []
    for i in range(per):
        for b in blocks:
            out.append(b[i])
    for i in range(ec):
        for e in ecs:
            out.append(e[i])
    return out


def _mask_fn(m):
    if m == 0:
        return lambda x, y: (x + y) % 2 == 0
    if m == 1:
        return lambda x, y: y % 2 == 0
    if m == 2:
        return lambda x, y: x % 3 == 0
    if m == 3:
        return lambda x, y: (x + y) % 3 == 0
    if m == 4:
        return lambda x, y: (x // 3 + y // 2) % 2 == 0
    if m == 5:
        return lambda x, y: (x * y) % 2 + (x * y) % 3 == 0
    if m == 6:
        return lambda x, y: ((x * y) % 2 + (x * y) % 3) % 2 == 0
    return lambda x, y: ((x + y) % 2 + (x * y) % 3) % 2 == 0


def _build(version, codewords, mask):
    size = 17 + 4 * version
    mod = [[False] * size for _ in range(size)]
    fun = [[False] * size for _ in range(size)]

    def setf(x, y, dark):
        mod[y][x] = dark
        fun[y][x] = True

    for i in range(size):                       # pola timing
        setf(6, i, i % 2 == 0)
        setf(i, 6, i % 2 == 0)

    for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):   # pola finder
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < size and 0 <= y < size:
                    d = max(abs(dx), abs(dy))
                    setf(x, y, d != 2 and d != 4)

    if version >= 2:                            # pola alignment (1 buah)
        c = 4 * version + 10
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                setf(c + dx, c + dy, max(abs(dx), abs(dy)) != 1)

    # informasi format (ECC L = 01)
    data = (1 << 3) | mask
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = ((data << 10) | rem) ^ 0x5412

    def bit(i):
        return ((bits >> i) & 1) != 0

    for i in range(0, 6):
        setf(8, i, bit(i))
    setf(8, 7, bit(6))
    setf(8, 8, bit(7))
    setf(7, 8, bit(8))
    for i in range(9, 15):
        setf(14 - i, 8, bit(i))
    for i in range(0, 8):
        setf(size - 1 - i, 8, bit(i))
    for i in range(8, 15):
        setf(8, size - 15 + i, bit(i))
    setf(8, size - 8, True)                     # modul gelap tetap

    # tempatkan data (zig-zag)
    stream = []
    for cw in codewords:
        for k in range(7, -1, -1):
            stream.append(((cw >> k) & 1) != 0)
    n_rem = {1: 0}.get(version, 7)
    stream += [False] * n_rem

    fn = _mask_fn(mask)
    i = 0
    right = size - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(size):
            for j in range(2):
                x = right - j
                upward = ((right + 1) & 2) == 0
                y = (size - 1 - vert) if upward else vert
                if not fun[y][x] and i < len(stream):
                    mod[y][x] = stream[i] ^ fn(x, y)
                    i += 1
        right -= 2
    return mod


def _penalty(m):
    size = len(m)
    p = 0
    rows = ["".join("1" if v else "0" for v in r) for r in m]
    cols = ["".join("1" if m[y][x] else "0" for y in range(size)) for x in range(size)]
    for line in rows + cols:
        run = 1
        for k in range(1, size):
            if line[k] == line[k - 1]:
                run += 1
            else:
                if run >= 5:
                    p += 3 + run - 5
                run = 1
        if run >= 5:
            p += 3 + run - 5
        p += 40 * (line.count("10111010000") + line.count("00001011101"))
    for y in range(size - 1):
        for x in range(size - 1):
            v = m[y][x]
            if v == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                p += 3
    dark = sum(1 for r in m for v in r if v)
    total = size * size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    return p + 10 * k


def matrix(text, max_version=6, mask=None):
    """Kembalikan matriks QR (list of list bool). ValueError jika teks terlalu panjang."""
    if isinstance(text, str):
        data = text.encode()
    else:
        data = bytes(text)
    for version in range(1, min(max_version, 6) + 1):
        if len(data) <= _data_capacity(version) - 2:
            break
    else:
        raise ValueError("teks terlalu panjang untuk QR versi %d" % max_version)

    cws = _interleave(_codewords(data, version), version)

    if mask is not None:
        return _build(version, cws, mask)

    best = None
    best_score = None
    for m in range(8):
        cand = _build(version, cws, m)
        score = _penalty(cand)
        if best is None or score < best_score:
            best, best_score = cand, score
    return best
