"""Cost of a group walking: 20 units ordered at once on the largest campaign map (docs/engine/simulation.md 8.7).

    python tools/bench_orders.py [INSTALL_DIR] [--map NAME] [--units N] [--ticks N] [--frames N]

Prints ms per tick (mean / p95 / max, simulation only), how many static / hop plans ran and the slowest, then
ms per frame with rendering (SDL dummy driver, the original interface on, the backend's `window.run` loop) at
the frame rates 30 and 60: the loop's clock is replaced by one that returns the simulated frame time and records
the real time of each frame, so the accumulator steps the simulation exactly as it would at that rate (16 ticks
per second at the default speed: 0.53 / 0.27 ticks per frame).  Frames are split by whether they stepped."""

import argparse
import os
import random
import statistics
import sys
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from allods2.assets import AssetCache  # noqa: E402
from allods2.cli import open_map  # noqa: E402
from allods2.common import as_fs, campaign_maps  # noqa: E402
from engine.sim import MoveUnits, Simulation, movement  # noqa: E402
from engine.world import World  # noqa: E402


def pick_group(world, n, rnd):
    """The n nearest walkers of the most numerous owner around a random one of them, and a target ~60 cells away
    that the leader can reach (flood of the static layer)."""
    from collections import Counter, deque
    from engine.sim.pathfinding import chebyshev
    owner = Counter(u.owner for u in world.units.values() if u.move_type == 1).most_common(1)[0][0]
    mine = sorted((u for u in world.units.values() if u.owner == owner and u.move_type == 1), key=lambda u: u.id)
    lead = rnd.choice(mine)
    grp = sorted(mine, key=lambda u: chebyshev((u.x, u.y), (lead.x, lead.y)))[:n]
    g = movement.path_grid(world, 1)
    start = (lead.x, lead.y)
    seen, q = {start}, deque([start])
    while q:
        x, y = q.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c = (x + dx, y + dy)
                if c not in seen and not g.is_blocked(*c):
                    seen.add(c)
                    q.append(c)
    far = sorted(c for c in seen if 50 <= chebyshev(c, start) <= 70 and 8 <= c[0] < world.width - 8)
    return owner, grp, rnd.choice(far)


def stats(ms):
    s = sorted(ms)
    return "mean %.2f  p95 %.2f  max %.2f" % (statistics.fmean(s), s[int(0.95 * (len(s) - 1))], s[-1])


def build(install, spec, n):
    assets = AssetCache(install)
    world = World.from_map(open_map(spec, install), assets)
    owner, grp, target = pick_group(world, n, random.Random(7))
    cmd = MoveUnits(owner, tuple(u.id for u in grp), target)
    return assets, world, owner, grp, target, cmd


def bench_ticks(install, spec, n, ticks):
    assets, world, owner, grp, target, cmd = build(install, spec, n)
    plans = {"static": [], "hop": []}
    for name, key in (("plan_static", "static"), ("plan_dynamic", "hop")):
        orig = getattr(movement, name)

        def wrap(*a, _o=orig, _k=key, **kw):
            t0 = time.perf_counter()
            r = _o(*a, **kw)
            plans[_k].append((time.perf_counter() - t0) * 1000)
            return r
        setattr(movement, name, wrap)
    sim, ms = Simulation(world), []
    for i in range(ticks):
        t0 = time.perf_counter()
        sim.step([cmd] if i == 0 else ())                  # tick 0 applies the order: the first plans of all units
        ms.append((time.perf_counter() - t0) * 1000)
    print("map %s %dx%d, %d units of player %d -> %s, formation auto" % (spec, world.width, world.height, len(grp), owner, target))
    print("ms per tick (%d ticks, simulation only): %s" % (ticks, stats(ms)))
    for k, v in plans.items():
        print("  %-6s plans: %4d, mean %.2f ms, max %.1f ms" % (k, len(v), statistics.fmean(v) if v else 0, max(v) if v else 0))
    worst = sorted(range(len(ms)), key=lambda i: -ms[i])[:3]
    print("  slowest ticks: %s" % ", ".join("#%d %.1f ms" % (i, ms[i]) for i in worst))
    moving = sum(1 for u in grp if u.order == 1)
    print("  still walking at the end: %d of %d" % (moving, len(grp)))


def bench_frames(install, spec, n, fps, frames):
    import pygame
    from engine.backend_pygame import window
    from engine.sim import tick_period_ms
    from engine.ui import Layout
    from engine.view import Camera, TerrainView
    assets, world, owner, grp, target, cmd = build(install, spec, n)
    lay = Layout.for_size(640, 480)
    v = lay.viewport
    lead = grp[0]
    cam = Camera(v.w, v.h, world.width, world.height, lead.x * 32 - v.w // 2, lead.y * 32 - v.h // 2, border=256)
    rec = []                                        # (real ms of the frame, ticks stepped in it)

    class FakeClock:
        def __init__(self):
            self.last, self.k, self.tick0 = None, 0, 0

        def tick(self, _limit=0):
            now = time.perf_counter()
            if self.last is not None:
                rec.append(((now - self.last) * 1000, world.tick - self.tick0))
            self.tick0, self.last = world.tick, time.perf_counter()
            self.k += 1
            return round(self.k * 1000 / fps) - round((self.k - 1) * 1000 / fps)

    pygame.init()
    window.ensure_display(*lay.size)
    pygame.time.Clock = FakeClock
    pygame.mouse.get_focused = lambda: False        # the dummy pointer sits at (0, 0) and would edge-scroll
    sim = window.run(world, TerrainView(world, assets.tileset()), cam, lay, assets=assets, max_frames=frames,
                     player_id=owner, commands=[cmd])
    first = rec[:fps]                               # the first second fills the surface and sprite caches
    rec = rec[fps:]
    allms = [r[0] for r in rec]
    step = [r[0] for r in rec if r[1]]
    idle = [r[0] for r in rec if not r[1]]
    print("%d fps (%d frames after warm-up, %d ticks in all): frame %s" % (fps, len(rec), sim.world.tick, stats(allms)))
    if step and idle:
        print("   frames with a tick: %s\n   frames without:     %s" % (stats(step), stats(idle)))
    print("   first second (cache warm-up): %s" % stats([r[0] for r in first]))
    budget = 1000 / fps
    print("   frames over the %.1f ms budget: %d (%.1f%%)" % (budget, sum(1 for m in allms if m > budget),
                                                           100.0 * sum(1 for m in allms if m > budget) / len(allms)))
    worst = sorted(range(len(rec)), key=lambda i: -rec[i][0])[:3]
    print("   slowest frames: %s" % ", ".join("#%d %.1f ms%s" % (i, rec[i][0], " (stepped)" if rec[i][1] else "") for i in worst))
    pygame.quit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("install", nargs="?")
    ap.add_argument("--map", default=None, help="campaign map path (default: the largest)")
    ap.add_argument("--units", type=int, default=20)
    ap.add_argument("--ticks", type=int, default=600)
    ap.add_argument("--frames", type=int, default=600, help="frames at 30 fps (60 fps runs twice as many)")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args()
    spec = a.map
    if spec is None:
        biggest = (0, None)
        for s in campaign_maps(as_fs(a.install)):
            m = open_map(s, a.install)
            if m.width > biggest[0]:
                biggest = (m.width, s)
        spec = biggest[1]
    bench_ticks(a.install, spec, a.units, a.ticks)
    if not a.no_render:
        for fps in (30, 60):
            bench_frames(a.install, spec, a.units, fps, a.frames * fps // 30)


if __name__ == "__main__":
    main()
