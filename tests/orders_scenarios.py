"""Scripted order scenarios on small synthetic worlds (no game files): the source of `tests/golden.json["orders"]`
(`tools/update_golden.py`) and of `tests/test_engine_orders_golden.py`.  Each returns a summary dict: the world
dump hash after the run, the first tick after the script at which no unit walks any more
(order 1 units that are parked beside an occupied target count as ended), the final cells, the number of "No way" events."""

import numpy as np

from engine.sim import MoveUnits, SetFormation, Simulation, Stop
from engine.world import UNIT_ID_BASE, Player, Unit, World

EAST = 64
N = 40


def world():
    w = World(np.zeros((N, N), np.uint16), np.zeros((N, N), np.int8), "orders-golden")
    w._cost = np.full((N, N), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    return w


def wall(w, cells):
    for x, y in cells:
        w._block[y, x] = 5
    w.block_rev += 1


def unit(w, uid, x, y, speed=24):
    u = Unit(UNIT_ID_BASE + uid, 1, 1, x, y, uid=uid, hp=10, hp_max=10, facing=EAST, speed_mod=speed)
    u.mover.turn_rate = 32
    w.add_unit(u)
    return u


def run(w, script, ticks):
    """`script`: {tick: [commands]}.  Steps `ticks` ticks; returns (simulation, tick at which the last order-1 unit
    stopped or None)."""
    sim, ended = Simulation(w), None
    for _ in range(ticks):
        sim.step(script.get(w.tick, ()))
        if ended is None and w.tick > max(script) and not any(
                (u.order == 1 and not u.mover.parked and not u.mover.waiting) or u.mover.step_ticks
                for u in w.units.values()):
            ended = w.tick
    return sim, ended


def summary(w, ended):
    return {"hash": w.dump_hash(), "ended": ended, "cells": {str(u.uid): [u.x, u.y] for u in w.units.values()},
            "no_way": len(w.events)}


def walk_reorder():
    """(a) One unit walks east round a wall; at tick 40 (mid-walk) it is ordered to a cell behind it."""
    w = world()
    wall(w, [(18, y) for y in range(8, 26)])
    u = unit(w, 1, 10, 16)
    script = {0: [MoveUnits(1, (u.id,), (28, 16))], 40: [MoveUnits(1, (u.id,), (12, 24))]}
    sim, ended = run(w, script, 900)
    return summary(w, ended)


def group_crossing(formation):
    """(b) Four units in a square walk east past a unit standing idle in their way (a blocker on the middle row);
    formation 0 (Off: all aim at one cell, the fallbacks spread them) or 2 (On: the shape is translated)."""
    w = world()
    blocker = unit(w, 9, 20, 19)
    us = [unit(w, i + 1, 12 + (i % 2) * 2, 18 + (i // 2) * 2) for i in range(4)]
    script = {0: [SetFormation(1, formation), MoveUnits(1, tuple(u.id for u in us), (28, 19))]}
    sim, ended = run(w, script, 900)
    s = summary(w, ended)
    s["blocker_moved"] = (blocker.x, blocker.y) != (20, 19)
    return s


def gap_jam():
    """(b2) The same square with the formation On through a one-cell gap in a wall: the column queues along the wall and
    the units that lose their hop plans give up (simulation 8.3 "spinning", the failure rule)."""
    w = world()
    wall(w, [(20, y) for y in range(8, 32) if y != 20])
    us = [unit(w, i + 1, 12 + (i % 2) * 2, 18 + (i // 2) * 2) for i in range(4)]
    script = {0: [SetFormation(1, 2), MoveUnits(1, tuple(u.id for u in us), (28, 20))]}
    sim, ended = run(w, script, 900)
    return summary(w, ended)


def unreachable():
    """(c) A target inside a walled pocket: the unit stops on the first ring around it and "No way" is posted."""
    w = world()
    wall(w, [(x, y) for x in range(24, 31) for y in range(14, 21) if x in (24, 30) or y in (14, 20)])
    u = unit(w, 1, 12, 17)
    script = {0: [MoveUnits(1, (u.id,), (27, 17))], 60: [Stop(1, (u.id,))]}
    sim, ended = run(w, script, 700)
    s = summary(w, ended)
    s["fallback_ring"] = max(abs(u.x - 27), abs(u.y - 17))
    return s


SCENARIOS = {"walk_reorder": walk_reorder, "crossing_off": lambda: group_crossing(0),
             "crossing_on": lambda: group_crossing(2), "gap_jam": gap_jam, "unreachable": unreachable}


def all_summaries():
    return {k: f() for k, f in SCENARIOS.items()}
