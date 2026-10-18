"""Orders on the campaign maps (H3 close-out; game files, skipped without the install).

Every unit of a map (all players: the command intake accepts any player) is ordered in seeded random groups to a
seeded random cell of its own connected region, first with the formation option Off, then (a second batch of orders
on the first batch's end state) On.  After the run each ordered unit must be in one of the documented end states,
no unit may sit mid-step without progress, and the world's indexes must stay consistent (`World.check_consistency`
every 32 ticks, plus an independent recomputation of the live-layer stamps).

End states (docs/engine/simulation.md sections 7.1, 7.3, 7.4, 8.3):
  goal      the unit stands on its (clamped) destination;
  fallback  it stands on the end of a static plan that fell back to the first ring around an unreachable target
            (human player: the cheapest labelled cell of the first ring, checked against an independent flood);
  limit     the static plan found nothing: a computer player's search (the human's too, to a blocked target) is cut
            at dist + min(5, dist / 4) levels, a sized unit's footprint may not fit; the unit stops on its own cell (7.1, 7.6 item 4);
  blocked   a hop plan towards the (free-at-plan-time) target came out empty because another unit stands on it:
            the failure stops the order (8.3 "Failure") within a few cells of the target;
  parked    order 1 kept but nothing drives the unit: the blocked-target rule of the group pass (goal not free and
            within one cell, 8.3) or a blocker wait next to the unit it waits for (7.4 item 5).

Default run: 4 maps (the largest, 110, and 53, 10 and 32).  All 46 maps: `ALLODS2_ALL_MAPS=1 pytest
tests/test_engine_orders_maps.py` (about 30 minutes, one process)."""

import os
import random
from collections import Counter, deque

import numpy as np
import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from allods2.common import campaign_maps
from engine.sim import MoveUnits, SetFormation, Simulation
from engine.sim.movement import CENTRE, live_cells, path_grid, unit_size
from engine.sim.orders import _target_free
from engine.sim.pathfinding import chebyshev
from engine.world import World

from helpers import GFS

MAPS = campaign_maps(GFS) if GFS else []
pytestmark = pytest.mark.skipif(not MAPS, reason="game files not present")
ALL = bool(os.environ.get("ALLODS2_ALL_MAPS"))
DEFAULT = ("10.alm", "32.alm", "53.alm", "110.alm")
WINDOW = 64                     # ticks between progress samples (4 s at the default speed)
MAX_TICKS = 3000 if ALL else 2000   # per batch; settled maps stop earlier
MAX_DIST = 80 if ALL else 30        # slow monsters need 32 ticks per cell: far targets would need > 3000 ticks
MAX_UNITS = None if ALL else 30     # default run: a seeded sample of the units per batch (a whole 250-unit map jams)
STATIC_ISNT_NEEDED = 5          # a failure happens in the final hop: at most this many static cells are left


def _params():
    out = []
    for spec in MAPS:
        short = spec.rsplit("/", 1)[-1]
        mark = [] if (ALL or short in DEFAULT) else [pytest.mark.skipif(True, reason="set ALLODS2_ALL_MAPS=1")]
        out.append(pytest.param(spec, id=short, marks=mark))
    return out


def component(w, mt, start):
    """8-connected region of free cells (static layer, the mover's mask) around `start`; no corner rule."""
    g = path_grid(w, mt)
    seen, q = {start}, deque([start])
    while q:
        x, y = q.popleft()
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                c = (x + dx, y + dy)
                if c not in seen and not g.is_blocked(*c):
                    seen.add(c)
                    q.append(c)
    return seen


