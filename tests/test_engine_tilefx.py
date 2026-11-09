"""K7: cell effects for scripts (docs/engine/triggers.md check 25, instants 29 / 30): the debug solves of maps 93, 94 and 95.

The puzzles read the cell record's effect slots with check 25 (Wall of Fire = layer 0, Poison Cloud 2, Wall of Earth 3).  Debug shortcuts (not
commands, so the same in a replay): the hero is put on a cell with `triggers.teleport`, given the spell and mana, and the boss of the last
step is killed by setting its HP; everything else is game logic (switches, casts, traps, teleporters, the script).
"""

import pytest

from engine.sim import CastSpell, MoveUnits, Simulation, UseStructure
from engine.sim import effects, triggers as T
from helpers import have_install
from test_engine_structures import _build, _use

pytestmark = pytest.mark.skipif(not have_install(), reason="needs the game install")

FIRE_WALL, EARTH_WALL = 3, 17


def _run(w, sim, hero, n):
    for _ in range(n):
        hero.hp = 300
        sim.step()


def _hero(n):
    w, sim, hero = _build(n)
    hero.spellbook = (1 << FIRE_WALL) | (1 << EARTH_WALL)
    hero.mana = hero.mana_max = 900
    hero.skills = (0, 60, 60, 60, 60, 60)
    return w, sim, hero


def _cast(w, sim, hero, spell, cell, frm, layer):
    """Put the hero on `frm`, order the cast at `cell` and run until the wall stands on the cell (the layer holds a carrier)."""
    assert (hero.x, hero.y) == tuple(frm) or T.teleport(w, hero, *frm)
    sim.step([CastSpell(1, (hero.id,), spell, None, cell=cell)])
    for _ in range(120):
        _run(w, sim, hero, 1)
        if effects.tile_layer(w, cell[0], cell[1], layer):
            return
    raise AssertionError("the cast at %s never stamped" % (cell,))


def _gate(w, sim, hero):
    """The shared opening of maps 93-95: both switches (uids 2, 3) open the teleporter record at (102, 34); walking in lands on (74, 72)."""
    for uid in (2, 3):
        _use(w, sim, hero, uid)
    _run(w, sim, hero, 40)
    assert w.cell_effects[(102, 34)][0] == 0x17
    assert T.teleport(w, hero, 100, 34)
    sim.step([MoveUnits(1, (hero.id,), (102, 34))])
    _run(w, sim, hero, 200)
    assert (hero.x, hero.y) == (74, 72)


def _finish(w, sim, hero, near, dead):
    """The last steps of the three maps, with the fights replaced by debug shortcuts: a unit of the quest dies, the hero is next to the named one
    (a script variable counts it), then at the exit corner (10, 135) the mission completes."""
    def find(uid):
        return next(u for u in list(w.units.values()) + list(w.script.phased.values()) if u.uid == uid)

    find(dead).hp = -1000
    _run(w, sim, hero, 60)
    other = find(near)                                      # a phased-out unit keeps its cell, which check 6 measures
    assert T.teleport(w, hero, other.x + 1, other.y) or T.teleport(w, hero, other.x - 1, other.y)
    _run(w, sim, hero, 40)
    assert T.teleport(w, hero, 10, 135)
    _run(w, sim, hero, 40)
    assert T.result(w) == "won"


def test_map_93_two_fire_walls_open_the_teleporter_and_the_mission_can_be_won():
    w, sim, hero = _hero(93)
    _gate(w, sim, hero)
    _cast(w, sim, hero, FIRE_WALL, (123, 69), (123, 72), 0)
    assert (115, 72) not in w.cell_effects
    _cast(w, sim, hero, FIRE_WALL, (123, 75), (123, 72), 0)
    _run(w, sim, hero, 40)
    assert w.cell_effects[(115, 72)] == (23, 255, 115, 72, 100, 104)        # trigger 9: both rows burn at once -> instant 25
    _finish(w, sim, hero, near=27, dead=32)


def test_map_93_a_single_wall_is_not_enough():
    w, sim, hero = _hero(93)
    _cast(w, sim, hero, FIRE_WALL, (123, 69), (123, 72), 0)
    _run(w, sim, hero, 200)
    assert (115, 72) not in w.cell_effects


def test_map_94_the_stonewall_needs_straight_walls_and_a_diagonal_one():
    """Rows 113 / 117 want (63, 65, 67) walled, row 115 only (65, 115): a wall cast from the east is the diagonal shape (effects.md 6.2)."""
    w, sim, hero = _hero(94)
    _gate(w, sim, hero)
    _cast(w, sim, hero, EARTH_WALL, (65, 113), (65, 109), 3)
    _cast(w, sim, hero, EARTH_WALL, (65, 117), (65, 121), 3)
    assert (66, 107) not in w.cell_effects
    _cast(w, sim, hero, EARTH_WALL, (65, 115), (69, 115), 3)
    assert [effects.tile_layer(w, x, 115, 3) for x in (63, 65, 66)] == [0, 1, 0]
    _run(w, sim, hero, 60)
    assert w.cell_effects[(66, 107)] == (23, 100, 66, 107, 122, 124)
    _finish(w, sim, hero, near=51, dead=33)


def test_map_94_a_straight_middle_wall_does_not_solve_it():
    w, sim, hero = _hero(94)
    _cast(w, sim, hero, EARTH_WALL, (65, 113), (65, 109), 3)
    _cast(w, sim, hero, EARTH_WALL, (65, 117), (65, 121), 3)
    _cast(w, sim, hero, EARTH_WALL, (65, 115), (65, 111), 3)
    _run(w, sim, hero, 80)
    assert (66, 107) not in w.cell_effects


def test_map_95_the_clouds_stay_until_fire_burns_them_and_instant_29_made_them_long_lived():
    w, sim, hero = _hero(95)
    _run(w, sim, hero, 80)
    clouds = [c for c in w.carriers if c.kind == "area" and c.spell == 6]
    assert [c.centre for c in clouds] == [(66, 25), (69, 27)]
    assert all(c.life & 0xFFFF > 32000 for c in clouds)                      # instant 29: 32768 (the first 320 ticks of life were replaced)
    assert effects.tile_layer(w, 66, 25, 2) == 1 and effects.tile_layer(w, 66, 25, 0) == 0
    _gate(w, sim, hero)
    for y in (24, 26, 28):                                                   # fire removes a cloud from the cells it stamps (effects.md 6.4)
        _cast(w, sim, hero, FIRE_WALL, (67, y), (67, y - 3), 0)
        assert effects.tile_layer(w, 67, y, 2) == 0
    _run(w, sim, hero, 80)
    assert w.cell_effects[(68, 37)] == (23, 100, 68, 37, 20, 19)
    _finish(w, sim, hero, near=50, dead=35)


def test_map_94_cast_replays_to_the_same_hash():
    def go(cmds):
        w, sim, hero = _hero(94)
        assert T.teleport(w, hero, 65, 109)
        for i in range(160):
            hero.hp = 300
            sim.step(cmds.get(w.tick, ()))
        return w, sim

    w, sim = go({2: [CastSpell(1, (_hero(94)[2].id,), EARTH_WALL, None, cell=(65, 113))]})
    assert effects.tile_layer(w, 65, 113, 3) == 1
    by_tick = {}
    for tick, cmd in sim.log:
        by_tick.setdefault(tick, []).append(cmd)
    w2, _ = go(by_tick)
    assert w2.dump_hash() == w.dump_hash()
