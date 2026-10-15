"""Write out/contact/terrain.png: all tile strips and ~30 map thumbnails.

    python tools/terrain_contact.py [INSTALL_DIR] [-o out/contact/terrain.png]

Top: the 13 sets x 4 strips as the game loads them (FUN_0047b899), labelled
set/strip and file. Bottom: map thumbnails, one pixel per cell = the mean
colour of the tile the game would draw (water frame 0, dirt overlay
applied, daylight row 46 on flat ground), plus one full-resolution crop.
Output contains game data: out/ only.
"""

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from allods2.alm import load_alm
from allods2.graphics import shade_table, terrain as tr
from allods2.graphics.palette import BRIGHT32

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_terrain import DEFAULT  # noqa: E402

DAY_ROW = 46


def thumbnail(m, terrain, table):
    t = m.tiles
    cache = {}
    out = np.zeros(t.shape + (3,), np.uint8)
    for y in range(m.height):
        for x in range(m.width):
            v = int(t[y, x])
            key = v if not v & tr.DIRT_FLAG else (v, tr.dirt_variant(x, y))
            if key not in cache:
                tile = terrain.cell_tile(v, x, y, animate=False)
                cache[key] = (0, 0, 0) if tile is None else table[DAY_ROW][tile].reshape(-1, 3).mean(0)
            out[y, x] = cache[key]
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base", nargs="?", default=DEFAULT)
    ap.add_argument("-o", "--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "out", "contact", "terrain.png"))
    ap.add_argument("-n", type=int, default=30)
    a = ap.parse_args(argv)
    terrain = tr.TerrainSet.load(os.path.join(a.base, "data", "graphics", "terrain"))
    table = shade_table(terrain.palette, tr.LIGHT_ROWS, BRIGHT32)
    font = ImageFont.load_default(10)

    strip_w = 4 * 34 + 10
    top_h = 448 + 30
    maps = sorted(glob.glob(os.path.join(a.base, "maps", "*.alm")))
    picks = [maps[round(i * (len(maps) - 1) / (a.n - 1))] for i in range(a.n)] if len(maps) > a.n else maps
    thumbs = [(os.path.basename(p), thumbnail(load_alm(p), terrain, table)) for p in picks]
    cols = 10
    cell = 270
    width = max(13 * strip_w, cols * cell) + 10
    crop_map = load_alm(picks[len(picks) // 2])
    cy, cx = crop_map.height // 2, crop_map.width // 2
    sub = crop_map.tiles[cy - 6:cy + 6, cx - 12:cx + 12]
    light = np.full(sub.shape, DAY_ROW)
    crop = tr.render(sub, terrain, light=light)
    height = top_h + (-(-len(thumbs) // cols)) * (cell + 16) + crop.shape[0] + 40
    sheet = Image.new("RGB", (width, height), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    for s in range(tr.SETS):
        x0 = 5 + s * strip_w
        draw.text((x0, 2), "set %d%s" % (s, " (water)" if s in tr.WATER else ""), fill=(230, 230, 230), font=font)
        draw.text((x0, 14), tr.strip_name(s, 0)[:6] + "%02d-%02d" % ((s & 3) * 4, (s & 3) * 4 + 3),
                  fill=(160, 160, 160), font=font)
        for j in range(4):
            a_ = terrain.strips.get((s, j))
            if a_ is not None:
                sheet.paste(Image.fromarray(table[DAY_ROW][a_]), (x0 + j * 34, 28))
    for i, (name, th) in enumerate(thumbs):
        x0, y0 = 5 + (i % cols) * cell, top_h + (i // cols) * (cell + 16)
        im = Image.fromarray(th)
        im.thumbnail((cell - 10, cell - 10))
        sheet.paste(im, (x0, y0))
        draw.text((x0, y0 + cell - 8), name[:44], fill=(230, 230, 230), font=font)
    y0 = height - crop.shape[0] - 30
    draw.text((5, y0 - 2), "full resolution, %s cells (%d..%d, %d..%d), flat, daylight row %d"
              % (crop_map.name, cx - 12, cx + 11, cy - 6, cy + 5, DAY_ROW), fill=(230, 230, 230), font=font)
    sheet.paste(Image.fromarray(crop), (5, y0 + 12))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sheet.save(a.out)
    print("%d sets, %d maps -> %s (%dx%d)" % (tr.SETS, len(thumbs), a.out, *sheet.size))


if __name__ == "__main__":
    main()