def make_orders(w, rnd, max_units=None):
    """Seeded groups of 1..5 same-owner, same-movement-class units, each to a random cell of the leader's region
    (inside the 8-cell border, 4..MAX_DIST cells from the leader).  `max_units`: order only a seeded sample.  Returns (commands, ordered ids)."""
    alive = [u for u in w.units.values() if u.hp > 0]
    if max_units is not None and len(alive) > max_units:
        alive = rnd.sample(alive, max_units)
    by = {}
    for u in alive:
        by.setdefault((u.owner, u.move_type), []).append(u)
    cmds, ordered = [], set()
    for key in sorted(by):
        us = by[key]
        rnd.shuffle(us)
        while us:
            n = rnd.randint(1, 5)
            grp, us = us[:n], us[n:]
            comp = component(w, key[1], (grp[0].x, grp[0].y))
            cand = sorted(c for c in comp if 8 <= c[0] <= w.width - 9 and 8 <= c[1] <= w.height - 9
                          and 4 <= chebyshev(c, (grp[0].x, grp[0].y)) <= MAX_DIST)
            if cand:
                cmds.append(MoveUnits(key[0], tuple(u.id for u in grp), rnd.choice(cand)))
                ordered.update(u.id for u in grp)
    return cmds, ordered


def active(u):
    """A unit the move driver works on: order 1, not parked, not in the blocker-wait turn."""
    return u.order == 1 and not u.mover.parked and not u.mover.waiting


def spinning(w, u):
    """The documented spin (simulation 8.3): the unit stands at a centre with order 1 and its hop plan comes out
    empty every tick, so it never steps.  Justified independently of the planner: (a) all 8 neighbours blocked in
    the live layer (static block, other units' stamps) = boxed in, or (b) the last hop plan was empty and a flood
    of the live layer from the unit, run `limit + 2` levels, labels no cell nearer (Chebyshev) to the hop's goal than
    the unit's own cell, which has the smallest label (0) in the first ring the fallback scan finds (rings 1..7,
    7.1), or none within 7 at all.  A crowd that blocks its own corridor (a column of
    units on a one-wide road) resolves only by a new order."""
    m = u.mover
    if m.step_ticks or (u.sub_x, u.sub_y) != (CENTRE, CENTRE):
        return False
    g, live = path_grid(w, u.move_type), live_cells(w, u)

    def blocked(c):
        return g.is_blocked(*c) or c in live
    here = (u.x, u.y)
    if all(blocked((u.x + dx, u.y + dy)) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy):
        return True
    r = m.last_hop
    if r is None or r.cells or m.last_hop_goal is None:
        return False
    n = unit_size(u)

    def free(c):                                    # a sized unit enters a cell with its footprint's top-left there
        return not any(blocked((c[0] + i, c[1] + j)) for j in range(n) for i in range(n))
    seen, front = {here}, [here]
    for _ in range(r.limit + 2):
        nxt = []
        for x, y in front:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    c = (x + dx, y + dy)
                    if c not in seen and free(c):
                        seen.add(c)
                        nxt.append(c)
        front = nxt
    near = min(chebyshev(c, m.last_hop_goal) for c in seen)       # the fallback ring scan sees the start cell too
    return near == chebyshev(here, m.last_hop_goal) or near > 7


class Watch:
    """Movement system with a probe: right after a unit's own tick (the state its hop plan saw, apart from units
    later in the list), a unit that is idle at a centre with an empty hop plan is checked every 16 ticks with
    `spinning`.  `spin[id]` = tick of the last justified spin; an unjustified one goes to `bad`."""

    def __init__(self, ordered):
        self.ordered, self.spin, self.bad = ordered, {}, []

    def __call__(self, world, commands):
        from engine.sim.movement import FollowPath, _tick_unit, apply_follow_path
        for cmd in commands:
            if isinstance(cmd, FollowPath):
                apply_follow_path(world, cmd)
        for u in list(world.units.values()):
            _tick_unit(world, u)
            m = u.mover
            if (u.id in self.ordered and (world.tick & 15) == 0 and active(u) and not m.step_ticks
                    and m.last_hop is not None and not m.last_hop.cells and m.since_hop == 0):
                if spinning(world, u):
                    self.spin[u.id] = world.tick
                else:
                    self.bad.append((world.tick, hex(u.id), (u.x, u.y), m.last_hop_goal))

    def spinning(self, world, u):
        return world.tick - self.spin.get(u.id, -999) <= 40


def key_of(u):
    m = u.mover
    return (u.x, u.y, u.sub_x, u.sub_y, u.facing, u.odometer, u.order, m.parked, m.waiting, m.step_ticks)


