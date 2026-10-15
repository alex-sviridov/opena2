"""Command line entry point: python -m allods2 <group> <command> ...

    python -m allods2 gfx export FILE DEST [--palette PAL]
    python -m allods2 anim preview SPRITE DEST [--data DIR] [--speed N]
                                   [--player P] [--variant V] [--grid PNG]

`gfx export` writes one PNG per sprite (DEST/<stem>_NNN.png) for .256,
b.256, .16 and .16a files, or DEST itself for a .bmp. --palette takes a
unit .pal / .bmp colour table, or human.pal[:N] for player N; it overrides
the embedded palette.

`anim preview` writes DEST/<action>_d<facing>.gif for each action of a
unit animation set and the 8 compass facings, at the game's tick period
for --speed (0..8, default 4), plus a still grid (rows = actions, columns
= facings; default out/contact/anim_<name>_grid.png). SPRITE is a
units.reg ID, a hero folder (heroes/swordsman) or a unit file/folder
under graphics/units (monsters/goblin). --data defaults to $ALLODS2_DATA,
else samples/.../data under the current directory. Write into out/ or
outside the repo, never samples/.
"""

import argparse
import os

from . import graphics as gfx

DEFAULT_DATA = os.path.join("samples", "Allods2_en_251005", "Allods2_en", "data")


def load_palette(spec):
    """'path' or 'path:N' (N-th of a multi-palette file such as human.pal)."""
    path, sep, n = spec.rpartition(":")
    if not (sep and n.isdigit()):
        path, n = spec, ""
    pals = gfx.load_palettes(path)
    return pals[int(n or 0)].rgb


def gfx_export(a):
    if a.file.lower().endswith(".bmp"):
        os.makedirs(os.path.dirname(os.path.abspath(a.dest)), exist_ok=True)
        gfx.write_png(a.dest, gfx.load_bmp(a.file).rgb)
        print("%s -> %s" % (a.file, a.dest))
        return 0
    sf = gfx.SpriteFile.load(a.file)
    pal = load_palette(a.palette) if a.palette else None
    os.makedirs(a.dest, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.file))[0]
    for i in range(len(sf)):
        gfx.write_png(os.path.join(a.dest, "%s_%03d.png" % (stem, i)), sf.to_rgba(i, pal))
    print("%s: %d %s sprites -> %s/" % (a.file, len(sf), sf.kind, a.dest))
    return 0


def anim_preview(a):
    from . import anim, anim_preview as P
    aset = anim.load_animation_set(a.sprite, a.data)
    pals = {s: aset.palette(s, a.player, a.variant) for s in ("main", "death") if s in aset.paths}
    paths = P.write_gifs(aset, a.dest, a.speed, pals)
    grid = a.grid or os.path.join("out", "contact", "anim_%s_grid.png" % aset.name)
    os.makedirs(os.path.dirname(os.path.abspath(grid)), exist_ok=True)
    P.grid(aset, pals).save(grid)
    print("%s (type %d, %s): %d GIFs -> %s/, grid -> %s"
          % (aset.name, aset.t.id, ", ".join(aset.actions), len(paths), a.dest, grid))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m allods2", description="Allods 2 data tools.")
    groups = ap.add_subparsers(dest="group", required=True)
    g = groups.add_parser("gfx", help="graphics").add_subparsers(dest="cmd", required=True)
    ex = g.add_parser("export", help="write one PNG per sprite")
    ex.add_argument("file")
    ex.add_argument("dest")
    ex.add_argument("--palette", help="unit .pal, .bmp, or human.pal:N")
    ex.set_defaults(func=gfx_export)
    g = groups.add_parser("anim", help="unit animation").add_subparsers(dest="cmd", required=True)
    pv = g.add_parser("preview", help="animated GIFs per action and facing, plus a still grid")
    pv.add_argument("sprite")
    pv.add_argument("dest")
    pv.add_argument("--data", default=os.environ.get("ALLODS2_DATA", DEFAULT_DATA))
    pv.add_argument("--speed", type=int, default=4, choices=range(9))
    pv.add_argument("--player", type=int, default=0, help="human.pal player colour (Palette 0)")
    pv.add_argument("--variant", type=int, default=0, help="palette<N>.pal variant (Palette > 0)")
    pv.add_argument("--grid", help="still grid PNG path")
    pv.set_defaults(func=anim_preview)
    a = ap.parse_args(argv)
    return a.func(a)
