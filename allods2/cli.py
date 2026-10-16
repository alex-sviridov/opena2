"""Command line entry point: python -m allods2 <group> <command> ...

    python -m allods2 gfx export FILE DEST [--palette PAL] [--index N | --sheet [--cols C]]
    python -m allods2 anim preview-all DEST [--data DIR] [--only CLASS ...]
    python -m allods2 anim preview SPRITE DEST [--data DIR] [--speed N]
                                   [--player P] [--variant V] [--grid PNG]

`gfx export` writes one PNG per sprite (DEST/<stem>_NNN.png) for .256,
b.256, .16 and .16a files, or DEST itself for a .bmp; with --index N, DEST
is the PNG of sprite N; with --sheet, DEST is one PNG with every sprite on
a grid of C columns (default 16). --palette takes a unit .pal / .bmp colour
table, or human.pal[:N] for player N; it overrides the embedded palette.

`anim preview` writes DEST/<action>_d<facing>.gif for each action of a
unit animation set and the 8 compass facings, at the game's tick period
for --speed (0..8, default 4), plus a still grid (rows = actions, columns
= facings; default out/contact/anim_<name>_grid.png). SPRITE is a
units.reg ID, a hero folder (heroes/swordsman), a unit file/folder
under graphics/units (monsters/goblin), or <kind>:<id> for the other
classes (structure:11, object:0, projectile:12, water:auto, burning:,
cursor:pickup, ui:chrgen_cube). `anim preview-all` writes
DEST/<class>/<name>/<action>[_dNN].gif and grid.png for everything.
--data defaults to $ALLODS2_DATA, else the install under samples/ (see
allods2.common). Write into out/ or outside the repo, never samples/.
"""

import argparse
import math
import os

import numpy as np

from . import graphics as gfx
from .common import DATA, OUT


def load_palette(spec):
    """'path' or 'path:N' (N-th of a multi-palette file such as human.pal)."""
    path, sep, n = spec.rpartition(":")
    if not (sep and n.isdigit()):
        path, n = spec, ""
    pals = gfx.load_palettes(path)
    return pals[int(n or 0)].rgb


def sheet(sf, palette=None, max_cols=16, pad=1):
    """(h, w, 4) RGBA of every sprite on a grid, in file order."""
    if not len(sf):
        raise SystemExit("no sprites")
    cw = max(s.width for s in sf.sprites) + pad
    ch = max(s.height for s in sf.sprites) + pad
    cols = min(max_cols, len(sf))
    out = np.zeros((math.ceil(len(sf) / cols) * ch, cols * cw, 4), np.uint8)
    for i in range(len(sf)):
        img = sf.to_rgba(i, palette)
        oy, ox = (i // cols) * ch, (i % cols) * cw
        out[oy:oy + img.shape[0], ox:ox + img.shape[1]] = img
    return out


def _write_one(path, img, what):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    gfx.write_png(path, img)
    print("%s -> %s (%dx%d)" % (what, path, img.shape[1], img.shape[0]))
    return 0


def gfx_export(a):
    if a.file.lower().endswith(".bmp"):
        return _write_one(a.dest, gfx.load_bmp(a.file).rgb, a.file)
    sf = gfx.SpriteFile.load(a.file)
    pal = load_palette(a.palette) if a.palette else None
    if a.index is not None:
        return _write_one(a.dest, sf.to_rgba(a.index, pal), "%s[%d]" % (a.file, a.index))
    if a.sheet:
        return _write_one(a.dest, sheet(sf, pal, a.cols), "%s: %d sprites" % (a.file, len(sf)))
    os.makedirs(a.dest, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.file))[0]
    for i in range(len(sf)):
        gfx.write_png(os.path.join(a.dest, "%s_%03d.png" % (stem, i)), sf.to_rgba(i, pal))
    print("%s: %d %s sprites -> %s/" % (a.file, len(sf), sf.kind, a.dest))
    return 0


def anim_preview(a):
    from . import anim
    from .anim import preview as P
    aset = anim.load_set(a.sprite, a.data)
    aset.player, aset.variant = a.player, a.variant
    paths = P.write_gifs(aset, a.dest, a.speed)
    grid = a.grid or os.path.join(OUT, "contact", "anim_%s_grid.png" % aset.name)
    os.makedirs(os.path.dirname(os.path.abspath(grid)), exist_ok=True)
    P.grid(aset).save(grid)
    print("%s %s (%s): %d GIFs -> %s/, grid -> %s"
          % (aset.kind, aset.name, ", ".join(aset.actions), len(paths), a.dest, grid))
    return 0


def anim_preview_all(a):
    from . import anim
    from .anim import preview as P
    total, used = 0, set()
    for cls, keys in anim.all_keys(a.data).items():
        if a.only and cls not in a.only:
            continue
        for key in keys:
            aset = anim.load_set(key, a.data)
            name = aset.name
            if (cls, name) in used:         # e.g. units.reg IDs 1 and 2 share humans/unarmed
                name = "%s_%s" % (name, key.replace(":", "_").replace("/", "_"))
            used.add((cls, name))
            d = os.path.join(a.dest, cls, name)
            n = len(P.write_gifs(aset, d, a.speed))
            P.grid(aset).save(os.path.join(d, "grid.png"))
            total += n
        print("%s: %d sets" % (cls, len(keys)))
    print("%d GIFs -> %s/" % (total, a.dest))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m allods2", description="Allods 2 data tools.")
    groups = ap.add_subparsers(dest="group", required=True)
    g = groups.add_parser("gfx", help="graphics").add_subparsers(dest="cmd", required=True)
    ex = g.add_parser("export", help="write one PNG per sprite")
    ex.add_argument("file")
    ex.add_argument("dest")
    ex.add_argument("--palette", help="unit .pal, .bmp, or human.pal:N")
    one = ex.add_mutually_exclusive_group()
    one.add_argument("--index", type=int, help="write only sprite N to DEST (a PNG)")
    one.add_argument("--sheet", action="store_true", help="write all sprites on one grid PNG")
    ex.add_argument("--cols", type=int, default=16, help="grid columns for --sheet")
    ex.set_defaults(func=gfx_export)
    g = groups.add_parser("anim", help="unit animation").add_subparsers(dest="cmd", required=True)
    pv = g.add_parser("preview", help="animated GIFs per action and facing, plus a still grid")
    pv.add_argument("sprite")
    pv.add_argument("dest")
    pv.add_argument("--data", default=DATA)
    pv.add_argument("--speed", type=int, default=4, choices=range(9))
    pv.add_argument("--player", type=int, default=0, help="human.pal player colour (Palette 0)")
    pv.add_argument("--variant", type=int, default=0, help="palette<N>.pal variant (Palette > 0)")
    pv.add_argument("--grid", help="still grid PNG path")
    pv.set_defaults(func=anim_preview)
    pa = g.add_parser("preview-all", help="GIFs and grids for every animated thing, by class")
    pa.add_argument("dest")
    pa.add_argument("--data", default=DATA)
    pa.add_argument("--speed", type=int, default=4, choices=range(9))
    pa.add_argument("--only", nargs="*", help="classes: units structures objects projectiles "
                                             "terrain effects cursors ui")
    pa.set_defaults(func=anim_preview_all)
    a = ap.parse_args(argv)
    return a.func(a)
