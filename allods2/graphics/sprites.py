"""Sprite containers and RLE decoders (.256, b.256, .16, .16a).

Spec: docs/formats/sprites.md.  Decoders follow the cursor model described
there; the game routine each one corresponds to is noted per function.
"""

import struct
from dataclasses import dataclass

import numpy as np

from ..common import read
from .palette import PALETTE_BYTES, grayscale_palette, read_palette

PALETTE_FLAG = 0x80000000

KINDS = ("256", "smooth", "16", "16a")


@dataclass
class Sprite:
    width: int
    height: int
    data: bytes

    def __repr__(self):
        return "Sprite(%dx%d, %d bytes)" % (self.width, self.height, len(self.data))


@dataclass
class Decoded:
    """A decoded sprite.

    index  (h, w) uint8  palette index (.256/.16a) or colour slot 0..15 (.16)
    mask   (h, w) bool   pixel is drawn
    alpha  (h, w) uint8  .16a alpha level 0..15, else None
    consumed             bytes of the stream the walk used
    rows_left            rows not closed by the column counter (0 = last row
                         closed normally, >0 = ended on a row skip / EOF)
    """
    index: np.ndarray
    mask: np.ndarray
    alpha: np.ndarray = None
    consumed: int = 0
    rows_left: int = 0


class SpriteFile:
    """Container shared by .256 / b.256 / .16a / .16 (loader 0x424559)."""

    def __init__(self, sprites, palette=None, kind="256"):
        if kind not in KINDS:
            raise ValueError("unknown sprite kind %r" % kind)
        self.sprites = sprites
        self.palette = palette
        self.kind = kind

    @classmethod
    def load(cls, path, fs=None, kind=None):
        """path in `fs` (a2res FS; None = OS path).  Sprite data are views
        of the file (no copy)."""
        return cls.parse(read(path, fs), kind or guess_kind(path))

    @classmethod
    def parse(cls, data, kind="256"):
        if len(data) < 4:
            raise ValueError("file too short")
        trailer = struct.unpack_from("<I", data, len(data) - 4)[0]
        count = trailer & ~PALETTE_FLAG
        pos = 0
        palette = None
        if trailer & PALETTE_FLAG:
            if len(data) < PALETTE_BYTES + 4:
                raise ValueError("palette past end of file")
            palette = read_palette(data)
            pos = PALETTE_BYTES
        end = len(data) - 4
        sprites = []
        for i in range(count):
            if pos + 12 > end:
                raise ValueError("sprite %d header past end of file" % i)
            w, h, size = struct.unpack_from("<III", data, pos)
            pos += 12
            if pos + size > end:
                raise ValueError("sprite %d data past end of file" % i)
            sprites.append(Sprite(w, h, data[pos:pos + size]))
            pos += size
        return cls(sprites, palette, kind)

    def __len__(self):
        return len(self.sprites)

    def __getitem__(self, i):
        return self.sprites[i]

    def decode(self, i):
        return decode(self.sprites[i], self.kind)

    def to_rgba(self, i, palette=None):
        """(h, w, 4) uint8 image of sprite i; palette defaults to the embedded one."""
        pal = palette if palette is not None else self.palette
        if pal is None:
            pal = grayscale_palette()
        return to_rgba(self.decode(i), self.kind, pal)


def guess_kind(path):
    name = path.replace("\\", "/").rpartition("/")[2].lower()
    if name.endswith(".16a"):
        return "16a"
    if name.endswith(".16"):
        return "16"
    if name.endswith("b.256"):
        return "smooth"
    return "256"


# --------------------------------------------------------------------------
# RLE walks.  Cursor model (sprites.md "Shared cursor model"): linear pointer
# p into a width-w image, column counter c checked after every op (reset to 0
# and one row consumed once c >= w, overshoot stays in p), row skips move p
# without touching c and end the sprite when n >= rows left.
# --------------------------------------------------------------------------

def _store(flat, p, values):
    """flat[p:p+len(values)] = values, clipped to the image like a no-op
    outside it (the game's clipped blitters skip such pixels)."""
    n = len(values)
    lo, hi = max(p, 0), min(p + n, len(flat))
    if lo < hi:
        flat[lo:hi] = values[lo - p:hi - p]


def _image(index, mask, w, h):
    """bytearray buffers -> (h, w) uint8 index and bool mask arrays."""
    return (np.frombuffer(index, np.uint8).reshape(h, w).copy(),
            np.frombuffer(mask, np.uint8).reshape(h, w).astype(bool))


def _walk_bytes(data, w, h, literal):
    """Byte-control walk shared by .256 and .16.  literal(data, i, n, p)
    writes a run and returns (new_i, pixels_advanced, counter_advance)."""
    rows, p, c, i, n_data = h, 0, 0, 0, len(data)
    while rows > 0 and i < n_data:
        b = data[i]
        i += 1
        n = b & 0x3F
        tag = b & 0xC0
        if tag == 0x00:
            i, adv, cadv = literal(i, n, p)
            p += adv
            c += cadv
        elif tag == 0x40:
            if rows <= n:
                break
            rows -= n
            p += n * w
            continue
        else:
            p += n
            c += n
        if c >= w:
            c = 0
            rows -= 1
    return i, rows


