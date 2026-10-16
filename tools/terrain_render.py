"""Render a map's terrain with heights and lighting, as the game draws it.

    python tools/terrain_render.py MAP [-o out/terrain3d/NAME.png] [--base INSTALL_DIR]
        [--rect X Y W H] [--time MINUTES] [--flat] [--fog CX CY R]

MAP is a campaign map name (10.alm) or a game path (scenario/10.alm). --rect picks cells (default:
the whole map; a 256x256 map takes about two minutes). --time is game time in
minutes for the day/night tint and sun (default: day/night off). --flat draws
without heights for comparison. --fog overlays the fog pass for a made-up
sight circle (cells within R of CX, CY in sight, within 2R explored, rest
never seen; rect-relative). Specs: docs/formats/terrain.md,
docs/mechanics/lighting.md §3.1.
Output contains game data: out/ only.
"""

import argparse
import os

import numpy as np
from PIL import Image

from allods2.alm import load_alm
from allods2.common import INSTALL, OUT, as_fs
from allods2.graphics import lighting as lt, palette as pal, terrain as tr


def add_fog(img, top, heights, cx, cy, r):
    h, w = heights.shape
    yy, xx = np.mgrid[:h + 1, :w + 1]
    d2 = (xx - cx) ** 2 + (yy - cy) ** 2
    levels = np.where(d2 < r * r, lt.FOG_SEEN,
                      np.where(d2 < 4 * r * r, lt.FOG_EXPLORED, lt.FOG_UNSEEN))
    vy = tr.vertex_y(heights) + top
    surface = pal.pack16(img)
    lt.draw_fog(surface, levels, vy, w, h)
    return pal.unpack16(surface)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("--base", default=INSTALL)
    ap.add_argument("-o", "--out")
    ap.add_argument("--rect", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    ap.add_argument("--time", type=int)
    ap.add_argument("--flat", action="store_true")
    ap.add_argument("--fog", type=int, nargs=3, metavar=("CX", "CY", "R"))
    a = ap.parse_args(argv)
    fs = as_fs(a.base)
    path = a.map if "/" in a.map.replace("\\", "/") else "scenario/" + a.map
    m = load_alm(path, fs)
    terrain = tr.TerrainSet.load(fs)
    day = lt.daylight(a.time or 0, a.time is not None)
    heights = m.heights.astype(np.int8)
    light = lt.terrain_light(heights, day.angle, day.ambient, day.diffuse)
    x, y, w, h = a.rect or (0, 0, m.width, m.height)
    sub = (slice(y, y + h), slice(x, x + w))
    if a.flat:
        img = tr.render(m.tiles[sub], terrain, light=light[sub], tint=day.tint)
    else:
        img, top = tr.render_3d(m.tiles[sub], heights[sub], terrain, light[sub], tint=day.tint)
        if a.fog:
            img = add_fog(img, top, heights[sub], *a.fog)
    stem = os.path.splitext(path.rpartition("/")[2])[0]
    out = a.out or os.path.join(OUT, "terrain3d", stem + ("_flat" if a.flat else "") + ".png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    Image.fromarray(img).save(out)
    print("%s cells %d,%d %dx%d -> %s (%dx%d)" % (stem, x, y, w, h, out, img.shape[1], img.shape[0]))


if __name__ == "__main__":
    main()
