"""Orders on the campaign maps (H3 close-out; game files, skipped without the install).

Every unit of a map (all players: the command intake accepts any player) is ordered in seeded random groups to a
seeded random cell of its own connected region, first with the formation option Off, then (a second batch of orders
on the first batch's end state) On.  After the run each ordered unit must be in one of the documented end states,
no unit may sit mid-step without progress, and the world's indexes must stay consistent (`World.check_consistency`
every 32 ticks, plus an independent model of the stamp and occupant slots: `StampModel`, and the calls of `FUN_0055be86` the exe
must make, derived from what each unit did: `RequiredCalls`).  Also here: mutation tests of `RequiredCalls` (synthetic) and a first-come
contest scenario on map 10 (`test_head_on_groups_contest_cells_first_come`).  Batches that end at the cap: `tools/orders_longrun.py`.

End states (docs/engine/simulation.md sections 7.1, 7.3, 7.4, 8.3):
  goal      the unit stands on its (clamped) destination;
  fallback  it stands on the end of a static plan that fell back to the first ring around an unreachable target
            (human player: the cheapest labelled cell of the first ring, checked against an independent flood);
  limit     the static plan found nothing: a computer player's search (the human's too, to a blocked target) is cut
            at dist + min(5, dist / 4) levels, a sized unit's footprint may not fit; the unit stops on its own cell (7.1, 7.6 item 4);
  blocked   a hop plan towards the (free-at-plan-time) target came out empty because another unit stands on it:
            the failure stops the order (8.3 "Failure") within a few cells of the target.  The failure can happen in the
            very tick that sets Brain mode 1 (the order, or a group-pass restart, `FUN_00573198`, followed by the creature
            tick's empty final hop, `FUN_0054d76e`, and `FUN_0056dc24`), so `Watch` records it around each unit's own tick;
  parked    order 1 kept but nothing drives the unit: the blocked-target rule of the group pass (goal not free and
            within one cell, 8.3) or a blocker wait next to the unit it waits for (7.4 item 5);
  gridlock  a spin (`spinning`): order 1, the hop plan empty every tick; it can last for good, as the static re-plan after
            more than 16 hops (`FUN_00555411`) restores the static list the hop pops eat;
  queueing  a batch that hit the tick cap with units still moving (a crowd churning through a chokepoint).

Default run: 4 maps (the largest, 110, and 53, 10 and 32).  All 46 maps: `ALLODS2_ALL_MAPS=1 pytest
tests/test_engine_orders_maps.py` (about 6 minutes with the native planner, 38 with `ALLODS2_NATIVE=0`; one process)."""

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
    """A unit the move driver works on: Brain mode 1 (order 1, or order 0xc after a failure that the group pass restarted),
    not parked, not in the blocker-wait turn."""
    return u.mode_go and not u.mover.parked and not u.mover.waiting


def spinning(w, u):
    """The documented spin (simulation 8.3): the unit stands at a centre with order 1 and its hop plan comes out
    empty every tick, so it never steps.  Justified independently of the planner: (a) all 8 neighbours blocked in
    the live layer (static block, other units' stamps) = boxed in, or (b) the last hop plan was empty and a flood
    of the live layer from the unit, run as many levels as the wave (`FUN_0054d76e`, 7.1: two half steps per loop while
    `it < limit`, so `limit` rounded up to even), labels no cell nearer (Chebyshev) to the hop's goal than
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
    for _ in range(r.limit + (r.limit & 1)):
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
    `spinning`.  `spin[id]` = tick of the last justified spin; an unjustified one goes to `bad`.  `fails[id]`: the
    failures (Brain mode 1 ended without `brain+0x50`: `FUN_0056dc24` under order 1, mode 0 under order 0xc) seen
    across the unit's own tick, which also catches a failure in the tick that set mode 1 (the pass restarts a failed
    unit 16 ticks later and a failing retry lands here again)."""

    def __init__(self, ordered, required=None, probes=()):
        self.ordered, self.spin, self.bad, self.fails, self.required = ordered, {}, [], {}, required
        self.probes = ([required] if required is not None else []) + list(probes)

    def __call__(self, world, commands):
        from engine.sim.movement import FollowPath, _tick_unit, apply_follow_path
        for cmd in commands:
            if isinstance(cmd, FollowPath):
                apply_follow_path(world, cmd)
        for u in list(world.units.values()):
            was = u.mode_go
            for p in self.probes:
                p.before(u)
            _tick_unit(world, u)
            if u.id in world.units:
                for p in self.probes:
                    p.after(world, u)
            m = u.mover
            if was and not u.mode_go and not u.stopped and u.id in self.ordered and (u.x, u.y) not in (m.goal, m.tail):
                self.fails[u.id] = {"tick": world.tick, "cell": (u.x, u.y), "tail": m.tail,
                                    "tail_free": _target_free(world, u, m.tail) if m.tail else None,
                                    "hop_empty": m.last_hop is not None and not m.last_hop.cells,
                                    "static_left": len(m.static_path)}
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
    return (u.x, u.y, u.sub_x, u.sub_y, u.facing, u.odometer, u.order, u.mode_go, m.parked, m.waiting, m.step_ticks)


