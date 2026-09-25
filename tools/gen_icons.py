"""Genereer PWA-iconen: het Vitalytics-logo (V-chevron op primary-container).

Zelfde vorm en kleuren als het inline SVG-logo in templates/base.html
(viewBox 0 0 34 34: --primary-container als vlak, --on-primary-container
voor de V; donker-themakleuren, zodat het icoon in beide modi hetzelfde
(donkerblauwe) logo toont — zie verzoek gebruiker). Pure stdlib, geen Pillow.

Na een kleur- of vormwijziging dit script opnieuw draaien:
python tools/gen_icons.py — de bestanden in static/icons/ worden overschreven.
"""
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "static", "icons")
os.makedirs(OUT, exist_ok=True)

BG = (11, 74, 143)     # --primary-container: #0b4a8f (donker thema)
FG = (217, 226, 255)   # --on-primary-container: #d9e2ff

# Logo-geometrie uit templates/base.html (viewBox 0 0 34 34)
RECT = 34.0
ROND = 9.0        # rx van het afgeronde vierkant
STREEP = 3.4      # stroke-width van de V
V_PUNTEN = ((9.5, 9.5), (17.0, 24.5), (24.5, 9.5))


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


def _seg_dist(px, py, x1, y1, x2, y2):
    """Afstand van punt tot lijnstuk; round caps/joins vallen hieruit mee:
    elk punt binnen de halve streepdikte van het V-pad krijgt de voorgrond."""
    vx, vy = x2 - x1, y2 - y1
    wx, wy = px - x1, py - y1
    l2 = vx * vx + vy * vy
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / l2))
    dx, dy = wx - t * vx, wy - t * vy
    return (dx * dx + dy * dy) ** 0.5


def _render(size, rounded, frac):
    """Teken het logo op size x size pixels. rounded=True geeft afgeronde
    hoeken met transparant eromheen; False een vol vierkant (maskable en
    apple-touch krijgen van het besturingssysteem hun eigen masker).
    frac: schaal van de inhoud — kleiner bij maskable vanwege de safe zone."""
    ss = 2  # 2x2 supersampling voor gladde randen
    k = size / RECT * frac
    ox = (size - RECT * k) / 2
    r_hoek = ROND * k if rounded else 0
    half = STREEP / 2 * k
    (ax, ay), (bx, by), (cx, cy) = [(ox + x * k, ox + y * k) for x, y in V_PUNTEN]
    rows = []
    for y in range(size):
        row = bytearray()
        for x in range(size):
            cr = cg = cb = 0
            m = 0  # aantal binnenliggende steekproeven (dekking)
            for sy in range(ss):
                for sx in range(ss):
                    px = x + (sx + 0.5) / ss
                    py = y + (sy + 0.5) / ss
                    if (not rounded) or _in_rounded(px, py, size, r_hoek):
                        m += 1
                        if (_seg_dist(px, py, ax, ay, bx, by) <= half
                                or _seg_dist(px, py, bx, by, cx, cy) <= half):
                            c = FG
                        else:
                            c = BG
                        cr += c[0]; cg += c[1]; cb += c[2]
            if m > 0:
                # Kleur = gemiddelde van de binnenliggende steekproeven;
                # alpha = dekkingsfractie. Delen door de opgetelde alpha (255
                # per steekproef) maakt alles zwart — die bug stond eerder in
                # dit script en leverde de zwarte favicon op.
                row += bytes((round(cr / m), round(cg / m), round(cb / m),
                              round(255 * m / (ss * ss))))
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(row)
    return rows


def make(name, size, rounded, frac):
    path = os.path.join(OUT, name)
    with open(path, "wb") as fh:
        fh.write(_png(size, _render(size, rounded, frac)))
    print(f"{name}: {os.path.getsize(path)} bytes")


make("icon-192.png", 192, True, 1.0)
make("icon-512.png", 512, True, 1.0)
make("icon-maskable-512.png", 512, False, 0.72)
make("apple-touch-icon.png", 180, False, 0.72)

# favicon.ico: 32x32-PNG verpakt in een ICO-container (begrijpt elke browser)
ico_png = _png(32, _render(32, True, 1.0))
header = struct.pack("<HHH", 0, 1, 1)
entry = struct.pack("<BBBBHHII", 32, 32, 0, 0, 1, 32, len(ico_png), 22)
with open(os.path.join(OUT, "favicon.ico"), "wb") as fh:
    fh.write(header + entry + ico_png)
print(f"favicon.ico: {os.path.getsize(os.path.join(OUT, 'favicon.ico'))} bytes")