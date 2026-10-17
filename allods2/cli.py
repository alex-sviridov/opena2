"""Command line entry point: python -m allods2 <group> <command> ...

    python -m allods2 gfx export FILE DEST [--palette PAL] [--index N | --sheet [--cols C]]
    python -m allods2 anim preview-all DEST [--install DIR] [--only CLASS ...]
    python -m allods2 anim preview SPRITE DEST [--install DIR] [--speed N]
                                   [--player P] [--variant V] [--grid PNG]
    python -m allods2 map info MAP [--install DIR]
    python -m allods2 map render MAP DEST.png [--layers terrain objects structures units items | all] [--relief] [--dirt]
                                 [--rect X Y W H] [--install DIR]
    python -m allods2 data export units|items|spells DEST.json [--install DIR]
    python -m allods2 res ls [PATH] [--install DIR]
    python -m allods2 res list ARCHIVE.res
    python -m allods2 res extract INSTALL|ARCHIVE.res DEST

FILE and PAL are game paths (graphics/units/monsters/bat/sprites.256, read
from the install's .res archives) or, when such a file exists on disk,
plain file paths.
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

MAP is a campaign map (10, 10.alm, scenario/10.alm) or a file on disk.
`map info` prints the header (size, version, players, tile sets, name and
description decoded from cp1251, section counts). `map render` draws the
layers: terrain = the Tiles block from the original tile strips, flat and
unlit by default (one 32x32 tile per cell); --relief draws it as the game
does (heights, terrain light at 06:00; slow on big maps); --dirt keeps the
editor's dirt flag, which the game clears on load; --rect crops to cells.
objects = trees, rocks, decorations (Objects block); structures = buildings and
bridges (section 4); both are depth-sorted like the game's view draw, drawn at
animation clock --clock N (default 0); units = map units in their idle frame (front view, owner's
human.pal colour; the file has no facing); items = the backpack sprite of each ground pile; all = every layer;
shadows and fog are not drawn.

`res ls` lists a game folder (archives at the top); `res list` prints
offset, size and path of every file in one archive; `res extract` unpacks
one archive, or every .res of an install, into DEST/<archive stem>/... for
inspection (the library itself reads the archives directly).
--install defaults to $ALLODS2_INSTALL, else samples/allods2_en_gog (see
allods2.common). Write into out/ or outside the repo, never samples/.
"""

import argparse
import math
import os

import numpy as np

from . import graphics as gfx
import a2res
from a2res import OS

from .common import INSTALL, OUT, as_fs


def source(path, install=None):
    """(fs, path): a file on disk as is, else a game path in the install."""
    if os.path.isfile(path):
        return OS, path
    return as_fs(install), path


def load_palette(spec, install=None):
    """'path' or 'path:N' (N-th of a multi-palette file such as human.pal)."""
    path, sep, n = spec.rpartition(":")
    if not (sep and n.isdigit()):
        path, n = spec, ""
    pals = gfx.load_palettes(path, source(path, install)[0])
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
    fs, path = source(a.file, a.install)
    if a.file.lower().endswith(".bmp"):
        return _write_one(a.dest, gfx.load_bmp(path, fs).rgb, a.file)
    sf = gfx.SpriteFile.load(path, fs)
    pal = load_palette(a.palette, a.install) if a.palette else None
    if a.index is not None:
        return _write_one(a.dest, sf.to_rgba(a.index, pal), "%s[%d]" % (a.file, a.index))
    if a.sheet:
        return _write_one(a.dest, sheet(sf, pal, a.cols), "%s: %d sprites" % (a.file, len(sf)))
    os.makedirs(a.dest, exist_ok=True)
    stem = os.path.splitext(os.path.basename(a.file.replace("\\", "/")))[0]
    for i in range(len(sf)):
        gfx.write_png(os.path.join(a.dest, "%s_%03d.png" % (stem, i)), sf.to_rgba(i, pal))
    print("%s: %d %s sprites -> %s/" % (a.file, len(sf), sf.kind, a.dest))
    return 0


def anim_preview(a):
    from . import anim
    from .anim import preview as P
    aset = anim.load_set(a.sprite, as_fs(a.install))
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
    fs = as_fs(a.install)
    total, used = 0, set()
    for cls, keys in anim.all_keys(fs).items():
        if a.only and cls not in a.only:
            continue
        for key in keys:
            aset = anim.load_set(key, fs)
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


def open_map(spec, install=None):
    from .formats import Map
    if os.path.isfile(spec):
        return Map.load(spec, a2res.OS)
    path = spec.replace("\\", "/")
    if "/" not in path:
        path = "scenario/" + path
    if not path.lower().endswith(".alm"):
        path += ".alm"
    return Map.load(path, as_fs(install))


