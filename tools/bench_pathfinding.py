"""Worst-case static search time on the campaign maps (docs/engine/simulation.md 7.5).

    python tools/bench_pathfinding.py [INSTALL_DIR] [--pairs N]

Random walkable pairs 1..200 cells apart plus the unbounded flood to an unreachable cell (the worst case
for a human unit: the wave runs until the frontier is empty)."""

import argparse
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from allods2.assets import AssetCache  # noqa: E402
from allods2.cli import open_map  # noqa: E402
from allods2.common import campaign_maps, as_fs  # noqa: E402
from engine.sim.movement import path_grid  # noqa: E402
from engine.sim.pathfinding import plan_static  # noqa: E402
from engine.world import World  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("install", nargs="?")
    ap.add_argument("--pairs", type=int, default=200)
    a = ap.parse_args()
    assets = AssetCache(a.install)
    maps = campaign_maps(as_fs(a.install))
    best = (0, None)
    sizes = {}
    for spec in maps:
        m = open_map(spec, a.install)
        w = World.from_map(m, assets)
        g = path_grid(w, 1)
        free = [(x, y) for y in range(8, w.height - 8) for x in range(8, w.width - 8) if not w.blocked(x, y, 1)]
        rnd = random.Random(1)
        worst = 0
        for _ in range(a.pairs):
            s, t = rnd.choice(free), rnd.choice(free)
            t0 = time.perf_counter()
            r = plan_static(g, s, t, human=True)
            dt = time.perf_counter() - t0
            if dt > worst:
                worst, case = dt, (s, t, len(r.searched), r.found)
        sizes[spec] = (w.width, worst, case)
        if worst > best[0]:
            best = (worst, (spec, case))
    biggest = max(sizes, key=lambda k: sizes[k][0])
    for spec, (width, worst, case) in sorted(sizes.items(), key=lambda kv: -kv[1][1])[:5]:
        print("%-10s %3d x %-3d worst %.1f ms  %s" % (spec, width, width, worst * 1000, case))
    print("largest map %s (%d cells wide)" % (biggest, sizes[biggest][0]))
    print("worst overall %.1f ms %s" % (best[0] * 1000, best[1]))


if __name__ == "__main__":
    main()
