"""Frame cost of the renderer on campaign map 32 with fog (docs/engine/architecture.md, Renderer speed).

    python tools/bench_render.py [--map 32] [--frames 60]

Per size (640x480, 1024x768) times, in ms: a still frame (caches warm), a scrolling frame (the camera moves 3 px right and 2 px up from the hero per
frame; terrain cells enter the window, so the cell cache misses) with its worst frame, and a still frame at the densest spot (most units
in view).  Draw list, draw_frame and the terrain pre-warm (run after the frame) are timed separately; headless (SDL_VIDEODRIVER=dummy)."""

import argparse
import os
import statistics
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pygame  # noqa: E402

from engine.backend_pygame.render import Caches, draw_frame  # noqa: E402
from engine.backend_pygame.sprites import SpriteCache  # noqa: E402
from engine.backend_pygame.surfaces import SurfaceCache  # noqa: E402
from engine.session import build_game  # noqa: E402
from engine.sim import MoveUnits, Simulation  # noqa: E402
from engine.view import Camera, DrawOptions, TerrainView, build_draw_list  # noqa: E402
from engine.view.drawlist import build_terrain_items  # noqa: E402


def timed(w, tv, caches, a, cam, opts, prewarm=True):
    t0 = time.perf_counter()
    items = build_draw_list(w, cam, w.tick, a, opts)
    t1 = time.perf_counter()
    terrain = build_terrain_items(tv, cam, w.tick, items.lights)
    surf = pygame.Surface((cam.view_w, cam.view_h))
    draw_frame(surf, caches, terrain, items, cam, w)
    t2 = time.perf_counter()
    if prewarm and hasattr(caches.terrain, "prewarm"):         # what the play loop does after each frame
        caches.terrain.prewarm(cam, w.tick)
    t3 = time.perf_counter()
    return (t1 - t0) * 1000, (t2 - t1) * 1000, (t3 - t2) * 1000


def stats(rows):
    dl, dr = [r[0] for r in rows], [r[1] for r in rows]
    tot = [x + y for x, y, _ in rows]                       # the frame itself; the pre-warm runs after the flip, in the idle time
    pw = [r[2] for r in rows]
    return "list %.1f + draw %.1f = %.1f ms mean (max %.1f), pre-warm %.1f (max %.1f)" % (
        statistics.mean(dl), statistics.mean(dr), statistics.mean(tot), max(tot), statistics.mean(pw), max(pw))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default="32")
    ap.add_argument("--frames", type=int, default=60)
    ap.add_argument("--no-scene", action="store_true", help="redraw every frame in full (the reference path, scene.py off)")
    args = ap.parse_args(argv)
    w, a = build_game(args.map, seed=1, vision=True)
    pygame.display.init()
    pygame.display.set_mode((64, 64))
    opts = DrawOptions()
    hero = w.units[w.players[1].main_hero]
    for W, H in ((640, 480), (1024, 768)):
        tv = TerrainView(w, a.tileset())
        caches = Caches(SurfaceCache(tv), SpriteCache(a), scene=False if args.no_scene else None)
        cam = Camera(W, H, w.width, w.height, hero.x * 32 - W // 2, hero.y * 32 - H // 2)
        timed(w, tv, caches, a, cam, opts)
        still = [timed(w, tv, caches, a, cam, opts) for _ in range(args.frames)]
        # densest spot: the camera position (step 128 px) with the most units in view
        best, spot = -1, (cam.x, cam.y)
        for y in range(0, w.height * 32 - H, 128):
            for x in range(0, w.width * 32 - W, 128):
                n = sum(1 for u in w.units.values() if x <= u.x * 32 < x + W and y <= u.y * 32 < y + H)
                if n > best:
                    best, spot = n, (x, y)
        cam.move_to(*spot)
        timed(w, tv, caches, a, cam, opts)
        dense = [timed(w, tv, caches, a, cam, opts) for _ in range(args.frames)]
        cam.move_to(hero.x * 32 - W // 2, hero.y * 32 - H // 2)
        scroll = []
        for _ in range(args.frames * 4):
            cam.move_by(3, -2)
            scroll.append(timed(w, tv, caches, a, cam, opts))
        # the world running: one tick per 2 frames (units walk, objects and water animate), the hero walking away from the start
        sim = Simulation(w, ai=True, vision=True)
        cam.move_to(hero.x * 32 - W // 2, hero.y * 32 - H // 2)
        live_still, live_scroll = [], []
        for name, rows, move in (("still", live_still, (0, 0)), ("scroll", live_scroll, (3, -2))):
            for i in range(args.frames * 2):
                if i % 2 == 0:
                    sim.step([MoveUnits(1, (hero.id,), (max(1, min(w.width - 2, hero.x + (i // 20 % 2 * 2 - 1) * 6)), hero.y))] if i % 20 == 0 else ())
                cam.move_by(*move)
                rows.append(timed(w, tv, caches, a, cam, opts))
        print("%dx%d" % (W, H))
        print("  still        %s" % stats(still))
        print("  dense (%2d u) %s" % (best, stats(dense)))
        print("  scrolling    %s" % stats(scroll))
        print("  still, live  %s" % stats(live_still))
        print("  scroll, live %s" % stats(live_scroll))
        sc = caches.scene
        if sc:
            print("  scene memo: %d full, %d incremental (%d with nothing dirty)" % (sc.full, sc.incremental, sc.reused))
        print("  cache misses %d" % caches.terrain.misses)


if __name__ == "__main__":
    main(sys.argv[1:])
