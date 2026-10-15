"""Write out/contact/tiles_<set>.png: each terrain set as an indexed grid.

    python tools/tile_contact.py [INSTALL_DIR] [-o out/contact] [--scale 2]

Columns are the 4 strips, rows the tiles inside a strip. Each tile is
labelled with the u16 a map's Tiles block stores for it (set << 6 |
strip << 4 | row; add 0x2000 for the dirt overlay), so the sheets can be
read against .alm dumps. Spec: docs/formats/terrain.md.
Output contains game data: out/ only.
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

from allods2.graphics import terrain as tr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_terrain import DEFAULT  # noqa: E402

PAD = 4
HEAD = 16


def sheet(terrain, s, scale, font):
    n = max(terrain.rows(s, j) for j in range(tr.STRIPS))
    t = tr.TILE * scale
    w = PAD + tr.STRIPS * (t + PAD)
    h = HEAD + PAD + n * (t + PAD)
    im = Image.new("RGB", (w, h), (40, 40, 40))
    draw = ImageDraw.Draw(im)
    title = "set %d" % s + (" (water, frame %d)" % (s - 8) if s in tr.WATER else "")
    draw.text((PAD, 2), title + ": " + " .. ".join(tr.strip_name(s, j) for j in (0, 3)),
              fill=(230, 230, 230), font=font)
    for j in range(tr.STRIPS):
        for r in range(terrain.rows(s, j)):
            x, y = PAD + j * (t + PAD), HEAD + PAD + r * (t + PAD)
            tile = Image.fromarray(terrain.tile_rgba(s, j, r)[..., :3])
            im.paste(tile.resize((t, t), Image.NEAREST), (x, y))
            label = "%04x" % tr.cell_value(s, j, r)
            draw.text((x + 2, y + 1), label, fill=(0, 0, 0), font=font)
            draw.text((x + 1, y), label, fill=(255, 255, 0), font=font)
    return im


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base", nargs="?", default=DEFAULT)
    ap.add_argument("-o", "--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "contact"))
    ap.add_argument("--scale", type=int, default=2)
    a = ap.parse_args(argv)
    terrain = tr.TerrainSet.load(os.path.join(a.base, "data", "graphics", "terrain"))
    font = ImageFont.load_default(10)
    os.makedirs(a.out, exist_ok=True)
    for s in range(tr.SETS):
        path = os.path.join(a.out, "tiles_%d.png" % s)
        im = sheet(terrain, s, a.scale, font)
        im.save(path)
        print("set %2d: %d strips x %d tiles -> %s"
              % (s, tr.STRIPS, max(terrain.rows(s, j) for j in range(tr.STRIPS)), path))


if __name__ == "__main__":
    main()
