"""Palettes: 256 RGBQUAD entries (B, G, R, reserved); spec: docs/formats/palettes.md.

A palette is a (256, 3) uint8 RGB array.  `Palette` adds the raw reserved
bytes (so files round-trip exactly) and I/O helpers.  `shade_table` is the
game's palette -> brightness-level table builder (FUN_00425bee); `pack16`
is its final RGB888 -> 16-bit step.
"""

import glob
import os
import struct

import numpy as np

PALETTE_BYTES = 0x400
PAL_OFFSET = 0x36           # the game seeks here in BMP-wrapped .pal files
HUMAN_PALETTES = 16
TEAM_COLOR_INDEX = 164      # 0x148 / 2, cached per player colour (FUN_0048392f)


def read_palette(buf, offset=0):
    """Parse 256 RGBQUAD entries (B, G, R, reserved) into RGB."""
    return Palette.from_bytes(buf, offset).rgb.copy()


def grayscale_palette():
    ramp = np.arange(256, dtype=np.uint8)
    return np.stack([ramp, ramp, ramp], axis=1)


class Palette:
    """256 colours plus the 4th RGBQUAD byte, which the game never reads."""

    def __init__(self, rgb, reserved=None, name=""):
        self.rgb = np.asarray(rgb, np.uint8).reshape(256, 3)
        self.reserved = (np.zeros(256, np.uint8) if reserved is None
                         else np.asarray(reserved, np.uint8).reshape(256))
        self.name = name

    @classmethod
    def from_bytes(cls, buf, offset=0, name=""):
        quads = np.frombuffer(buf, np.uint8, PALETTE_BYTES, offset).reshape(256, 4)
        return cls(quads[:, 2::-1], quads[:, 3], name)

    def to_bytes(self):
        quads = np.empty((256, 4), np.uint8)
        quads[:, 2::-1] = self.rgb
        quads[:, 3] = self.reserved
        return quads.tobytes()

    def to_rgb(self):
        """List of 256 (r, g, b) int tuples."""
        return [tuple(int(c) for c in e) for e in self.rgb]

    def swatch(self, cell=8):
        """(16*cell, 16*cell, 3) image; entry i at row i // 16, column i % 16."""
        grid = self.rgb.reshape(16, 16, 3)
        return np.repeat(np.repeat(grid, cell, 0), cell, 1)

    def to_png_swatch(self, path, cell=8):
        from .png import write_png
        write_png(path, self.swatch(cell))

    def save(self, path, kind="raw"):
        """kind "raw": the 1024 bytes alone.  kind "pal": an 8-bit 16x16 BMP
        whose pixel i is index i, with the colour table at 0x36 as the game
        expects of unit .pal files."""
        if kind == "raw":
            data = self.to_bytes()
        elif kind == "pal":
            pixels = bytes(range(256))      # 16 rows of 16, width already 4-aligned
            off = 14 + 40 + PALETTE_BYTES
            data = (struct.pack("<2sIHHI", b"BM", off + len(pixels), 0, 0, off)
                    + struct.pack("<IiiHHIIiiII", 40, 16, 16, 1, 8, 0, len(pixels),
                                  0, 0, 256, 0)
                    + self.to_bytes() + pixels)
        else:
            raise ValueError("kind must be 'raw' or 'pal'")
        with open(path, "wb") as f:
            f.write(data)

    def __eq__(self, other):
        return isinstance(other, Palette) and np.array_equal(self.rgb, other.rgb)

    def __repr__(self):
        return "Palette(%r)" % self.name


def load_pal_file(path):
    """Unit .pal: the game seeks to 0x36 and reads 0x400 bytes (0x47f108)."""
    return load_pal(path).rgb


def load_pal(path):
    with open(path, "rb") as f:
        f.seek(PAL_OFFSET)
        return Palette.from_bytes(f.read(PALETTE_BYTES), name=path)


def load_human_palettes(path):
    """units/humans/human.pal: 16 raw palettes of 0x400 bytes each."""
    return [p.rgb for p in load_human(path)]


