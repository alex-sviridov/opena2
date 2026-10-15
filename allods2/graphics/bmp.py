"""BMP loading.  The game reads standard bottom-up DIBs and flips the rows
after loading; spec: docs/formats/bitmaps.md."""

from dataclasses import dataclass

import numpy as np
from PIL import Image


@dataclass
class Bitmap:
    """rgb: (h, w, 3) uint8, top row first.  For 8-bit files also the raw
    indices (h, w) and the (256, 3) palette, as the "Bitmap 256" class keeps."""
    rgb: np.ndarray
    index: np.ndarray = None
    palette: np.ndarray = None

    @property
    def width(self):
        return self.rgb.shape[1]

    @property
    def height(self):
        return self.rgb.shape[0]


def load_bmp(path):
    with Image.open(path) as im:
        if im.format != "BMP":
            raise ValueError("not a BMP: %s" % path)
        if im.mode == "P":
            index = np.asarray(im)
            flat = im.getpalette() or []
            pal = np.zeros((256, 3), np.uint8)
            entries = np.asarray(flat, np.uint8).reshape(-1, 3)[:256]
            pal[:len(entries)] = entries
            return Bitmap(pal[index], index, pal)
        return Bitmap(np.asarray(im.convert("RGB")))