def decode_256(data, w, h):
    """.256 (blitter 0x454344): 00nnnnnn literal indices, 01nnnnnn skip rows,
    1xnnnnnn skip transparent pixels."""
    index = bytearray(w * h)
    mask = bytearray(w * h)

    def literal(i, n, p):
        run = bytes(data[i:i + n]).ljust(n, b"\0")      # truncated stream: pad with zeros
        _store(index, p, run)
        _store(mask, p, b"\1" * n)
        return i + n, n, n

    used, rows = _walk_bytes(data, w, h, literal) if w and h else (0, h)
    return Decoded(*_image(index, mask, w, h), None, used, rows)


def decode_smooth(data, w, h):
    """*b.256 edge-smoothing overlay: same stream as .256.  Drawn with the 50 %
    translucent blitter (0x454656) over the main sprite when the "Smoothing"
    option is on (hero draw 0x4632a1)."""
    return decode_256(data, w, h)


def decode_16(data, w, h):
    """.16 (0x4540d1): control bytes as .256; a literal run of n bytes holds
    up to 2n nibble pixels, low nibble first.  A zero high nibble ends the
    run: the counter advances 2n-1 and the rest of the run is re-read as
    control bytes."""
    index = bytearray(w * h)
    mask = bytearray(w * h)

    def literal(i, n, p):
        px = bytearray()
        counter = 2 * n
        for b in data[i:i + n]:
            i += 1
            px.append(b & 0x0F)
            if not b >> 4:                     # run ends after this low nibble
                counter -= 1
                break
            px.append(b >> 4)
        _store(index, p, px)
        _store(mask, p, b"\1" * len(px))
        return i, len(px), counter

    used, rows = _walk_bytes(data, w, h, literal) if w and h else (0, h)
    return Decoded(*_image(index, mask, w, h), None, used, rows)


def decode_16a(data, w, h):
    """.16a (0x45889b): 16-bit words.  v & 0x4000 skip rows (tested first),
    v & 0x8000 skip pixels, else v literal pixel words.  Pixel word: bits
    9..12 alpha level, bits 1..8 palette index."""
    index = np.zeros(w * h, np.uint8)
    alpha = np.zeros(w * h, np.uint8)
    mask = np.zeros(w * h, bool)
    words = np.frombuffer(data, "<u2", len(data) // 2)
    rows, p, c, i, count = h, 0, 0, 0, len(words)
    while w and rows > 0 and i < count:
        v = int(words[i])
        i += 1
        if v & 0x4000:
            n = v & 0x3FFF
            if rows <= n:
                break
            rows -= n
            p += n * w
            continue
        if v & 0x8000:
            n = v & 0x3FFF
        else:
            n = v
            run = words[i:i + n]
            i += len(run)
            _store(index, p, ((run >> 1) & 0xFF).astype(np.uint8))
            _store(alpha, p, ((run >> 9) & 0x0F).astype(np.uint8))
            _store(mask, p, np.ones(len(run), bool))
        p += n
        c += n
        if c >= w:
            c = 0
            rows -= 1
    return Decoded(index.reshape(h, w), mask.reshape(h, w), alpha.reshape(h, w),
                   i * 2, rows)


DECODERS = {"256": decode_256, "smooth": decode_smooth, "16": decode_16, "16a": decode_16a}


def decode(sprite, kind):
    return DECODERS[kind](sprite.data, sprite.width, sprite.height)


def check_sprite(sprite, kind):
    """(bytes_consumed, data_size, rows_left).  Consistent streams consume
    exactly their data."""
    d = decode(sprite, kind)
    return d.consumed, len(sprite.data), d.rows_left


def alpha_coverage(level):
    """Opacity of a .16a alpha level, 0..255: the game blends (a+1)/16."""
    return np.minimum((np.asarray(level, np.uint16) + 1) * 16, 255).astype(np.uint8)


SMOOTH_ALPHA = 0x80


def to_rgba(decoded, kind, palette):
    """(h, w, 4) uint8 RGBA for a decoded sprite.  Smoothing overlays get
    alpha 128, matching the game's 50 % blend."""
    h, w = decoded.mask.shape
    out = np.zeros((h, w, 4), np.uint8)
    m = decoded.mask
    out[..., :3][m] = np.asarray(palette, np.uint8)[decoded.index[m]]
    if kind == "16a":
        out[..., 3][m] = alpha_coverage(decoded.alpha[m])
    else:
        out[..., 3][m] = SMOOTH_ALPHA if kind == "smooth" else 255
    return out
