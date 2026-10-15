"""Write out/contact/units.png: per unit type, the frames the game draws.

    python tools/unit_contact.py [DATA_DIR] [-o out/contact/units.png]

Row per Unit<n>: stand for facings d = 0..15 (mirrored where Flip says),
then for facing d = 8 (sprite direction 0): one move cycle, one attack
cycle, the dying phases and bone stages of the Dying type. Palette:
palette.pal when Palette > 0, else human.pal player 0. Checkerboard =
transparent. Output contains game data: out/ only.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from allods2 import graphics as gfx
from allods2 import units as U

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sprite_contact import over_checker  # noqa: E402
from validate_sprites import DEFAULT_DATA, ROOT  # noqa: E402

CELL = 64


def palette(t, data):
    if t.Palette > 0:
        return gfx.load_pal_file(t.palette_paths(data)[0])
    return gfx.load_human_palettes(os.path.join(data, U.UNITS_DIR, "humans", "human.pal"))[0]


def tile(sf, pal, idx_m):
    idx, mirrored = idx_m
    if sf is None or idx >= len(sf):
        return np.full((CELL, CELL, 3), (90, 0, 0), np.uint8)
    rgba = sf.to_rgba(idx, pal)
    if mirrored:
        rgba = rgba[:, ::-1]
    im = Image.fromarray(over_checker(rgba))
    im.thumbnail((CELL, CELL))
    out = Image.new("RGB", (CELL, CELL), (40, 40, 40))
    out.paste(im, ((CELL - im.width) // 2, (CELL - im.height) // 2))
    return np.asarray(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data", nargs="?", default=DEFAULT_DATA)
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "out", "contact", "units.png"))
    a = ap.parse_args(argv)
    types = U.load_unit_types(os.path.join(a.data, U.UNITS_DIR, "units.reg"))
    ids = U.by_id(types)
    cache = {}

    def sprites(t):
        p = t.sprite_paths(a.data)[0]
        if p not in cache:
            cache[p] = gfx.SpriteFile.load(p) if t.file and os.path.isfile(p) and os.path.getsize(p) > 4 else None
        return cache[p]

    rows = []
    for t in types:
        sf, pal = sprites(t), palette(t, a.data) if t.file else None
        cells = [tile(sf, pal, U.stand_frame(t, d)) for d in range(16)]
        d = 8
        if t.MovePhases > 0:
            cells += [tile(sf, pal, U.move_frame(t, d, p)) for p in t.sequence("Move")[::2]]
        if t.AttackPhases > 0:
            cells += [tile(sf, pal, U.attack_frame(t, d, p)) for p in sorted(set(t.sequence("Attack")))]
        td = ids.get(t.Dying)
        if td is not None and td.DyingPhases > 0 and td.file:
            sd, pd = sprites(td), palette(td, a.data)
            cells += [tile(sd, pd, U.dying_frame(td, d, s)) for s in range(td.DyingPhases)]
            cells += [tile(sd, pd, U.bones_frame(td, d, st)) for st in range(2, 2 + max(td.BonePhases, 0))]
        rows.append(("Unit%d ID %d %s%s" % (t.index, t.id, t.DescText or t.file, " [Flip]" if t.Flip else ""), cells))
    width = max(len(c) for _, c in rows) * CELL + 10
    sheet = Image.new("RGB", (width, len(rows) * (CELL + 14) + 10), (40, 40, 40))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(10)
    for r, (label, cells) in enumerate(rows):
        y = 5 + r * (CELL + 14)
        draw.text((5, y), label, fill=(230, 230, 230), font=font)
        for i, c in enumerate(cells):
            sheet.paste(Image.fromarray(c), (5 + i * CELL, y + 12))
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    sheet.save(a.out)
    print("%d unit types -> %s (%dx%d)" % (len(rows), a.out, *sheet.size))


if __name__ == "__main__":
    main()
