"""python -m engine run MAP [--x PX --y PX] [--speed N] [--size WxH] [--install DIR]
   python -m engine screenshot MAP X Y DEST.png [--tick N] [--size WxH] [--install DIR]

MAP as for `python -m allods2 map` (10, scenario/10.alm, or a file).  X, Y =
the viewport's top-left in world pixels (x = 32*col, y = 32*row - height).
`run` starts at the playable-area corner (256, 256) by default.  Arrow keys
or the mouse at the window edge scroll; Esc quits.  `screenshot` writes a PNG
with no window (SDL dummy driver).  Docs: docs/engine/architecture.md.
"""

import argparse
import os
import sys


def _size(s):
    w, _, h = s.lower().partition("x")
    return int(w), int(h)


def _setup(a):
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from allods2.common import as_fs
    from engine.view import Camera, TerrainView
    from engine.world import World
    m = open_map(a.map, a.install)
    world = World.from_map(m)
    tv = TerrainView(world, AssetCache(as_fs(a.install)).tileset())
    w, h = a.size
    return world, tv, Camera(w, h, world.width, world.height, a.x, a.y)


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
    a = p.parse_args(argv)
    if a.cmd == "screenshot":
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    world, tv, camera = _setup(a)
    from engine.backend_pygame import render, window
    if a.cmd == "run":
        window.run(world, tv, camera, a.speed, "Allods 2 - " + world.name)
    else:
        rgb = render.screenshot(tv, camera, a.tick, a.dest)
        print("%s at (%d, %d) tick %d -> %s (%dx%d)"
              % (world.name, camera.ix, camera.iy, a.tick, a.dest, rgb.shape[1], rgb.shape[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
