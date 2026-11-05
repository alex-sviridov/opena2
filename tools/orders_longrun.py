"""Long runs of the 46-map orders test's batches that end at the tick cap (docs/engine/simulation.md 8.7 "Unsettled crowds").

Replays the batches of `tests/test_engine_orders_maps.py` with `ALLODS2_ALL_MAPS=1` settings (same seeds, same orders, cap 3000
ticks).  When a batch ends at the cap with units still walking (`queueing`), a copy of the world runs on to `--factor` x the cap and
every unit that was not settled at the cap is classified:

  resolved:<state>  it reached a documented end state (goal, fallback, limit, blocked, boxed in, parked) during the extension;
  progressing       still walking at the end, and nearer to its goal in the last third of the extension than ever before;
  gridlock          the documented spin (`spinning`: order 1, empty hop plan every tick) at the end;
  parked            order 1, parked or waiting next to its blocker at the end;
  cycling, hop goal held
                    still walking without getting nearer, and every hop plan of the extension either found its hop goal or fell back
                    because the goal was out of the wave's reach over the live layer (`HopProbe`, independent flood): the static plan
                    ignores units, so it keeps aiming through the jam, and the ring fallback (7.1) walks the unit to and fro;
                    `route_free` tells whether some other route to the plan's end exists (the exe never looks for it);
  cycling, unjustified fallback
                    a fallback although the flood reaches the hop goal: not explained by the documented rules (to investigate).

The test itself continues from the original world (not the copy), so its later batches are those of the test.  Usage:
`.venv/bin/python tools/orders_longrun.py [MAP ...] [--factor 3] [--json OUT]` (MAP = `10.alm` etc.; default all 46)."""

import argparse
import json
import os
import random
import sys
from collections import Counter

os.environ["ALLODS2_ALL_MAPS"] = "1"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))

import test_engine_orders_maps as T                     # noqa: E402  (the test's batch machinery)
from allods2.assets import AssetCache                   # noqa: E402
from allods2.cli import open_map                        # noqa: E402
from engine.sim import SetFormation, Simulation         # noqa: E402
from engine.sim.pathfinding import chebyshev            # noqa: E402
from engine.world import World                          # noqa: E402


def route_free(w, u):
    """True when the end of the unit's static plan (`mover.tail`) is reachable over the live layer as the unit sees it (static block and
    the other units' stamps; 8-connected, the unit's footprint, no corner rule): then nothing but its own planning keeps it from walking
    there.  False: every route is held by other units (a jam)."""
    from collections import deque
    from engine.sim.movement import live_cells, path_grid
    g, live, n = path_grid(w, u.move_type), live_cells(w, u), T.unit_size(u)
    tail = tuple(u.mover.tail) if u.mover.tail else None
    if tail is None:
        return False

    def ok(c):
        return all(not g.is_blocked(c[0] + i, c[1] + j) and (c[0] + i, c[1] + j) not in live for j in range(n) for i in range(n))
    start = (u.x, u.y)
    seen, q = {start}, deque([start])
    while q:
        c = q.popleft()
        if c == tail:
            return True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                d = (c[0] + dx, c[1] + dy)
                if d not in seen and 0 <= d[0] < w.width and 0 <= d[1] < w.height and ok(d):
                    seen.add(d)
                    q.append(d)
    return False


class HopProbe:
    """Every hop plan of a watched unit (right after its own tick, the layer its plan saw): `found` (a hop to its goal), `held` (fallback or
    unreachable, and an independent flood of the live layer from the unit over as many levels as the wave, `FUN_0054d76e`: `limit` rounded
    up to even, does not reach the hop goal: the exe's rules leave only the ring fallback), `unjustified` (fallback although the flood
    reaches the goal)."""

    def __init__(self, ids):
        self.ids, self.stats = set(ids), {i: Counter() for i in ids}

    def before(self, u):
        self.hop = id(u.mover.last_hop)

    def after(self, w, u):
        m = u.mover
        if u.id not in self.ids or m.last_hop is None or id(m.last_hop) == self.hop:
            return
        r = m.last_hop
        if r.reason == "found":
            self.stats[u.id]["found"] += 1
            return
        self.stats[u.id]["held" if not reach(w, u, m.last_hop_goal, r.limit + (r.limit & 1)) else "unjustified"] += 1


def reach(w, u, goal, levels):
    """True when a BFS of `levels` rings over the cells free for `u`'s footprint (static block, other units' stamps) reaches `goal`."""
    from engine.sim.movement import live_cells, path_grid
    if goal is None:
        return False
    g, live, n = path_grid(w, u.move_type), live_cells(w, u), T.unit_size(u)

    def ok(c):
        return all(not g.is_blocked(c[0] + i, c[1] + j) and (c[0] + i, c[1] + j) not in live for j in range(n) for i in range(n))
    here, goal = (u.x, u.y), tuple(goal)
    seen, front = {here}, [here]
    for _ in range(levels):
        nxt = []
        for x, y in front:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    c = (x + dx, y + dy)
                    if c not in seen and ok(c):
                        if c == goal:
                            return True
                        seen.add(c)
                        nxt.append(c)
        front = nxt
    return False


