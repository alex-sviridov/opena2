"""Labelled contact sheets of one unit sprite file, to check its frame layout.

    python tools/anim_contact.py NAME FILE TYPE_ID [DATA_DIR] [-o out/contact]

FILE is relative to graphics/units without extension (e.g.
heroes/swordsman/sprites); TYPE_ID the units.reg ID whose layout applies.
Writes:
  anim_<NAME>_raw.png     every frame in file order, frame index under it;
                          the label colour is the block the layout assigns
                          (stand, move, attack, dying, bones/idle, unused)
  anim_<NAME>_layout.png  one row per (block, sprite direction), each frame
                          labelled "index", rows labelled with the facings
                          d that use the direction (m = drawn mirrored)
Defaults (no arguments): the three specimens heroes/swordsman (ID 3),
monsters/goblin (64) and monsters/dragon (71). Palette: palette.pal next to
the file or in its parent, else human.pal player 0. Output contains game
data: out/ only.
"""

import argparse
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

from allods2 import graphics as gfx
from allods2 import units as U

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sprite_contact import over_checker  # noqa: E402
from validate_sprites import DEFAULT_DATA, ROOT  # noqa: E402

SPECIMENS = [("hero_swordsman", "heroes/swordsman/sprites", 3),
             ("goblin", "monsters/goblin/sprites", 64),
             ("dragon", "monsters/dragon/sprites", 71)]
COLOURS = {"stand": (255, 255, 255), "move": (120, 200, 255), "attack": (255, 120, 120),
           "dying": (255, 200, 80), "tail": (160, 255, 140), "unused": (255, 0, 255)}
LABEL_H = 12
MAX_CELL = 128


def palette(path, data):
    for d in (os.path.dirname(path), os.path.dirname(os.path.dirname(path))):
        p = os.path.join(d, "palette.pal")
        if os.path.isfile(p):
            return gfx.load_pal_file(p)
    return gfx.load_human_palettes(os.path.join(data, U.UNITS_DIR, "humans", "human.pal"))[0]


def blocks(t, own_death, n):
    """[(block, direction, first, count)] in file order, per units.md."""
    out = [("stand", None, 0, t.stand_frames)]
    pos = t.stand_frames
    per = [("move", U._mb(t)), ("attack", t.AttackPhases)]
    if own_death:
        per.append(("dying", t.DyingPhases))
    tail = t.IdlePhases or (max(t.BonePhases, 0) if own_death else 0)
    per.append(("tail", tail))
    for name, k in per:
        for i in range(t.dirs):
            if k > 0:
                out.append((name, i, pos, k))
            pos += max(k, 0)
    if pos < n:
        out.append(("unused", None, pos, n - pos))
    return out


def facings(t, i, stand):
    """Facings d (0..15) that draw sprite direction i; 'm' = mirrored."""
    res = []
    for d in range(16):
        j, m = (U.dir16 if stand else U.dir8)(d, t.Flip)
        if j == i:
            res.append("%d%s" % (d, "m" if m else ""))
    return ",".join(res)


def cell_image(sf, pal, idx, cw, ch, label, colour):
    im = Image.new("RGB", (cw, ch + LABEL_H), (40, 40, 40))
    fr = Image.fromarray(over_checker(sf.to_rgba(idx, pal)))
    if fr.width > cw or fr.height > ch:
        fr.thumbnail((cw, ch))
    im.paste(fr, ((cw - fr.width) // 2, (ch - fr.height) // 2))
    ImageDraw.Draw(im).text((2, ch), label, fill=colour)
    return im


def sheet(rows, cw, ch, left=0):
    width = left + max(len(r[1]) for r in rows) * cw
    out = Image.new("RGB", (width, len(rows) * (ch + LABEL_H)), (20, 20, 20))
    dr = ImageDraw.Draw(out)
    for y, (title, cells) in enumerate(rows):
        oy = y * (ch + LABEL_H)
        if left:
            dr.text((2, oy + 2), title, fill=(255, 255, 255))
        for x, c in enumerate(cells):
            out.paste(c, (left + x * cw, oy))
    return out


def make(name, rel, type_id, data, out_dir):
    types = U.by_id(U.load_unit_types(os.path.join(data, U.UNITS_DIR, "units.reg")))
    t = types[type_id]
    path = os.path.join(data, U.UNITS_DIR, rel + ".256")
    sf = gfx.SpriteFile.load(path)
    pal = palette(path, data)
    n = len(sf)
    own_death = t.Dying == t.id and not rel.startswith("heroes") or \
        os.path.basename(os.path.dirname(rel)) in ("unarmed", "mage_st")
    bl = blocks(t, own_death, n)
    sizes = [(sf[i].width, sf[i].height) for i in range(n)]
    cw = min(MAX_CELL, max(w for w, _ in sizes) + 4)
    ch = min(MAX_CELL, max(h for _, h in sizes) + 2)
    owner = {}
    for b, _, first, k in bl:
        for f in range(first, first + k):
            owner[f] = b
    cols = t.stand_frames if t.stand_frames == 16 else 18
    cells = [cell_image(sf, pal, f, cw, ch, str(f), COLOURS[owner.get(f, "unused")])
             for f in range(n)]
    raw = sheet([("", cells[r:r + cols]) for r in range(0, n, cols)], cw, ch)
    os.makedirs(out_dir, exist_ok=True)
    raw.save(os.path.join(out_dir, "anim_%s_raw.png" % name))
    rows = []
    for b, i, first, k in bl:
        title = b if i is None else "%s dir %d" % (b, i)
        if b == "stand":
            title += "\nd: dir = (d-8)&15"
        elif i is not None:
            title += "\nd=" + facings(t, i, False)
        rows.append((title, [cells[f] for f in range(first, min(first + k, n))]))
    lay = sheet(rows, cw, ch, left=140)
    lay.save(os.path.join(out_dir, "anim_%s_layout.png" % name))
    print("%s: %s, %d frames, layout %d (type %d, Flip %d)"
          % (name, rel, n, sum(k for b, _, _, k in bl if b != "unused"), t.id, t.Flip))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec", nargs="*", help="NAME FILE TYPE_ID [DATA_DIR]")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "out", "contact"))
    a = ap.parse_args(argv)
    data = a.spec[3] if len(a.spec) > 3 else DEFAULT_DATA
    specs = [(a.spec[0], a.spec[1], int(a.spec[2]))] if a.spec else SPECIMENS
    for name, rel, tid in specs:
        make(name, rel, tid, data, a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
