"""Selection commands, the command log and replay (G3b).  Spec:
docs/superpowers/specs/2026-10-17-interface-selection-design.md "Commands and the log"."""

import numpy as np
import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.sim import SelectUnits, Simulation, replay
from engine.world import UNIT_ID_BASE, Player, Unit, World

from helpers import GFS

N = 16
A1, A2, B1, B2 = (UNIT_ID_BASE + i for i in (1, 2, 3, 4))


def world():
    w = World(np.zeros((N, N), np.uint16), np.zeros((N, N), np.int8), "syn")
    w.players = {1: Player(1, 0, human=True), 2: Player(2, 1)}
    for uid, owner in ((1, 1), (2, 1), (3, 2), (4, 2)):
        w.add_unit(Unit(UNIT_ID_BASE + uid, 1, owner, uid, 1, uid=uid, hp=10, hp_max=10))
    return w


def run(w, *cmds):
    sim = Simulation(w)
    for c in cmds:
        sim.step([c])
    return sim


def test_select_own_and_dedupe():
    w = world()
    run(w, SelectUnits(1, [A2, A1, A2]))
    assert w.players[1].selection == (A2, A1) and not w.selection_is_foreign(1)


def test_select_foreign_alone_is_accepted():
    w = world()
    run(w, SelectUnits(1, (B1,)))
    assert w.players[1].selection == (B1,) and w.selection_is_foreign(1)


def test_mixed_and_several_foreign_are_rejected():
    w = world()
    run(w, SelectUnits(1, (A1,)), SelectUnits(1, (A2, B1)), SelectUnits(1, (B1, B2)))
    assert w.players[1].selection == (A1,)
    w.players[1].selection = ()
    run(w, SelectUnits(1, (B1, B2)))
    assert w.players[1].selection == ()


def test_toggle_adds_removes_and_is_rejected_while_foreign():
    w = world()
    run(w, SelectUnits(1, (A1,)), SelectUnits(1, (A2,), True), SelectUnits(1, (A1, B1), True))
    assert w.players[1].selection == (A2,)
    run(w, SelectUnits(1, (B1,)), SelectUnits(1, (A1,), True))
    assert w.players[1].selection == (B1,)


def test_empty_clears_unknown_dropped_unknown_player_rejected():
    w = world()
    run(w, SelectUnits(1, (A1, 0xDEAD)))
    assert w.players[1].selection == (A1,)
    run(w, SelectUnits(9, (A1,)))
    assert w.players[1].selection == (A1,)
    run(w, SelectUnits(1, ()))
    assert w.players[1].selection == ()


def test_remove_unit_purges_selection():
    w = world()
    run(w, SelectUnits(1, (A1, A2)), SelectUnits(2, (A1,)))
    w.remove_unit(A1)
    assert w.players[1].selection == (A2,) and w.players[2].selection == ()


def test_dump_has_selection_only_when_non_empty():
    w = world()
    assert all(len(p) == 7 for p in w.dump()["players"])
    h = w.dump_hash()
    run(w, SelectUnits(1, (A1,)))
    assert w.dump()["players"][0][7] == {"selection": [A1]} and w.dump_hash() != h


def test_log_and_replay():
    w = world()
    cmds = [SelectUnits(1, (A1, B1)), SelectUnits(1, (A1, A2)), SelectUnits(1, (A1,), True)]
    sim = Simulation(w)
    sim.step()
    sim.step([cmds[0]])
    sim.step([cmds[1], cmds[2]])
    assert sim.log == [(1, cmds[0]), (2, cmds[1]), (2, cmds[2])]
    w2 = world()
    sim2 = Simulation(w2)
    replay(sim2, sim.log, 3)
    assert w2.tick == 3 and sim2.log == sim.log
    assert w2.players[1].selection == w.players[1].selection == (A2,)
    assert w2.dump_hash() == w.dump_hash()


def test_explicit_empty_systems_means_none():
    w = world()
    Simulation(w, []).step([SelectUnits(1, (A1,))])
    assert w.players[1].selection == ()


@pytest.mark.skipif(not GFS, reason="game files not present")
def test_select_on_map_53():
    """Map 53 is the one campaign map with a unit of the human player (map 10 has none)."""
    w = World.from_map(open_map("53", GFS), AssetCache(GFS))
    human = next(p.id for p in w.players.values() if p.human)
    uid = next(u.id for u in w.units.values() if u.owner == human)
    sim = Simulation(w)
    sim.step([SelectUnits(human, (uid,))])
    assert w.players[human].selection == (uid,) and not w.selection_is_foreign(human)
    other = next(u.id for u in w.units.values() if u.owner != human)
    sim.step([SelectUnits(human, (other,))])
    assert w.selection_is_foreign(human)
