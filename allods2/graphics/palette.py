"""Palettes: 256 RGBQUAD entries (B, G, R, 0); spec: docs/formats/palettes.md.

A palette is a (256, 3) uint8 RGB array.
"""

import numpy as np

PALETTE_BYTES = 0x400


def read_palette(buf, offset=0):
    """Parse 256 RGBQUAD entries (B, G, R, reserved) into RGB."""
    quads = np.frombuffer(buf, np.uint8, PALETTE_BYTES, offset).reshape(256, 4)
    return quads[:, 2::-1].copy()


def grayscale_palette():
    ramp = np.arange(256, dtype=np.uint8)
    return np.stack([ramp, ramp, ramp], axis=1)


def load_pal_file(path):
    """Unit .pal: the game seeks to 0x36 and reads 0x400 bytes (0x47f108)."""
    with open(path, "rb") as f:
        f.seek(0x36)
        return read_palette(f.read(PALETTE_BYTES))


def load_human_palettes(path):
    """units/humans/human.pal: 16 raw palettes of 0x400 bytes each."""
    with open(path, "rb") as f:
        data = f.read(16 * PALETTE_BYTES)
    return [read_palette(data, i * PALETTE_BYTES) for i in range(len(data) // PALETTE_BYTES)]
