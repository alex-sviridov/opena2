"""Check every fontN.dat against its glyph sprites.

    python tools/validate_fonts.py [DATA_DIR]

Byte accounting: the .dat is exactly 4 bytes per glyph of the matching
.16/.16a file, and every glyph stream decodes exactly (pass/fail). Metric
rule, reported for information: a value is the glyph's last ink column
(0 for a blank glyph); exceptions are listed.
"""

import glob
import os
import sys

from allods2 import graphics as gfx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_sprites import DEFAULT_DATA  # noqa: E402


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    data_dir = argv[0] if argv else DEFAULT_DATA
    bad = 0
    dats = sorted(glob.glob(os.path.join(data_dir, "graphics", "font*", "font*.dat")))
    for dat in dats:
        font = gfx.Font.load(dat[:-4])
        size = os.path.getsize(dat)
        n = len(font.sprites)
        streams = sum(gfx.check_sprite(s, font.sprites.kind)[0] == len(s.data)
                      for s in font.sprites.sprites)
        ink = gfx.last_ink_columns(font.sprites)
        rule = sum(a == b for a, b in zip(font.widths, ink))
        cells = sorted({(s.width, s.height) for s in font.sprites.sprites})
        ok = size == 4 * n and streams == n
        bad += not ok
        print("%-10s %-4s %3d glyphs, cell %s, chars 0x20-0x%02X, dat %4d B, "
              "streams %d/%d, width = last ink column %d/%d  %s"
              % (os.path.basename(dat), font.sprites.kind, n, cells, 0x1F + n,
                 size, streams, n, rule, n, "OK" if ok else "FAIL"))
        for g, (a, b) in enumerate(zip(font.widths, ink)):
            if a != b:
                print("    char 0x%02X: dat %d, last ink column %d" % (0x20 + g, a, b))
    if not dats:
        print("no fontN.dat under", data_dir)
        return 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