def map_info(a):
    m = open_map(a.map, a.install)
    h = m.header
    print("%s: %d x %d cells, version %d, section tag %d" % (m.name, h.width, h.height, h.version, h.tag))
    print("name:        %r" % h.name)
    print("description: %r" % h.description)
    print("players:     %d" % h.player_count)
    print("tile sets:   0x%04x = %s" % (h.tile_sets, " ".join(map(str, h.tile_set_list))))
    print("light:       angle %.4f, ambient %d, diffuse %d, field_0c %d (initial; the game overwrites)"
          % (h.angle, h.ambient, h.diffuse, h.field_0c))
    print("counts:      sec4 %d, sec6 %d, sec7 %d, sec8 %d, sec10 %d, sec11 %s, sec12 %d"
          % (h.n_sec4, h.n_sec6, h.n_sec7, h.n_sec8, h.n_sec10, h.n_sec11, h.n_sec12))
    print("misc:        84=%d 88=%d 8c=%d 90=%d" % (h.field_84, h.field_88, h.field_8c, h.field_90))
    print("terrain:     %d cells, %d with the dirt flag, %d water" % (
        h.cells, int(((m.terrain & 0x2000) != 0).sum()),
        int((((m.terrain & 0x1FFF) >> 6 >= 8) & ((m.terrain & 0x1FFF) >> 6 <= 11)).sum())))
    walk = ""
    if min(h.width, h.height) > 16:
        inner = (slice(8, -8), slice(8, -8))
        walk = "; walkable (playable area): walker %.0f%%, Ghost/Bee %.0f%%" % (
            100 * m.passability(1)[inner].mean(), 100 * m.passability(2)[inner].mean())
    print("heights:     %d..%d%s" % (m.heights_i8.min(), m.heights_i8.max(), walk))
    print("sections:    " + ", ".join("%d: %d B" % (k, len(v)) for k, v in sorted(m.alm.sections.items())
                                    for v in [v.data]))
    return 0


LAYERS = ("terrain", "objects", "structures", "units", "items")


def map_render(a):
    a.layers = [l for part in a.layers for l in part.split(",") if l]
    for l in a.layers:
        if l not in LAYERS and l != "all":
            raise SystemExit("unknown layer %r (%s, all)" % (l, ", ".join(LAYERS)))
    if "all" in a.layers:
        a.layers = list(LAYERS)
    from .graphics import lighting as lt, terrain as tr
    m = open_map(a.map, a.install)
    cells = m.terrain if a.dirt else m.runtime_terrain()
    x, y, w, h = a.rect or (0, 0, m.width, m.height)
    sub = (slice(y, y + h), slice(x, x + w))
    terrain = tr.TerrainSet.load(as_fs(a.install))
    if a.relief:
        day = lt.daylight(0, False)
        heights = m.heights.astype(np.int8)
        light = lt.terrain_light(heights, day.angle, day.ambient, day.diffuse)
        img, _ = tr.render_3d(cells[sub], heights[sub], terrain, light[sub], tint=day.tint)
    else:
        img = tr.render(cells[sub], terrain)
    if {"objects", "structures", "units", "items"} & set(a.layers):
        from .anim.scene import Scene, draw_scene
        from .graphics.canvas import Canvas
        if a.rect:
            raise SystemExit("--rect with objects/structures is not supported")
        top = _relief_top(m, sub) if a.relief else 0
        cv = Canvas(1, 1)
        cv.pix = np.ascontiguousarray(img)
        scene = Scene(as_fs(a.install))
        draw_scene(cv, m, scene, top=top, relief=a.relief, clock=a.clock,
                   objects="objects" in a.layers, structures="structures" in a.layers,
                   units="units" in a.layers, items="items" in a.layers)
        img = cv.pix
    return _write_one(a.dest, img, "%s %s" % (m.name, "+".join(a.layers)))


def _relief_top(m, sub):
    """Margin above map row 0 in render_3d's image (see tr.vertex_y)."""
    from .graphics import terrain as tr
    return max(0, -int(tr.vertex_y(m.heights[sub]).min()))


def res_ls(a):
    fs = as_fs(a.install)
    for name in fs.listdir(a.path):
        p = a2res.join(a.path, name)
        print("%-5s %10s %s" % ("dir" if fs.isdir(p) else "", "" if fs.isdir(p) else len(fs.read(p)), p))
    return 0


def res_list(a):
    with a2res.ResArchive(a.archive) as arc:
        for path, e in arc.walk():
            print("0x%08x %10d %s" % (e.a, e.b, path))
    return 0


