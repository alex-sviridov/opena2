"""Movement / orders questions answered against allods2.exe (docs/engine/simulation.md "Exe answers").

Synthetic worlds always run; the data.bin rate scan skips without the install."""

import numpy as np
import pytest

from engine.sim import MoveUnits, Simulation
from engine.sim.movement import _step_or_turn, unit_speed, walk_speed
from engine.world import UNIT_ID_BASE, Player, Unit, World

from helpers import needs_data

EAST, WEST = 64, 192


def world(n=32):
    w = World(np.zeros((n, n), np.uint16), np.zeros((n, n), np.int8), "syn")
    w._cost = np.full((n, n), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    return w


def unit(w, uid, x, y, speed=24, facing=EAST, rate=16):
    u = Unit(UNIT_ID_BASE + uid, 1, 1, x, y, uid=uid, hp=10, hp_max=10, facing=facing, speed_mod=speed)
    u.mover.turn_rate = rate
    w.add_unit(u)
    return u


# --- FUN_00555c7e with an empty dynamic list: one FUN_005551ef turn tick, nothing else ---------------

def test_empty_list_runs_one_turn_tick_towards_the_target_facing():
    w = world()
    u = unit(w, 1, 10, 10, rate=16)
    u.mover.target_facing = WEST                    # 180 degrees away, e.g. left by an unfinished in-range turn
    pos = (u.x, u.y, u.sub_x, u.sub_y)
    _step_or_turn(w, u)
    assert u.facing == EAST + 16                    # 180 degrees go clockwise, one rate step
    assert (u.x, u.y, u.sub_x, u.sub_y) == pos and not u.mover.step_ticks
    for _ in range(7):
        _step_or_turn(w, u)
    assert u.facing == WEST                         # 8 ticks = ceil(128 / 16); the last one snaps (d < rate)


def test_empty_list_at_target_facing_is_a_no_op():
    w = world()
    u = unit(w, 1, 10, 10)
    u.mover.target_facing = u.facing
    _step_or_turn(w, u)
    assert u.facing == EAST and not u.mover.turning


# --- group speed byte vs effects ---------------------------------------------------------------------

def test_cancel_group_zeroes_the_group_speed_byte():
    """`FUN_00570e83` writes `group+0x44 := 0` (0x570e6f); every group order calls it before it may set the byte."""
    from engine.sim.orders import _cancel_group
    w = world()
    a, b = unit(w, 1, 10, 10, speed=30), unit(w, 2, 12, 10, speed=18)
    sim = Simulation(w)
    sim.step([MoveUnits(1, (a.id, b.id), (20, 12))])
    g = w.groups[a.order_group]
    assert g.speed == 18
    _cancel_group(w, g)
    assert g.speed == 0 and walk_speed(w, a) == unit_speed(a) == 30


def test_effect_after_the_order_never_touches_the_group_byte():
    """Writers of `group+0x44`: ctor / copy (0x522e93, 0x52332f), `FUN_005703c0`, `FUN_0057063e`, `FUN_00570e83`; the effect code only
    writes the unit's `+0x8c`, so the byte stays and `walk_speed` keeps using it."""
    w = world()
    a, b = unit(w, 1, 10, 10, speed=30), unit(w, 2, 12, 10, speed=18)
    sim = Simulation(w)
    sim.step([MoveUnits(1, (a.id, b.id), (20, 12))])
    b.speed_mod += 12                               # Haste
    a.speed_mod -= 20                               # Slow
    assert walk_speed(w, a) == walk_speed(w, b) == 18


# --- the stale dynamic list is unreachable ------------------------------------------------------------

@needs_data
def test_no_template_turns_for_more_than_the_dynamic_refresh_rate():
    """A turn of 180 degrees lasts ceil(128 / rate) ticks; the stale-list fallback needs more than DynamicRefreshRate (32) calls."""
    from allods2.common import game_fs
    from allods2.formats import progression as prog, unitstats
    t = unitstats.load(game_fs())
    for x in t.of_kind("monster"):
        assert -(-128 // max(1, x.turn_rate)) <= 16, x.name
    for x in t.of_kind("human"):
        assert -(-128 // max(1, prog.derived_speed(x, x.unit_type) & 255)) <= 8, x.name