def classify_long(w, sim, watch, ids, cap, factor):
    """Run the copy on for (factor - 1) * cap ticks; classify the units of `ids`."""
    extra = (factor - 1) * cap
    probe = HopProbe(ids)
    watch.probes.append(probe)
    hist = {i: [] for i in ids}
    report = {}
    settled_at = None
    prev, quiet = {}, 0
    for n in range(1, extra + 1):
        sim.step()
        if n % 32 == 0:
            for i in ids:
                u = w.units.get(i)
                if u is not None:
                    hist[i].append((n, (u.x, u.y), chebyshev((u.x, u.y), u.mover.goal) if u.mover.goal else 0, u.odometer))
        if n % T.WINDOW == 0:
            moving = [u for u in w.units.values() if (T.active(u) and not watch.spinning(w, u)) or u.mover.step_ticks]
            quiet = quiet + 1 if not moving else 0
            if quiet >= 2:
                settled_at = n
                break
    human = {pid for pid, p in w.players.items() if p.human}
    out = {}
    for i in ids:
        u = w.units.get(i)
        if u is None:
            out[i] = ("gone", None)
            continue
        k = T.classify(w, u, human, report, watch, settled_at is not None)
        h = hist[i]
        if k == "queueing":
            ds = [d for _, _, d, _ in h]
            cut = len(ds) * 2 // 3
            progressing = bool(ds) and cut and min(ds[cut:]) < min(ds[:cut])
            free = route_free(w, u)
            hs = probe.stats[i]
            if progressing:
                k2 = "progressing"
            elif hs["unjustified"]:
                k2 = "cycling, unjustified fallback"
            else:
                k2 = "cycling, hop goal held"                   # every fallback of the extension had its hop goal out of reach
            out[i] = (k2, {"cell": (u.x, u.y), "goal": u.mover.goal, "tail": u.mover.tail, "dist_cap": ds[0] if ds else None,
                           "dist_end": ds[-1] if ds else None, "cells_late": len({c for _, c, _, _ in h[len(h) // 3:]}),
                           "owner": u.owner, "size": T.unit_size(u), "move_type": u.move_type, "route_free": free, "hops": dict(hs)})
        elif k in ("gridlock", "parked"):
            out[i] = (k, None)
        else:
            out[i] = ("resolved:" + k, None)
    return out, settled_at


def _batches(spec, assets):
    """The test's run as a generator: yields (label, world, sim, watch, ordered, settled, kinds) after each batch."""
    w = World.from_map(open_map(spec, T.GFS), assets)
    sim = Simulation(w)
    watch = T.Watch(set())
    sim.systems[-1] = watch
    rnd = random.Random(sum(map(ord, spec)))
    for label, form in (("formation off", 0), ("formation on", 2)):
        cmds, ordered = T.make_orders(w, rnd, None)
        watch.ordered = ordered
        sim.step([SetFormation(p, form) for p in w.players] + cmds)
        settled = T.run_batch(w, sim, watch, ordered, label, {})
        human = {pid for pid, p in w.players.items() if p.human}
        kinds = {i: T.classify(w, w.units[i], human, {}, watch, settled) for i in sorted(ordered)}
        yield label, w, sim, watch, ordered, settled, kinds
        watch.fails = {}


def run_map(spec, assets, factor):
    """The world cannot be deep-copied (asset handles), so a capped batch is extended in a fresh replay of the run (deterministic)."""
    res = {}
    for k, (label, w, sim, watch, ordered, settled, kinds) in enumerate(_batches(spec, assets)):
        entry = {"end": dict(Counter(kinds.values()))}
        if not settled:
            unsettled = [i for i, c in kinds.items() if c in ("queueing", "gridlock", "parked")]
            for j, (_, w2, sim2, watch2, _, _, kinds2) in enumerate(_batches(spec, assets)):
                if j == k:
                    assert kinds2 == kinds, "the replay differs"
                    watch2.fails = {}
                    cls, settled_at = classify_long(w2, sim2, watch2, unsettled, T.MAX_TICKS, factor)
                    break
            entry["unsettled_at_cap"] = dict(Counter(kinds[i] for i in unsettled))
            entry["long"] = dict(Counter(c for c, _ in cls.values()))
            entry["settled_after"] = settled_at
            entry["detail"] = {hex(i): d for i, (c, d) in cls.items() if d is not None}
        res[label] = entry
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("maps", nargs="*")
    ap.add_argument("--factor", type=int, default=3)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    if T.GFS is None:
        sys.exit("game files not present")
    assets = AssetCache(T.GFS)
    specs = [s for s in T.MAPS if not a.maps or s.rsplit("/", 1)[-1] in a.maps]
    out = {}
    for spec in specs:
        r = run_map(spec, assets, a.factor)
        out[spec] = r
        brief = {k: {kk: v[kk] for kk in ("end", "unsettled_at_cap", "long", "settled_after") if kk in v} for k, v in r.items()}
        print(spec, json.dumps(brief), flush=True)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(out, f, indent=1, default=str)


if __name__ == "__main__":
    main()