def res_extract(a):
    if os.path.isdir(a.source):
        archives = list(a2res.ResFS(a.source).archives.values())
    else:
        archives = [a2res.ResArchive(a.source)]
    for arc in archives:
        print("%s: %d files -> %s/" % (os.path.basename(arc.path), a2res.extract(arc, a.dest),
                                      os.path.join(a.dest, arc.name)))
    return 0


def data_export(a):
    import json
    fs = as_fs(a.install)
    if a.table == "items":
        from .formats import itemdefs
        table = itemdefs.load(fs)
        msg = "%d item definitions (%d weapons, %d shields, %d armour, %d special), %d names -> %s" % (
            len(table), *(len(table.of_kind(k)) for k in itemdefs.KINDS), len(table.names), a.dest)
    elif a.table == "spells":
        from .formats import spelldefs
        table = spelldefs.load(fs)
        msg = "%d spells (%d empty records), %d with descriptions -> %s" % (
            len(table), table.extra_records, sum(1 for d in table if d.description), a.dest)
    else:
        from .formats import unitstats
        table = unitstats.load(fs)
        msg = "%d unit types (%d monsters, %d humans) -> %s" % (
            len(table), len(table.of_kind("monster")), len(table.of_kind("human")), a.dest)
    os.makedirs(os.path.dirname(os.path.abspath(a.dest)), exist_ok=True)
    with open(a.dest, "w", encoding="utf-8") as f:
        json.dump(table.to_dict(), f, indent=1, sort_keys=True)
    print(msg)
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
    ex.add_argument("--install", default=INSTALL)
    ex.set_defaults(func=gfx_export)
    g = groups.add_parser("anim", help="unit animation").add_subparsers(dest="cmd", required=True)
    pv = g.add_parser("preview", help="animated GIFs per action and facing, plus a still grid")
    pv.add_argument("sprite")
    pv.add_argument("dest")
    pv.add_argument("--install", default=INSTALL)
    pv.add_argument("--speed", type=int, default=4, choices=range(9))
    pv.add_argument("--player", type=int, default=0, help="human.pal player colour (Palette 0)")
    pv.add_argument("--variant", type=int, default=0, help="palette<N>.pal variant (Palette > 0)")
    pv.add_argument("--grid", help="still grid PNG path")
    pv.set_defaults(func=anim_preview)
    pa = g.add_parser("preview-all", help="GIFs and grids for every animated thing, by class")
    pa.add_argument("dest")
    pa.add_argument("--install", default=INSTALL)
    pa.add_argument("--speed", type=int, default=4, choices=range(9))
    pa.add_argument("--only", nargs="*", help="classes: units structures objects projectiles "
                                             "terrain effects cursors ui")
    pa.set_defaults(func=anim_preview_all)
    g = groups.add_parser("map", help=".alm maps").add_subparsers(dest="cmd", required=True)
    mi = g.add_parser("info", help="print the map header")
    mi.add_argument("map")
    mi.add_argument("--install", default=INSTALL)
    mi.set_defaults(func=map_info)
    mr = g.add_parser("render", help="draw map layers into a PNG")
    mr.add_argument("map")
    mr.add_argument("dest")
    mr.add_argument("--layers", nargs="+", default=["terrain"],
                    help="terrain objects structures units items, or all (space or comma separated)")
    mr.add_argument("--clock", type=int, default=0, help="animation clock of the objects (default 0)")
    mr.add_argument("--relief", action="store_true", help="heights and lighting as in game (slow)")
    mr.add_argument("--dirt", action="store_true", help="keep the editor's dirt flag")
    mr.add_argument("--rect", type=int, nargs=4, metavar=("X", "Y", "W", "H"))
    mr.add_argument("--install", default=INSTALL)
    mr.set_defaults(func=map_render)
    g = groups.add_parser("res", help=".res archives").add_subparsers(dest="cmd", required=True)
    d = g.add_parser("ls", help="list a game folder")
    d.add_argument("path", nargs="?", default="")
    d.add_argument("--install", default=INSTALL)
    d.set_defaults(func=res_ls)
    ls = g.add_parser("list", help="list the files of an archive")
    ls.add_argument("archive")
    ls.set_defaults(func=res_list)
    x = g.add_parser("extract", help="unpack an archive or every archive of an install")
    x.add_argument("source", help="ARCHIVE.res or an install directory")
    x.add_argument("dest")
    x.set_defaults(func=res_extract)
    g = groups.add_parser("data", help="game database tables").add_subparsers(dest="cmd", required=True)
    de = g.add_parser("export", help="write a table as JSON (units: monsters and humans; items: weapons, shields, armour, special items; spells)")
    de.add_argument("table", choices=("units", "items", "spells"))
    de.add_argument("dest")
    de.add_argument("--install", default=INSTALL)
    de.set_defaults(func=data_export)
    a = ap.parse_args(argv)
    return a.func(a)