def stamps_independent(w, u):
    """The live layer as seen by `u`, recomputed from the rule (7.3): every other unit (dying ones too) of a class whose stamp
    the mover's mask contains, footprint at its cell, its step target and its step origin."""
    mask = {1: 0x41, 2: 0x44, 3: 0x82}.get(u.move_type, 0x41)
    out = set()
    for o in w.units.values():
        if o is u or not ((0x80 if o.move_type == 3 else 0x40) & mask):
            continue
        n = max(1, int(getattr(o.stats, "token_size", 1) or 1)) if o.stats is not None else 1
        cells = [(o.x, o.y)] + [tuple(c) for c in (o.mover.step_target, o.mover.step_from) if c]
        out.update((cx + i, cy + j) for cx, cy in cells for j in range(n) for i in range(n))
    return out


def run_batch(w, sim, watch, ordered, label, report, cap=MAX_TICKS):
    """Step until every ordered unit is stopped or parked for two group-pass periods, or `cap` ticks; checks the
    invariants on the way.  Returns True when everything settled, False at the cap (a crowd still queueing through a chokepoint)."""
    prev, quiet = {}, 0
    walking = {u.id for u in w.units.values() if u.id in ordered}
    fails = report.setdefault("fails", {})
    for n in range(1, cap + 1):
        sim.step()
        for i in list(walking):
            u = w.units[i]
            if u.order != 1:
                walking.discard(i)
                m = u.mover
                if (u.x, u.y) != m.goal and not (u.x, u.y) == m.tail:      # not an arrival: the failure stop
                    fails[i] = {"tick": w.tick, "cell": (u.x, u.y), "tail": m.tail,
                                "tail_free": _target_free(w, u, m.tail) if m.tail else None,
                                "hop_empty": m.last_hop is not None and not m.last_hop.cells,
                                "static_left": len(m.static_path)}
        if n % 32 == 0:
            bad = w.check_consistency()
            assert not bad, "%s tick %d: %s" % (label, n, bad[:3])
        if n % WINDOW == 0:
            cur = {u.id: key_of(u) for u in w.units.values() if active(u) and u.id in ordered}
            stuck = [i for i, k in cur.items() if prev.get(i) == k and not watch.spinning(w, w.units[i])]
            assert not stuck, "%s: no progress in %d ticks: %s" % (label, WINDOW, [(hex(i), w.units[i].mover.goal, (w.units[i].x, w.units[i].y)) for i in stuck[:5]])
            prev = cur
            moving = [u for u in w.units.values() if (active(u) and not watch.spinning(w, u)) or u.mover.step_ticks]
            quiet = quiet + 1 if not moving else 0
            if quiet >= 2:
                return True
    return False


def classify(w, u, human_ids, report, watch, settled):
    m, cell = u.mover, (u.x, u.y)
    if u.order == 1:
        if not (m.parked or m.waiting):
            if watch.spinning(w, u):
                return "gridlock"
            return "queueing" if not settled else "WALKING AFTER SETTLE"
        if m.goal is not None and chebyshev(cell, m.goal) < 2 and not _target_free(w, u, m.goal):
            return "parked"                                     # blocked-target rule (8.3)
        if any(chebyshev((o.x, o.y), cell) <= 1 for o in w.units.values() if o is not u and o.hp > 0):
            return "parked"                                     # blocker wait (7.4 item 5)
        return "PARKED ALONE"
    assert u.order == 0xC and u.stopped, (hex(u.id), u.order)
    if cell == m.goal:
        return "goal"
    r = m.last_plan
    if cell == m.tail and r is not None and r.reason in ("fallback", "unreachable") and r.end == cell:
        if u.owner in human_ids and unit_size(u) == 1:
            ring = chebyshev(cell, m.goal)
            reach = component(w, u.move_type, cell)
            closer = [c for c in reach if chebyshev(c, m.goal) < ring]
            if closer:
                return "FALLBACK NOT FIRST RING"
        return "fallback"
    if r is not None and r.reason == "unreachable" and cell == m.tail and r.end is None:
        free_target = not path_grid(w, u.move_type).is_blocked(*m.goal)      # the human's search is unbounded only to a free target
        return "limit" if (u.owner not in human_ids or unit_size(u) > 1 or not free_target) else "LIMIT FOR HUMAN"
    f = report["fails"].get(u.id)
    if f is not None and f["hop_empty"] and f["static_left"] <= STATIC_ISNT_NEEDED and f["cell"] == cell:
        return "blocked" if not f["tail_free"] else "boxed in"
    return "STOPPED ELSEWHERE"


