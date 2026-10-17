"""python -m engine run MAP [--x PX --y PX] [--speed N] [--size WxH] [--install DIR]
   python -m engine screenshot MAP X Y DEST.png [--tick N] [--size WxH] [--install DIR]
   python -m engine world-info MAP [--install DIR] [--strict]
   python -m engine world-dump MAP DEST.json [--install DIR]
   python -m engine minimap MAP DEST.png [--units] [--install DIR]

MAP as for `python -m allods2 map` (10, scenario/10.alm, or a file).  X, Y =
the viewport's top-left in world pixels (x = 32*col, y = 32*row - height).
`run` starts at the playable-area corner (256, 256) by default.  Arrow keys
or the mouse at the window edge scroll; F1/F2/F3 toggle the debug overlays
passability / markers / depth; Esc quits.  --debug takes a comma list of those
names (screenshot: drawn in the PNG).  Objects and structures are drawn with the
game's default options; --no-* switch shadows, the BRIGHT2 light row, the b.256
smoothing, or both layers off.  `screenshot` writes a PNG
with no window (SDL dummy driver).  `run` shows the minimap top right (click or
drag moves the camera; --no-minimap hides it); `minimap` writes its base image (no pygame).  Docs: docs/engine/architecture.md.
"""

import argparse
import os
import sys

from engine.world import World


def _size(s):
    w, _, h = s.lower().partition("x")
    return int(w), int(h)


def _world(a):
    """The map's World (no pygame)."""
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    return World.from_map(open_map(a.map, a.install), AssetCache(a.install))


def world_info(a):
    """Entity counts, blocked cells, unknown types (spec "CLI")."""
    w = _world(a)
    r = w.report
    kinds = {}
    for (kind, tid), n in r.counts.items():
        kinds.setdefault(kind, []).append((tid, n))
    print("%s: %d x %d cells" % (w.name, w.width, w.height))
    print("entities: %d (%s)" % (len(w.objects), ", ".join(
        "%s %d" % (k, sum(n for _, n in kinds.get(k, ()))) for k in ("object", "structure", "bridge"))))
    for k in ("object", "structure", "bridge"):
        if k in kinds:
            print("%s types: %s" % (k, " ".join("%d:%d" % t for t in sorted(kinds[k]))))
    print("players %d, units %d (%d on blocked cells), ground piles %d" % (
        len(w.players), len(w.units), r.units_on_blocked, len(w.items)))
    print("blocked cells (walker mask 0x41): %d of %d" % (int((~w.walkable(1)).sum()), w.width * w.height))
    print("ignored outside the window: %d" % r.ignored_outside_window)
    print("unknown types: %d, unknown units: %d" % (len(r.unknown), len(r.unknown_units)))
    for uid, tid, sid, x, y in r.unknown_units:
        print("  unit uid %d type %d serverID %d at (%d, %d)" % (uid, tid, sid, x, y))
    for kind, tid, x, y in r.unknown:
        print("  %s type %d at (%d, %d)" % (kind, tid, x, y))
    return 2 if (a.strict and r.unknown) else 0


def world_dump(a):
    w = _world(a)
    with open(a.dest, "w", encoding="ascii") as f:
        f.write(w.dump_json())
    print("%s: %d entities -> %s" % (w.name, len(w.objects), a.dest))
    return 0


def minimap_cmd(a):
    """Write the minimap image of a map (no pygame, no camera rectangle)."""
    from allods2.common import as_fs
    from allods2.graphics import write_png
    from allods2.cli import open_map
    from allods2.minimap import load_color_table, minimap_rgb
    m = open_map(a.map, a.install)
    rgb = minimap_rgb(m.runtime_terrain(), load_color_table(as_fs(a.install)))
    if a.units:
        from allods2.assets import AssetCache
        from allods2.minimap import load_dot_colors
        from engine.view.minimap import MinimapGeometry, draw_unit_dots
        rgb = rgb.copy()
        draw_unit_dots(rgb, MinimapGeometry(m.width, m.height),
                       World.from_map(m, AssetCache(a.install)), load_dot_colors(as_fs(a.install)))
    write_png(a.dest, rgb)
    print("%s: %d x %d cells -> %s (%dx%d)" % (m.name, m.width, m.height, a.dest, rgb.shape[1], rgb.shape[0]))
    return 0


def _setup(a):
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.view import Camera, DrawOptions, TerrainView
    from engine.ui import DebugFlags
    assets = AssetCache(a.install)
    world = World.from_map(open_map(a.map, a.install), assets)
    tv = TerrainView(world, assets.tileset())
    w, h = a.size
    opts = DrawOptions(shadows=not a.no_shadows, lit=not a.no_light,
                       smoothing=not a.no_smoothing, objects=not a.no_objects)
    return world, tv, Camera(w, h, world.width, world.height, a.x, a.y), assets, opts, DebugFlags.parse(a.debug)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("map")
    r.add_argument("--x", type=int, default=256)
    r.add_argument("--y", type=int, default=256)
    r.add_argument("--speed", type=int, default=4, choices=range(9))
    r.add_argument("--size", type=_size, default=(1024, 768))
    r.add_argument("--install")
    s = sub.add_parser("screenshot")
    s.add_argument("map")
    s.add_argument("x", type=int)
    s.add_argument("y", type=int)
    s.add_argument("dest")
    s.add_argument("--tick", type=int, default=0)
    s.add_argument("--size", type=_size, default=(1024, 768))
    s.add_argument("--install")
    for q in (r, s):
        q.add_argument("--no-shadows", action="store_true")
        q.add_argument("--no-light", action="store_true")
        q.add_argument("--no-smoothing", action="store_true")
        q.add_argument("--no-objects", action="store_true")
        q.add_argument("--debug", default="", metavar="LIST", help="passability,markers,depth")
    i = sub.add_parser("world-info")
    i.add_argument("map")
    i.add_argument("--install")
    i.add_argument("--strict", action="store_true")
    d = sub.add_parser("world-dump")
    d.add_argument("map")
    d.add_argument("dest")
    d.add_argument("--install")
    m = sub.add_parser("minimap")
    m.add_argument("map")
    m.add_argument("dest")
    m.add_argument("--install")
    m.add_argument("--units", action="store_true", help="add the unit dots")
    r.add_argument("--no-minimap", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "minimap":
        return minimap_cmd(a)
    if a.cmd == "world-info":
        return world_info(a)
    if a.cmd == "world-dump":
        return world_dump(a)
    if a.cmd == "screenshot":
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    try:
        world, tv, camera, assets, opts, debug = _setup(a)
    except ValueError as e:
        p.error(str(e))
    from engine.backend_pygame import render, window
    if a.cmd == "run":
        from allods2.common import as_fs
        from allods2.minimap import load_color_table, load_dot_colors
        from engine.view import Minimap
        mm = None if a.no_minimap else Minimap(world, load_color_table(as_fs(a.install)),
                                               load_dot_colors(as_fs(a.install)))
        window.run(world, tv, camera, a.speed, "Allods 2 - " + world.name,
                   assets=assets, options=opts, debug=debug, minimap=mm)
    else:
        rgb = render.screenshot(tv, camera, a.tick, a.dest, assets=assets, options=opts, debug=debug)
        print("%s at (%d, %d) tick %d -> %s (%dx%d)"
              % (world.name, camera.ix, camera.iy, a.tick, a.dest, rgb.shape[1], rgb.shape[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
