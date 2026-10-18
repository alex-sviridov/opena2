"""Determinism of orders (H3 close-out): a play session recorded through the UI order logic replays to the same
world hash when the tick loop is driven the way the backend does at 30 and at 60 frames per second (accumulator of
frame times against `tick_period_ms`, one `Simulation.step(queue.drain())` per period) and in one batch with
`replay()`.  A session is a list of (millisecond, input) events; the UI logic is `OrderInput` (hotkeys, left and
right release, Ctrl+F) and `SelectUnits`, exactly what `backend_pygame.window.run` feeds the queue."""

import pytest

from engine.sim import CommandQueue, SelectUnits, Simulation, replay, tick_period_ms
from engine.ui import CursorState as S
from engine.ui import OrderInput
from engine.world import UNIT_ID_BASE, Player, Unit, World

import numpy as np

from helpers import GFS

SPEED = 4
PERIOD = tick_period_ms(SPEED)


def selection_state(world, pid):
    return "own" if world.players[pid].selection else "none"


class Session:
    """Turns scripted inputs into commands with `OrderInput`, as the window loop does."""

    def __init__(self, world, pid, queue):
        self.world, self.pid, self.queue = world, pid, queue
        p = world.players[pid]
        self.oi = OrderInput(pid, 640, lambda: p.selection, lambda: selection_state(world, pid), p.formation)

    def feed(self, event):
        kind, arg = event
        if kind == "select":
            self.queue.put(SelectUnits(self.pid, arg))
        elif kind == "click":                         # left release on ground with the move cursor
            what, cmd = self.oi.release(S.MOVE, arg, False)
            assert what == "order"
            if cmd is not None:
                self.queue.put(cmd)
        elif kind == "key":
            cmd, _ = self.oi.key(arg)
            if cmd is not None:
                self.queue.put(cmd)
        elif kind == "ctrl_f":
            cmd, _ = self.oi.key("f", ctrl=True)
            self.queue.put(cmd)
        elif kind == "right_click":
            cmd = self.oi.right_release()
            if cmd is not None:
                self.queue.put(cmd)


def frame_times(fps, total_ms):
    """Integer-millisecond frame boundaries of a loop at `fps`: the backend's `dt` values."""
    t, k = 0, 0
    while t < total_ms:
        k += 1
        nxt = min(total_ms, round(k * 1000 / fps))
        yield nxt - t, nxt
        t = nxt


def drive(world, fps, total_ms, inputs=None, log=None):
    """The backend loop: per frame add dt, deliver due inputs (`inputs`: sorted (ms, event) list through a Session)
    or logged commands (`log`: (tick, command) list, put on the queue just before the step of that tick), then
    `while acc >= period: step(queue.drain())`.  Returns the Simulation."""
    sim, queue = Simulation(world), CommandQueue()
    session = Session(world, inputs[0], queue) if inputs else None
    events = list(inputs[1]) if inputs else []
    pending = sorted(log or [], key=lambda tc: tc[0])
    acc = 0
    for dt, now in frame_times(fps, total_ms):
        acc += dt
        while events and events[0][0] <= now:
            session.feed(events.pop(0)[1])
        while acc >= PERIOD:
            while pending and pending[0][0] == world.tick:
                queue.put(pending.pop(0)[1])
            sim.step(queue.drain())
            acc -= PERIOD
    return sim


# --- the scripted session ---------------------------------------------------------------------------------------

def script(ids, cell):
    """Ticks are ~62 ms: select 4, move, re-order mid-walk, formation On, new group, stop, deselect, select, move."""
    a, b = ids[:4], ids[2:7]
    x, y = cell
    return [
        (100, ("select", a)), (150, ("click", (x + 9, y + 3))),
        (1500, ("click", (x + 4, y + 11))),                         # mid-walk re-order
        (2500, ("ctrl_f", None)),                                   # formation Auto -> On
        (2600, ("select", b)), (2650, ("click", (x - 8, y + 5))),   # overlaps the first group: units change group
        (4200, ("click", (x - 2, y - 7))),                          # re-order while the formation walks
        (5200, ("key", "t")),                                       # stand ground (the selection is own)
        (5600, ("select", a)), (5650, ("click", (x + 12, y - 4))),
        (6500, ("ctrl_f", None)),                                   # On -> Off
        (6550, ("click", (x + 1, y + 1))),
        (8000, ("right_click", None)),                              # deselect
        (8200, ("select", ids[:2])), (8250, ("click", (x + 3, y + 3))),
        (9000, ("key", "t")),
    ]


TOTAL_MS = 14000


def check(make_world, pid, ids, cell):
    ev = script(ids, cell)
    rec = drive(make_world(), 30, TOTAL_MS, inputs=(pid, ev))
    n, log, want = rec.world.tick, rec.log, rec.world.dump_hash()
    assert n == TOTAL_MS // PERIOD and len(log) >= 14
    kinds = {type(c).__name__ for _, c in log}
    assert {"SelectUnits", "MoveUnits", "SetFormation", "Stop"} <= kinds
    assert any(u.order for u in rec.world.units.values())        # something actually moved
    for fps in (30, 60, 144):
        sim = drive(make_world(), fps, TOTAL_MS, log=log)
        assert sim.world.tick == n, fps
        assert sim.world.dump_hash() == want, fps
    batch = Simulation(make_world())
    replay(batch, log, n)
    assert batch.world.dump_hash() == want
    # sanity: the hash is sensitive (dropping one logged command changes it)
    short = Simulation(make_world())
    replay(short, [lc for i, lc in enumerate(log) if i != 6], n)
    assert short.world.dump_hash() != want
    # driving the UI script at 60 fps records the same session shifted by at most a tick per input; it must replay too
    rec60 = drive(make_world(), 60, TOTAL_MS, inputs=(pid, ev))
    again = Simulation(make_world())
    replay(again, rec60.log, rec60.world.tick)
    assert again.world.dump_hash() == rec60.world.dump_hash()


def synthetic_world():
    w = World(np.zeros((48, 48), np.uint16), np.zeros((48, 48), np.int8), "syn")
    w._cost = np.full((48, 48), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    w.players[2] = Player(2, 1)
    for k in range(8):
        u = Unit(UNIT_ID_BASE + k + 1, 1, 1, 12 + (k % 4) * 2, 14 + (k // 4) * 2, uid=k + 1, hp=10, hp_max=10,
                 facing=64 + 32 * (k % 3), speed_mod=24 + 3 * (k % 4))
        u.mover.turn_rate = 32
        w.add_unit(u)
    for x, y in ((20, 12), (20, 13), (20, 14), (21, 16), (21, 17)):      # a few obstacles
        w._block[y, x] = 5
    w.block_rev += 1
    return w


def test_session_replays_identically_synthetic():
    ids = tuple(UNIT_ID_BASE + k + 1 for k in range(8))
    check(synthetic_world, 1, ids, (14, 16))


@pytest.mark.skipif(not GFS, reason="game files not present")
def test_session_replays_identically_on_map_53():
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    assets = AssetCache(GFS)

    def make():
        return World.from_map(open_map("53", GFS), assets)

    w = make()
    pid = 4                                          # the intake accepts any player: use the one with most units
    mine = [u for u in w.units.values() if u.owner == pid and u.move_type == 1][:8]
    ids = tuple(u.id for u in mine)
    check(make, pid, ids, (mine[0].x, mine[0].y))
