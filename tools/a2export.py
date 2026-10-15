"""Export Allods 2 graphics to PNG.

    python tools/a2export.py SPRITEFILE OUT.png [--palette PAL] [--index N] [--cols C]
    python tools/a2export.py FILE.bmp OUT.png

Without --index, every sprite is laid out on a grid. --palette takes a unit
.pal (BMP colour table) to override the embedded palette. Write outputs to
out/ (gitignored) or outside the repo, never into samples/.
"""

import argparse
import math

import numpy as np

from allods2 import graphics as gfx


def sheet(sf, palette=None, max_cols=16, pad=1):
    n = len(sf)
    if not n:
        raise SystemExit("no sprites")
    cw = max(s.width for s in sf.sprites) + pad
    ch = max(s.height for s in sf.sprites) + pad
    cols = min(max_cols, n)
    rows = math.ceil(n / cols)
    out = np.zeros((rows * ch, cols * cw, 4), np.uint8)
    for i in range(n):
        img = sf.to_rgba(i, palette)
        oy, ox = (i // cols) * ch, (i % cols) * cw
        out[oy:oy + img.shape[0], ox:ox + img.shape[1]] = img
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Export Allods 2 graphics to PNG.")
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--palette")
    ap.add_argument("--index", type=int)
    ap.add_argument("--cols", type=int, default=16)
    a = ap.parse_args(argv)

    if a.src.lower().endswith(".bmp"):
        img = gfx.load_bmp(a.src).rgb
        desc = "bitmap"
    else:
        sf = gfx.SpriteFile.load(a.src)
        pal = gfx.load_pal_file(a.palette) if a.palette else None
        img = sf.to_rgba(a.index, pal) if a.index is not None else sheet(sf, pal, a.cols)
        desc = "%d sprites, %s palette" % (len(sf), "embedded" if sf.palette is not None else "no")
    gfx.write_png(a.out, img)
    print("%s: %s -> %s (%dx%d)" % (a.src, desc, a.out, img.shape[1], img.shape[0]))


if __name__ == "__main__":
    main()
