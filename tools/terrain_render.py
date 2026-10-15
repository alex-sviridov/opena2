"""Render a map's terrain with heights and lighting, as the game draws it.

    python tools/terrain_render.py MAP.alm [-o out/terrain3d/NAME.png]
        [--rect X Y W H] [--time MINUTES] [--flat]

MAP may be a path or a name in INSTALL_DIR/maps. --rect picks cells (default:
the whole map; a 256x256 map takes about two minutes). --time is game time in
minutes for the day/night tint and sun (default: day/night off). --flat draws
without heights for comparison. Spec: docs/formats/terrain.md.
Output contains game data: out/ only.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image

from allods2.alm import load_alm
from allods2.graphics import lighting as lt, terrain as tr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate_terrain import DEFAULT  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("map")
    ap.add_argument("--base", default=DEFAULT)
    ap.add_argument("-o", "--out")
    ap.add_argument("--rect", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    ap.add_argument("--time", type=int)
    ap.add_argument("--flat", action="store_true")
    a = ap.parse_args(argv)
    path = a.map if os.path.exists(a.map) else os.path.join(a.base, "maps", a.map)
    m = load_alm(path)
    terrain = tr.TerrainSet.load(os.path.join(a.base, "data", "graphics", "terrain"))
    day = lt.daylight(a.time or 0, a.time is not None)
    heights = m.heights.astype(np.int8)
    light = lt.terrain_light(heights, day.angle, day.ambient, day.diffuse)
    x, y, w, h = a.rect or (0, 0, m.width, m.height)
    sub = (slice(y, y + h), slice(x, x + w))
    if a.flat:
        img = tr.render(m.tiles[sub], terrain, light=light[sub], tint=day.tint)
    else:
        img, _ = tr.render_3d(m.tiles[sub], heights[sub], terrain, light[sub], tint=day.tint)
    stem = os.path.splitext(os.path.basename(path))[0]
    out = a.out or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "out", "terrain3d", stem + ("_flat" if a.flat else "") + ".png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    Image.fromarray(img).save(out)
    print("%s cells %d,%d %dx%d -> %s (%dx%d)" % (stem, x, y, w, h, out, img.shape[1], img.shape[0]))


if __name__ == "__main__":
    main()