def load_human(path):
    with open(path, "rb") as f:
        data = f.read(HUMAN_PALETTES * PALETTE_BYTES)
    return [Palette.from_bytes(data, i * PALETTE_BYTES, "%s[%d]" % (path, i))
            for i in range(len(data) // PALETTE_BYTES)]


def load_palettes(path):
    """Every palette in a file, by the rule the game uses for that file type:

    - `human.pal` (raw, a multiple of 0x400 bytes): one per 0x400 bytes
    - other `.pal`: BMP-wrapped, 0x400 bytes at 0x36
    - `.256` / `.16a` sprites with trailer bit 31: the first 0x400 bytes
    - 8-bit `.bmp`: the colour table (biClrUsed entries, 0 = 256), zero-padded
    Returns [] for files without a palette.
    """
    with open(path, "rb") as f:
        data = f.read()
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pal":
        if data[:2] != b"BM" and len(data) % PALETTE_BYTES == 0:
            return load_human(path)
        return [Palette.from_bytes(data, PAL_OFFSET, path)]
    if ext in (".256", ".16a", ".16"):
        if len(data) >= 4 and struct.unpack_from("<I", data, len(data) - 4)[0] & 0x80000000:
            return [Palette.from_bytes(data, 0, path)]
        return []
    if ext == ".bmp":
        hsize, = struct.unpack_from("<I", data, 14)
        bpp, = struct.unpack_from("<H", data, 28)
        if bpp != 8:
            return []
        used, = struct.unpack_from("<I", data, 46)
        n = used or 256
        table = data[14 + hsize:14 + hsize + 4 * n].ljust(PALETTE_BYTES, b"\0")
        return [Palette.from_bytes(table, 0, path)]
    raise ValueError("no palette rule for %s" % path)


PALETTE_EXTS = (".pal", ".256", ".16a", ".16", ".bmp")


def source_kind(path):
    """Palette source class: "human.pal", ".pal", "*b.256", or the extension."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pal":
        return "human.pal" if os.path.basename(path).lower() == "human.pal" else ".pal"
    if ext == ".256" and path.lower().endswith("b.256"):
        return "*b.256"
    return ext


def find_palettes(data_dir):
    """Yield (path relative to data_dir, source_kind, [Palette]) for every
    file under data_dir that has palettes, in sorted path order."""
    for path in sorted(glob.glob(os.path.join(data_dir, "**", "*"), recursive=True)):
        if path.lower().endswith(PALETTE_EXTS) and os.path.isfile(path):
            pals = load_palettes(path)
            if pals:
                yield os.path.relpath(path, data_dir), source_kind(path), pals


# --- shade tables (FUN_00425bee) ---------------------------------------------

MASK, PLAIN, BRIGHT2, BRIGHT32, FADE16, GRAY = range(6)


def shade_table(rgb, levels, mode, tint=(0, 0, 0)):
    """RGB888 rows the game converts to 16-bit, as an (n, 256, 3) uint8 array.

    tint is the day/night (R, G, B) bias the game passes when the 4th
    argument is 1 (FUN_0047a208); pass (0, 0, 0) for argument 0.  Row r of
    BRIGHT2 / BRIGHT32 / GRAY is level k = levels - r (row 0 brightest);
    row r of FADE16 is k = r + 1 (row 15 = full colour).
    MASK and PLAIN fill one row; FADE16 always fills 16.  The game's
    low-memory variant of FADE16 (/18 instead of /16 when physical RAM is
    under 24,000,000 bytes) is legacy and not reproduced.
    """
    c = np.asarray(rgb, np.int64).reshape(256, 3)
    t = np.asarray(tint, np.int64).reshape(1, 3)
    if mode == MASK:
        row = np.full((256, 3), 255, np.int64)
        row[0] = 0
        return row[None].astype(np.uint8)
    if mode == PLAIN:
        return np.minimum(c + t, 255)[None].astype(np.uint8)
    if mode == FADE16:
        ks = np.arange(1, 17).reshape(-1, 1, 1)
        out = c[None] * ks >> 4
    else:
        ks = np.arange(levels, 0, -1).reshape(-1, 1, 1)
        if mode == BRIGHT2:
            out = (c + t)[None] * ks * 2 // levels
        elif mode == BRIGHT32:
            out = (c + t)[None] * ks >> 5
        elif mode == GRAY:
            g = (c.sum(1)[None, :, None] * ks * 2 // 3) // levels
            out = np.broadcast_to(g & 0xFFFF, (len(ks), 256, 3))
        else:
            raise ValueError("unknown shade mode %r" % mode)
    return np.clip(out, 0, 255).astype(np.uint8)


def pack16(rgb, bits=(5, 6, 5)):
    """RGB888 -> 16-bit pixels: each channel `c >> (8 - n) << shift`,
    R highest.  The game reads widths and shifts from the surface
    (0x5fb958..0x5fb968, 0x62c9bc); (5, 6, 5) and (5, 5, 5) are typical."""
    rgb = np.asarray(rgb, np.uint16)
    rb, gb, bb = bits
    return ((rgb[..., 0] >> (8 - rb)) << (gb + bb)
            | (rgb[..., 1] >> (8 - gb)) << bb
            | (rgb[..., 2] >> (8 - bb))).astype(np.uint16)


def unpack16(px, bits=(5, 6, 5)):
    """Inverse of pack16 for display, replicating high bits into low bits."""
    px = np.asarray(px, np.uint32)
    rb, gb, bb = bits
    out = []
    for value, n in (((px >> (gb + bb)), rb), ((px >> bb), gb), (px, bb)):
        v = value & ((1 << n) - 1)
        out.append((v << (8 - n)) | (v >> (2 * n - 8) if n >= 4 else 0))
    return np.stack(out, -1).astype(np.uint8)


# --- palettes built in code (FUN_00463d30) -----------------------------------

# 256-entry gradients: entry i = (i * R // 255, i * G // 255, i * B // 255).
# The game converts each with shade_table(..., 16, FADE16).
RAMP_PALETTES = {
    "ramp_0x62a6f0": (0xb9, 0x9f, 0x49),
    "ramp_0x629848": (0xff, 0xff, 0x74),
    "ramp_0x62ab10": (0, 0, 0),
    "ramp_0x62a2c8": (0x41, 0x2f, 0x14),
    "ramp_0x629e90": (0x65, 0x27, 0x3d),
}


def ramp_palette(r, g, b):
    i = np.arange(256, dtype=np.int64)[:, None]
    return (i * np.array([r, g, b]) // 255).astype(np.uint8)


def code_palettes():
    return [Palette(ramp_palette(*c), name=n) for n, c in RAMP_PALETTES.items()]


def code_ramps16():
    """The 14 sixteen-colour 16-bit tables FUN_00463d30 writes directly,
    as {table address: (16, 3) RGB888 before pack16}."""
    i = np.arange(16, dtype=np.int64)
    j = 15 - i
    z = np.zeros(16, np.int64)
    lin = lambda m: i * m // 15
    tables = {
        0x62afb8: (z + 8, z + 8, z + 8),
        0x629c48: (i * 17, i * 17, i * 17),
        0x62aaf0: (i * 14, i * 14, i * 14),
        0x62af58: (lin(185), lin(159), lin(73)),
        0x62af38: (lin(107), lin(154), lin(120)),
        0x62afd8: (lin(255), lin(255), lin(64)),
        0x62b068: (lin(255), lin(64), lin(64)),
        0x62a6d0: (lin(64), lin(255), lin(64)),
        0x62a2a8: (lin(160), lin(120), lin(50)),
        0x62af98: (lin(139), lin(65), lin(32)),
        0x62af18: (lin(150), lin(90), z),
        0x62b028: (141 - lin(61), lin(126), lin(49)),
        0x62b008: (255 - lin(175), lin(252), lin(98)),
        0x629c68: (j * 160 // 15 + 32, j * 148 // 15 + 32, j * 88 // 15 + 32),
    }
    return {a: np.stack(t, 1).astype(np.uint8) for a, t in tables.items()}


def player_text_ramp(rgb, tint=(0, 0, 0)):
    """16-entry colour table for player colour palette `rgb` (a human.pal
    entry), as FUN_0048392f builds at 0x629c90 + p * 0x20: slot s is
    index 164 of BRIGHT2 row 15 - s // 2, i.e. the colour x (s // 2 + 1) / 8."""
    rows = shade_table(rgb, 16, BRIGHT2, tint)
    return np.stack([rows[15 - s // 2, TEAM_COLOR_INDEX] for s in range(16)])