def check_batch(w, watch, ordered, label, report, settled):
    human = {pid for pid, p in w.players.items() if p.human}
    kinds = Counter()
    bad = []
    for i in sorted(ordered):
        u = w.units[i]
        k = classify(w, u, human, report, watch, settled)
        kinds[k] += 1
        if k.isupper():
            bad.append((k, hex(i), u.owner, u.move_type, (u.x, u.y), u.mover.goal, u.mover.tail, u.order))
    report[label] = kinds
    report["fails"] = {}
    assert not bad, "%s: %d units in no documented end state: %s" % (label, len(bad), bad[:5])
    # live layer: every unit's view equals the independent recomputation
    for u in list(w.units.values())[:: max(1, len(w.units) // 12)]:
        assert live_cells(w, u) == stamps_independent(w, u), hex(u.id)


@pytest.mark.parametrize("spec", _params())
def test_every_unit_ordered_ends_in_a_documented_state(spec):
    w = World.from_map(open_map(spec, GFS), AssetCache(GFS))
    assert not w.check_consistency()
    sim, report = Simulation(w), {}
    watch = Watch(set())
    sim.systems[-1] = watch
    rnd = random.Random(sum(map(ord, spec)))
    cmds, ordered = make_orders(w, rnd, MAX_UNITS)
    watch.ordered = ordered
    sim.step([SetFormation(p, 0) for p in w.players] + cmds)
    settled = run_batch(w, sim, watch, ordered, "formation off", report)
    check_batch(w, watch, ordered, "formation off", report, settled)
    # second batch from the end state, formation On (rigid shapes: members may target blocked cells -> fallbacks)
    cmds, ordered = make_orders(w, rnd, MAX_UNITS)
    watch.ordered = ordered
    sim.step([SetFormation(p, 2) for p in w.players] + cmds)
    settled = run_batch(w, sim, watch, ordered, "formation on", report)
    check_batch(w, watch, ordered, "formation on", report, settled)
    assert not w.check_consistency()
    print(spec, {k: dict(v) for k, v in report.items() if k != "fails"})


# --- World.check_consistency, synthetic --------------------------------------------------------------------

def test_check_consistency_detects_broken_indexes_and_steps():
    from engine.world import OrderGroup, Player, Unit, UNIT_ID_BASE
    w = World(np.zeros((16, 16), np.uint16), np.zeros((16, 16), np.int8), "syn")
    w.players[1] = Player(1, 0, human=True)
    a = Unit(UNIT_ID_BASE + 1, 1, 1, 5, 5, uid=1, hp=5, hp_max=5)
    b = Unit(UNIT_ID_BASE + 2, 1, 1, 6, 5, uid=2, hp=5, hp_max=5)
    w.add_unit(a)
    w.add_unit(b)
    assert w.check_consistency() == []
    a.x = 9                                                     # moved without the index
    assert any("index" in p for p in w.check_consistency())
    a.x = 5
    a.mover.step_ticks = 10                                     # a step without a reservation
    assert any("step_target" in p for p in w.check_consistency())
    a.mover.step_target, a.mover.step_from = (7, 5), (5, 5)     # not adjacent
    assert any("not one cell" in p for p in w.check_consistency())
    a.mover.step_target = (6, 5)
    assert w.check_consistency() == []
    a.mover.step_from = (7, 5)                                  # unit on neither end
    assert any("neither end" in p for p in w.check_consistency())
    a.mover.step_from = (5, 5)
    a.order_group = 3                                           # names a group that does not exist
    assert any("group 3" in p for p in w.check_consistency())
    w.groups[3] = OrderGroup(3, 1, [a.id, b.id])
    assert any("names group 0" in p for p in w.check_consistency())
    b.order_group = 3
    assert w.check_consistency() == []
    w.players[1].selection = (0xdead,)
    assert any("selects missing" in p for p in w.check_consistency())
    w.players[1].selection = ()
    b.sub_x = 300
    assert any("sub-cell" in p for p in w.check_consistency())
