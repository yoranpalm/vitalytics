"""Genereer PWA-iconen (dumbbell op merkblauw) — pure stdlib, geen Pillow."""
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "static", "icons")
os.makedirs(OUT, exist_ok=True)

BG = (58, 95, 200)     # merkblauw #3A5FC8
FG = (255, 255, 255)


def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def _png(size, rows):
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b""))


def _in_rounded(px, py, s, r):
    cx = min(max(px, r), s - r)
    cy = min(max(py, r), s - r)
    return (px - cx) ** 2 + (py - cy) ** 2 <= r * r


def _dumbbell(px, py, s, inset):
    """Horizontale halter met twee gewichtsplaten, gecentreerd in de inhoudsbox."""
    m = s * inset
    span = s - 2 * m
    u = (px - m) / span - 0.5
    v = (py - m) / span - 0.5
    bar_h, plate_w, plate_h, plate_x = 0.11, 0.10, 0.62, 0.34
    if abs(u) <= plate_x + plate_w / 2 and abs(v) <= bar_h / 2:
        return True
    return abs(abs(u) - plate_x) <= plate_w / 2 and abs(v) <= plate_h / 2


def _render(size, rounded, inset):
    ss = 2  # 2x2 supersampling voor gladde randen
    rows = []
    r = size * 0.225 if rounded else 0
    for y in range(size):
        row = bytearray()
        for x in range(size):
            cr = cg = cb = ca = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    px = x + (sx + 0.5) / ss
                    py = y + (sy + 0.5) / ss
                    if (not rounded) or _in_rounded(px, py, size, r):
                        c = FG if _dumbbell(px, py, size, inset) else BG
                        cr += c[0]; cg += c[1]; cb += c[2]; ca += 255
            if ca > 0:
                row += bytes((round(cr / ca), round(cg / ca), round(cb / ca),
                              round(ca / (ss * ss))))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(row)
    return rows


def make(name, size, rounded, inset):
    path = os.path.join(OUT, name)
    with open(path, "wb") as fh:
        fh.write(_png(size, _render(size, rounded, inset)))
    print(f"{name}: {os.path.getsize(path)} bytes")


make("icon-192.png", 192, True, 0.14)
make("icon-512.png", 512, True, 0.14)
make("icon-maskable-512.png", 512, False, 0.20)
make("apple-touch-icon.png", 180, False, 0.16)

# favicon.ico: 32x32-PNG verpakt in een ICO-container (begrijpt elke browser)
ico_png = _png(32, _render(32, True, 0.14))
header = struct.pack("<HHH", 0, 1, 1)
entry = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(ico_png), 22)
with open(os.path.join(OUT, "favicon.ico"), "wb") as fh:
    fh.write(header + entry + ico_png)
print(f"favicon.ico: {os.path.getsize(os.path.join(OUT, 'favicon.ico'))} bytes")