def _size(o):
    return max(1, int(getattr(o.stats, "token_size", 1) or 1)) if o.stats is not None else 1


class StampModel:
    """Independent model of the stamp slots that make the live layer (cell record rec+0x2c for the ground classes, rec+0x30
    for class 3; simulation.md 7.4 "Live layer" and "Cell record", 11.4), rebuilt from the calls of `FUN_0055be86` alone.
    The test wraps `CellSlots.be86`; after each call it applies the spec's rule to its own tables, from the call's arguments
    and the unit's cell, never reading the engine's tables:
      claim(unit, cell, mode) = the size x size footprint at the unit's cell (modes 0 and 1) and at `cell` (mode 0); mode 2
      claims nothing; a cell the unit held and does not claim now is released; a claimed cell is taken when free or already
      the unit's (first come, first served: `FUN_0055c2ce` / `FUN_0055c1fe`), so a race loser holds nothing there, and a
      cell its winner leaves is free although the loser stands on it.
    The engine supplies only the call log (who, which cell and mode, in which order).  `check` compares the tables with
    `World.slots.stamp`, every sampled unit's `live_cells` with the cells the others hold in the table its mask sees
    (0x40 ground, 0x80 flyers), and the claim of every unit with its visible state, which pins the call sites: a unit holds
    for its own cell and, mid-step, for the far end of the step (the target before the border crossing, the origin after
    it); at a centre for its own cell only, or also for the head of its dynamic list (`FUN_00555c7e` stamps the next cell at
    every call with a waypoint, before the facing test, so a unit turning towards it holds it already)."""

    required = None                     # a RequiredCalls fed by the same hook (stamp_model fixture)

    def __init__(self):
        self.held = ({}, {})            # [ground, air]: (x, y) -> unit id
        self.mine = {}                  # unit id -> cells it holds
        self.anchor = {}                # unit id -> (own cell at the call, second cell or None), None after mode 2
        self.races = []                 # refused claims (unit, holder, cell)
        self.occ = ({}, {})             # occupant slots rec+4 / rec+8: (x, y) -> unit id, from the place / lift calls
        self.lost = []                  # places that stopped at a held occupant slot (unit, holder, cell)

    def place(self, u):
        """`FUN_0055020a` (7.4 "Cell record"): the footprint at the own cell row by row (x inner); a held slot (any unit) stops the loop."""
        if u.move_type not in (1, 2, 3) and u.move_type != -1:
            return
        t, n = self.occ[self.air(u)], _size(u)
        for j in range(n):
            for i in range(n):
                c = (u.x + i, u.y + j)
                if c in t:
                    self.lost.append((u.id, t[c], c))
                    return
                t[c] = u.id

    def lift(self, u):
        """`FUN_00550697`: clears the footprint slots whoever holds them; an empty slot stops the loop."""
        if u.move_type not in (1, 2, 3) and u.move_type != -1:
            return
        t, n = self.occ[self.air(u)], _size(u)
        for j in range(n):
            for i in range(n):
                if t.pop((u.x + i, u.y + j), None) is None:
                    return

    @staticmethod
    def air(o):
        return o.move_type == 3

    def call(self, u, cell, mode):
        own = (u.x, u.y)
        second = ((cell & 255, cell >> 8) if mode == 0 else None)
        self.anchor[u.id] = None if mode == 2 else (own, second)
        n = _size(u)
        claim = set()
        if mode != 2:
            for cx, cy in [own] + ([second] if second else []):
                claim.update((cx + i, cy + j) for j in range(n) for i in range(n))
        t, old = self.held[self.air(u)], self.mine.get(u.id, set())
        for c in old - claim:
            if t.get(c) == u.id:
                del t[c]
        got = set()
        for c in claim:
            if t.get(c, u.id) == u.id:
                t[c] = u.id
                got.add(c)
            else:
                self.races.append((u.id, t[c], c))          # first come: the claim of a held cell is refused
        self.mine[u.id] = got

    def check(self, w, label, viewers=12):
        occ = [{(idx & 255, idx >> 8): h for idx, h in d.items()} for d in w.slots.occ]
        for k in (0, 1):
            diff = set(occ[k].items()) ^ set(self.occ[k].items())
            assert not diff, "%s tick %d: occupant slots (%s) differ from the model: %s" % (
                label, w.tick, ("ground", "air")[k], sorted((c, hex(h)) for c, h in diff)[:6])
        eng = [{(idx & 255, idx >> 8): h for idx, h in d.items()} for d in w.slots.stamp]
        for k in (0, 1):
            diff = set(eng[k].items()) ^ set(self.held[k].items())
            assert not diff, "%s tick %d: stamp slots (%s) differ from the model: %s" % (
                label, w.tick, ("ground", "air")[k], sorted((c, hex(h)) for c, h in diff)[:6])
        for u in list(w.units.values())[:: max(1, len(w.units) // viewers)]:
            sees = {1: 0x41, 2: 0x44, 3: 0x82}.get(u.move_type, 0x41)
            want = set()
            for k, bit in ((0, 0x40), (1, 0x80)):
                if bit & sees:
                    want.update(c for c, h in self.held[k].items() if h != u.id)
            assert live_cells(w, u) == want, "%s tick %d: live layer of %#x" % (label, w.tick, u.id)
        bad = []
        for o in w.units.values():
            m, own, a = o.mover, (o.x, o.y), self.anchor.get(o.id)
            if m.step_ticks:
                far = m.step_target if own == tuple(m.step_from) else m.step_from
                ok = a == (own, tuple(far))
            else:
                ok = a is not None and a[0] == own and (a[1] is None or (bool(o.path) and a[1] == tuple(o.path[0])))
            if not ok:
                bad.append((hex(o.id), own, (o.sub_x, o.sub_y), m.step_from, m.step_target, o.path[:1], a))
        assert not bad, "%s tick %d: stamp claims off the visible state: %s" % (label, w.tick, bad[:4])


class RequiredCalls:
    """The `FUN_0055be86` calls the exe MUST make, derived from what a unit visibly did in its own tick (and from the orders phase),
    checked against the call log.  `StampModel` replays the log, so a call the engine never makes is invisible to it as long as the
    claims stay plausible (a dropped turn stamp: the unit at a centre then holds its own cell only, which is also a valid claim); this
    check derives the calls from the events instead (docs/engine/simulation.md 7.4 "Live layer", 8.7, 11.4; CONFIRMED asm):
      R1 step start, `FUN_00555c7e` 0x555cee-0x555d15: a unit at a centre that starts a step makes mode 2, then mode 0 with the step's
         target, both before it moves;
      R2 turn tick, the same call site (before the facing test): a mode-1 walker at a centre that turns towards the head of its dynamic
         list makes mode 2, then mode 0 with that head;
      R3 border crossing, `FUN_00554fd2` 0x555127-0x555186: a stepping unit whose cell changes makes mode 2 on the old cell, then (after
         the move and the place) mode 0 with the old cell;
      R4 step end, `FUN_00555b38` 0x555bf4-0x555c0f: a step that ends makes mode 2, then mode 1, on the new cell;
      R5 hop plan, `FUN_0054d76e` dynamic mode: mode 2 (0x54dd19) and, on every exit of the wave, mode 1 (0x54e11e; all four exits
         0x54dfb0, 0x54e001, 0x54e015, 0x54e038 jump to 0x54e109), before the step of R1 / R2;
      R6 cancel, `FUN_0056d969` 0x56d9a7-0x56da01: an order change (command or group pass) of a unit at a centre whose last call was
         a mode 0 (`mover+0x80` neither 0 nor its own cell) makes mode 1.
    The cell argument is checked for mode 0 only (the engine passes 0 for modes 1 and 2, which ignore it); the position at the call
    is checked too.  The place's own mode 1 inside R3 (`FUN_0055020a`) is not required: mode 0 right after it claims the same cells,
    so dropping it changes no table (and a place that loses the occupant race skips it in the exe)."""

    def __init__(self, model):
        self.model, self.seg, self.missing, self.counts = model, None, [], Counter()

    def log(self, u, cell, mode):
        if self.seg is not None:
            self.seg.setdefault(u.id, []).append((mode, cell, (u.x, u.y)))

    # --- the unit's own tick -------------------------------------------------------------------------------
    def before(self, u):
        m = u.mover
        self.seg = {}
        self.snap = ((u.x, u.y), (u.sub_x, u.sub_y) == (CENTRE, CENTRE), m.step_ticks, u.facing, id(m.last_hop))

    def after(self, w, u):
        from engine.cellslots import pack
        from engine.sim.movement import facing_to
        cell0, centre0, stepping0, facing0, hop0 = self.snap
        m, here, req = u.mover, (u.x, u.y), []
        if m.last_hop is not None and id(m.last_hop) != hop0:
            req += [("R5", 2, None, cell0), ("R5", 1, None, cell0)]
        if stepping0:
            if here != cell0:
                req += [("R3", 2, None, cell0), ("R3", 0, pack(*cell0), here)]
            if not m.step_ticks:
                req += [("R4", 2, None, here), ("R4", 1, None, here)]
        elif centre0:
            if m.step_ticks and tuple(m.step_from) == cell0:
                req += [("R1", 2, None, cell0), ("R1", 0, pack(*m.step_target), cell0)]
            elif (u.mode_go and not m.waiting and u.path and u.facing != facing0
                    and m.target_facing == facing_to(here, tuple(u.path[0]))):
                req += [("R2", 2, None, here), ("R2", 0, pack(*u.path[0]), here)]
        self._match(w, u, req, self.seg.get(u.id, []))
        self.seg = None

    # --- the orders phase (commands, group pass) ---------------------------------------------------------
    @staticmethod
    def _orders_key(u):
        m = u.mover
        return (u.order, u.mode_go, m.goal, u.stopped, m.parked, m.waiting)

    def orders_before(self, w):
        self.seg = {}
        self.osnap = {u.id: (self._orders_key(u), (u.x, u.y), (u.sub_x, u.sub_y) == (CENTRE, CENTRE),
                             (self.model.anchor.get(u.id) or (None, None))[1]) for u in w.units.values()}

    def orders_after(self, w):
        for u in w.units.values():
            s = self.osnap.get(u.id)
            if s is None:
                continue
            key, cell, centre, second = s
            if key != self._orders_key(u) and centre and second is not None and second != cell:
                self._match(w, u, [("R6", 1, None, cell)], self.seg.get(u.id, []))
        self.seg = None

    def _match(self, w, u, req, calls):
        """`req` must be a subsequence of `calls` (a call matches on mode, the cell for mode 0, the unit's position)."""
        i = 0
        for rule, mode, cell, pos in req:
            while i < len(calls) and not (calls[i][0] == mode and (cell is None or calls[i][1] == cell) and calls[i][2] == pos):
                i += 1
            if i == len(calls):
                self.missing.append((w.tick, hex(u.id), rule, mode, cell, pos, calls[:6]))
                return
            i += 1
            self.counts[rule] += 1


def install_required(sim, req):
    """Route the orders phase of `sim` through `req` (the unit ticks go through `Watch(required=req)`)."""
    from engine.sim.orders import orders_system

    def orders(world, commands):
        req.orders_before(world)
        orders_system(world, commands)
        req.orders_after(world)
    sim.systems[sim.systems.index(orders_system)] = orders


def slots_hook(monkeypatch, model, drop=None):
    """Wrap `CellSlots.be86`: every call feeds `model` (a `StampModel`, with its `required` log).  `drop(site, u, cell, mode)` (mutation
    tests): a call for which it returns True is not made at all; `site` = the name of the calling function."""
    import sys
    from engine.cellslots import CellSlots
    orig = CellSlots.be86

    def be86(slots, u, cell, mode):
        if drop is not None and drop(sys._getframe(1).f_code.co_name, u, cell, mode):
            return
        orig(slots, u, cell, mode)
        model.call(u, cell, mode)
        if model.required is not None:
            model.required.log(u, cell, mode)
    monkeypatch.setattr(CellSlots, "be86", be86)
    place, lift = CellSlots.place, CellSlots.lift

    def place_hook(slots, u):
        model.place(u)                                  # before the call: the unit's cell at the call
        return place(slots, u)

    def lift_hook(slots, u):
        model.lift(u)
        return lift(slots, u)
    monkeypatch.setattr(CellSlots, "place", place_hook)
    monkeypatch.setattr(CellSlots, "lift", lift_hook)


@pytest.fixture
def stamp_model(monkeypatch):
    """A `StampModel` fed by every `CellSlots.be86` call (world construction included), with its `RequiredCalls` check."""
    model = StampModel()
    model.required = RequiredCalls(model)
    slots_hook(monkeypatch, model)
    return model


def run_batch(w, sim, watch, ordered, label, report, cap=MAX_TICKS, stamps=None):
    """Step until every ordered unit is stopped or parked for two group-pass periods, or `cap` ticks; checks the
    invariants on the way.  Returns True when everything settled, False at the cap (a crowd still queueing through a chokepoint)."""
    prev, quiet = {}, 0
    for n in range(1, cap + 1):
        sim.step()
        if n % 32 == 0:
            bad = w.check_consistency()
            assert not bad, "%s tick %d: %s" % (label, n, bad[:3])
            if stamps is not None:
                stamps.check(w, label)
                if stamps.required is not None:
                    miss = stamps.required.missing
                    assert not miss, "%s: %d required FUN_0055be86 calls missing: %s" % (label, len(miss), miss[:4])
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
    if u.mode_go:
        if not (m.parked or m.waiting):
            if watch.spinning(w, u):
                return "gridlock"
            return "queueing" if not settled else "WALKING AFTER SETTLE"
        if m.goal is not None and chebyshev(cell, m.goal) < 2 and not _target_free(w, u, m.goal):
            return "parked"                                     # blocked-target rule (8.3)
        if any(chebyshev((o.x, o.y), cell) <= 1 for o in w.units.values() if o is not u and o.hp > 0):
            return "parked"                                     # blocker wait (7.4 item 5)
        return "PARKED ALONE"
    assert u.order == 0xC, (hex(u.id), u.order)           # stopped (arrival, 56dbc6) or failed and waiting for the next pass
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
    f = watch.fails.get(u.id)
    if f is not None and f["hop_empty"] and f["static_left"] <= STATIC_ISNT_NEEDED and f["cell"] == cell:
        return "blocked" if not f["tail_free"] else "boxed in"
    return "STOPPED ELSEWHERE"


def check_batch(w, watch, ordered, label, report, settled, stamps):
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
    watch.fails = {}
    assert not bad, "%s: %d units in no documented end state: %s" % (label, len(bad), bad[:5])
    stamps.check(w, label)                                  # live layer: the independent slot model


@pytest.mark.parametrize("spec", _params())
def test_every_unit_ordered_ends_in_a_documented_state(spec, stamp_model):
    w = World.from_map(open_map(spec, GFS), AssetCache(GFS))
    assert not w.check_consistency()
    stamp_model.check(w, "start")
    sim, report = Simulation(w), {}
    watch = Watch(set(), stamp_model.required)
    sim.systems[-1] = watch
    install_required(sim, stamp_model.required)
    rnd = random.Random(sum(map(ord, spec)))
    cmds, ordered = make_orders(w, rnd, MAX_UNITS)
    watch.ordered = ordered
    sim.step([SetFormation(p, 0) for p in w.players] + cmds)
    settled = run_batch(w, sim, watch, ordered, "formation off", report, stamps=stamp_model)
    check_batch(w, watch, ordered, "formation off", report, settled, stamp_model)
    # second batch from the end state, formation On (rigid shapes: members may target blocked cells -> fallbacks)
    cmds, ordered = make_orders(w, rnd, MAX_UNITS)
    watch.ordered = ordered
    sim.step([SetFormation(p, 2) for p in w.players] + cmds)
    settled = run_batch(w, sim, watch, ordered, "formation on", report, stamps=stamp_model)
    check_batch(w, watch, ordered, "formation on", report, settled, stamp_model)
    assert not w.check_consistency()
    assert not stamp_model.required.missing
    print(spec, {k: dict(v) for k, v in report.items()}, "required calls:", dict(stamp_model.required.counts))


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


# --- RequiredCalls: a dropped FUN_0055be86 call is caught (mutation tests, synthetic, always run) ------------------------

def _required_run(monkeypatch, drop=None):
    """Four slow-turning walkers ordered west through a one-cell gap, re-ordered at tick 3 while they turn (R6), run with the
    `StampModel` + `RequiredCalls` checks; `drop` removes calls (see `slots_hook`).  Returns (model, stamp-model failure or None)."""
    import orders_scenarios as osc
    model = StampModel()
    model.required = RequiredCalls(model)
    slots_hook(monkeypatch, model, drop)
    w = osc.world()
    osc.wall(w, [(14, y) for y in range(8, 32) if y != 20])
    us = [osc.unit(w, i + 1, 22 + (i % 2) * 2, 18 + (i // 2) * 3) for i in range(4)]
    for u in us:
        u.mover.turn_rate = 8                           # 128 / 8 = 16 ticks for the turn west: R2 turn ticks, R6 on the re-order
    sim = Simulation(w)
    watch = Watch({u.id for u in us}, model.required)
    sim.systems[-1] = watch
    install_required(sim, model.required)
    ids = tuple(u.id for u in us)
    script = {0: [MoveUnits(1, ids, (8, 20))], 3: [MoveUnits(1, ids, (9, 21))]}
    err = None
    for _ in range(500):
        sim.step(script.get(w.tick, ()))
        if err is None and w.tick % 8 == 0:
            try:
                model.check(w, "syn")
            except AssertionError as e:
                err = str(e)
    return model, err


def test_required_calls_hold_on_the_unmutated_engine(monkeypatch):
    model, err = _required_run(monkeypatch)
    assert err is None and not model.required.missing
    assert all(model.required.counts[r] > 0 for r in ("R1", "R2", "R3", "R4", "R5", "R6")), model.required.counts


@pytest.mark.parametrize("site, mode, rule, turn_only", [
    ("_start_step", None, "R2", True),              # the pair of a turn tick (as if it came after the facing test): the slot model alone misses it
    ("_start_step", 0, "R1", False),                # the step-start stamp
    ("move_unit", 0, "R3", False),                  # the border crossing's re-stamp of the old cell
    ("_end_step", 1, "R4", False),                  # the step end's own stamp
    ("_hop_plan", 1, "R5", False),                  # the planner's own stamp before the walk back
    ("restamp_displaced", 1, "R6", False),          # the cancel's re-stamp
])
def test_required_calls_catch_a_dropped_call(monkeypatch, site, mode, rule, turn_only):
    from engine.sim.movement import facing_to

    def drop(s, u, cell, m):
        if s != site or mode not in (None, m):
            return False
        return not turn_only or u.facing != facing_to((u.x, u.y), tuple(u.path[0]))
    model, err = _required_run(monkeypatch, drop)
    rules = {x[2] for x in model.required.missing}
    assert rule in rules, (rule, rules, model.required.missing[:3])
    if turn_only:
        assert err is None, "the replayed slot model alone already sees the dropped turn stamp: %s" % err


# --- first come on a real map: two groups head-on through a chokepoint ------------------------------------------------------

class ContestProbe:
    """A contest = a unit at a hop plan (or a blocker wait) whose static head is adjacent and stamped by another unit: two units
    want one cell.  The first-come rule (7.4 "Cell record", `FUN_0055c2ce`) and the plan over the live layer decide it: the holder
    keeps the cell, the other never steps into it (it plans round, its plan comes out empty, or, human size 1, it waits for the
    holder, `FUN_0056fc69`).  `fresh`: the holder took the cell in this very tick, so the creation order decided (it is processed
    first)."""

    def __init__(self, model):
        self.model, self.log, self.start = model, [], ({}, {})

    def tick_start(self):
        self.start = tuple(dict(t) for t in self.model.held)

    def before(self, u):
        m = u.mover
        self.hop = id(m.last_hop)
        head = tuple(m.static_path[0]) if m.static_path else None
        self.head = head if head is not None and chebyshev(head, (u.x, u.y)) == 1 else None
        self.holder = self.model.held[StampModel.air(u)].get(self.head) if self.head else None

    def after(self, w, u):
        m = u.mover
        if self.holder in (None, u.id) or (id(m.last_hop) == self.hop and not (m.waiting or m.parked)):
            return
        nxt = tuple(m.step_target) if m.step_ticks else tuple(u.path[0]) if u.path else None
        fresh = self.start[StampModel.air(u)].get(self.head) != self.holder
        self.log.append({"tick": w.tick, "unit": u, "holder": w.units[self.holder], "cell": self.head, "next": nxt,
                         "wait": m.waiting or m.parked, "fresh": fresh})


CHOKE_MAP = "10.alm"            # a diagonal corridor (57, 28)-(60, 30) between two large regions (found by a flood search)


@pytest.mark.skipif(not any(s.endswith("/" + CHOKE_MAP) for s in MAPS), reason="game files not present")
@pytest.mark.parametrize("human", [False, True], ids=["computer", "human"])
def test_head_on_groups_contest_cells_first_come(monkeypatch, human):
    """Three walkers of player 3 on each side of the corridor of map 10, ordered through it towards each other (formation Off).
    Asserted: every contest is won by the holder (the other unit's next cell is never the contested one); a contest decided in one
    tick goes to the unit earlier in the creation order; no refused stamp claim and no lost occupant race (with every plan over the
    live layer no move order makes a race loser: 11.4); the computer's units never wait (they re-plan), the human's size-1 units
    do; slot models, required calls and consistency as in the map test; every unit ends in a documented state."""
    model = StampModel()
    model.required = RequiredCalls(model)
    slots_hook(monkeypatch, model)
    spec = next(s for s in MAPS if s.endswith("/" + CHOKE_MAP))
    w = World.from_map(open_map(spec, GFS), AssetCache(GFS))
    walkers = sorted((u for u in w.units.values() if u.owner == 3 and u.move_type == 1 and _size(u) == 1), key=lambda u: u.seq)
    north, south = walkers[:3], walkers[3:6]
    for u, c in zip(north, [(57, 26), (57, 25), (55, 25)]):     # a seeded draw (cells within 3 of each end) that also gives a
        w.move_unit(u.id, *c)                                   # contest decided in one tick (the creation order) at (58, 28)
    for u, c in zip(south, [(63, 32), (59, 31), (61, 33)]):
        w.move_unit(u.id, *c)
    owner = 1 if human else 3
    for u in north + south:
        u.owner = owner                                 # player 1 is the human (no units of its own on this map)
    ordered = {u.id for u in north + south}
    sim, probe = Simulation(w), ContestProbe(model)
    watch = Watch(ordered, model.required, [probe])
    sim.systems[-1] = watch
    install_required(sim, model.required)
    sim.systems.insert(0, lambda world, commands: probe.tick_start())
    sim.step([SetFormation(owner, 0), MoveUnits(owner, tuple(u.id for u in north), (62, 33)),
              MoveUnits(owner, tuple(u.id for u in south), (56, 24))])
    report = {}
    settled = run_batch(w, sim, watch, ordered, "head-on", report, cap=1500, stamps=model)
    check_batch(w, watch, ordered, "head-on", report, settled, model)
    log = probe.log
    assert log, "no contest: the scenario does not exercise first come"
    assert all(e["next"] != e["cell"] for e in log), [e for e in log if e["next"] == e["cell"]][:3]
    fresh = [e for e in log if e["fresh"]]
    assert fresh, "no contest decided within one tick"
    assert all(e["holder"].seq < e["unit"].seq for e in fresh), fresh[:3]
    waits = [e for e in log if e["wait"]]
    assert bool(waits) == human, (human, len(waits))
    assert not model.races and not model.lost, (model.races[:3], model.lost[:3])
    cells = Counter((u.x, u.y) for u in w.units.values())
    assert max(cells.values()) == 1
    print(CHOKE_MAP, "human" if human else "computer", dict(report["head-on"]), "contests", len(log), "fresh", len(fresh), "waits", len(waits))
