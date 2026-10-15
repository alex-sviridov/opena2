"""Command line entry point: python -m allods2 <group> <command> ...

    python -m allods2 gfx export FILE DEST [--palette PAL]

`gfx export` writes one PNG per sprite (DEST/<stem>_NNN.png) for .256,
b.256, .16 and .16a files, or DEST itself for a .bmp. --palette takes a
unit .pal / .bmp colour table, or human.pal[:N] for player N; it overrides
the embedded palette. Write into out/ or outside the repo, never samples/.
"""

import argparse
import os

from . import graphics as gfx


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


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m allods2", description="Allods 2 data tools.")
    groups = ap.add_subparsers(dest="group", required=True)
    g = groups.add_parser("gfx", help="graphics").add_subparsers(dest="cmd", required=True)
    ex = g.add_parser("export", help="write one PNG per sprite")
    ex.add_argument("file")
    ex.add_argument("dest")
    ex.add_argument("--palette", help="unit .pal, .bmp, or human.pal:N")
    ex.set_defaults(func=gfx_export)
    a = ap.parse_args(argv)
    return a.func(a)
