"""Cell record effects (traps) and the hidden caster (docs/engine/effects.md 9, sim/traps.py; CONFIRMED routines in the comments).
Synthetic worlds always run; the real-map tests read the install (maps 76 and 93) and skip without it."""

import pytest

from engine.sim import MoveUnits, Simulation
from engine.sim import traps
from engine.world import CastReleased, CastStarted, Damage
from spell_helpers import FIRE_ARROW, full_table
from test_engine_combat import fighter, run, world as base_world

from helpers import GFS

TELEPORT = traps.TELEPORT


def world():
    w = base_world()
    w.spell_table = full_table()
    return w


def walker(w, uid, x, y, owner=1, hp=100):
    u = fighter(w, uid, x, y, owner=owner, hp=hp)
    return u


def walk_until(sim, u, cond, limit=200):
    for _ in range(limit):
        sim.step()
        if cond():
            return
    raise AssertionError("never")


def test_record_is_refused_on_a_static_block_cell_and_dumped_only_when_present():
    w = world()
    assert "cell_effects" not in w.dump()
    w._block[12, 12] = 5                                # FUN_0055ba36: live layer bit 0 refuses the record
    assert not traps.set_record(w, 12, 12, (TELEPORT, 0, 12, 12, 20, 20))
    assert traps.set_record(w, 13, 12, (TELEPORT, 0, 13, 12, 20, 20))
    assert w.dump()["cell_effects"] == [[13, 12, [TELEPORT, 0, 13, 12, 20, 20]]]


def test_instant_25_record_layout():
    # FUN_0057847e: n4 == 0 -> source = target = the trap cell; else (n4, n5) and (n6, n7)
    assert traps.instant_effect([23, 255, 15, 121, 0, 0, 0, 0]) == ((15, 121), (23, 255, 15, 121, 15, 121))
    assert traps.instant_effect([23, 100, 15, 121, 1, 2, 13, 22]) == ((15, 121), (23, 100, 1, 2, 13, 22))


def test_teleport_trap_sets_brain_b0_on_entering_and_teleports_at_the_step_end_then_stands():
    w = world()
    u = walker(w, 1, 10, 10)
    traps.set_record(w, 11, 10, (TELEPORT, 0, 11, 10, 20, 14))
    sim = Simulation(w)
    sim.step([MoveUnits(1, (u.id,), (14, 10))])
    walk_until(sim, u, lambda: (u.x, u.y) == (11, 10))
    assert u.teleport_to == (14 << 8) | 20 and u.sub_x != 128   # FUN_005503af at the border crossing (place)
    walk_until(sim, u, lambda: (u.x, u.y) != (11, 10))
    assert (u.x, u.y, u.sub_x, u.sub_y) == (20, 14, 128, 128)   # FUN_00555b38 0x555c50: FUN_0055a96c at the step end
    assert u.order == 0xC and u.anchor == (20, 14) and not u.mode_go and not u.stopped   # FUN_0056dba1: cancel + stand
    assert u.teleport_to                                       # still set: the Brain tick consumes it next tick
    sim.step()
    assert u.teleport_to == 0 and (u.x, u.y) == (20, 14)       # the own cell is never free: nothing moves


def test_a_failed_teleport_lets_the_walk_go_on_and_clears_b0_at_the_next_centre():
    w = world()
    u = walker(w, 1, 10, 10)
    blocker = walker(w, 2, 20, 14, owner=1)
    traps.set_record(w, 11, 10, (TELEPORT, 0, 11, 10, 20, 14))
    sim = Simulation(w)
    sim.step([MoveUnits(1, (u.id,), (14, 10))])
    walk_until(sim, u, lambda: (u.x, u.y) == (11, 10) and u.sub_x == 128)
    assert u.order == 1 and u.teleport_to                      # the target is stamped by the blocker: FUN_0055a928 fails
    walk_until(sim, u, lambda: u.teleport_to == 0, limit=3)
    walk_until(sim, u, lambda: (u.x, u.y) == (14, 10) and u.order == 0xC, limit=200)
    assert (blocker.x, blocker.y) == (20, 14)


def test_the_trap_fires_every_time_it_is_entered():
    w = world()
    u = walker(w, 1, 10, 10)
    traps.set_record(w, 11, 10, (TELEPORT, 0, 11, 10, 20, 14))
    sim = Simulation(w)
    for _ in range(2):
        sim.step([MoveUnits(1, (u.id,), (12, 10))])
        walk_until(sim, u, lambda: (u.x, u.y) == (20, 14))
        run(sim, 2)
        w.move_unit(u.id, 10, 10)                           # back in front of the trap (no record on (10, 10))
    assert (11, 10) in w.cell_effects


def test_a_flyer_ignores_the_place_reader_but_not_the_step_end_reader():
    w = world()
    u = walker(w, 1, 10, 10)
    u.move_type = 3                                         # FUN_005503af: class 3 takes the 0x5505c3 branch (no effect test)
    traps.set_record(w, 11, 10, (TELEPORT, 0, 11, 10, 20, 14))
    sim = Simulation(w)
    sim.step([MoveUnits(1, (u.id,), (14, 10))])
    walk_until(sim, u, lambda: (u.x, u.y) != (10, 10))
    assert u.teleport_to == 0
    walk_until(sim, u, lambda: u.sub_x == 128 and u.sub_y == 128, limit=40)
    assert (u.x, u.y) == (20, 14)                           # FUN_00555b38 has no class test


def test_spell_trap_makes_a_hidden_caster_that_casts_at_the_unit_with_level_power():
    w = world()
    u = walker(w, 1, 10, 10, hp=1000)
    traps.set_record(w, 11, 10, (FIRE_ARROW, 40, 11, 10, 11, 10))
    sim = Simulation(w)
    sim.step([MoveUnits(1, (u.id,), (14, 10))])
    state = w.rng.state
    walk_until(sim, u, lambda: w.transients)
    t0 = w.tick - 1                                          # the tick that ran the place (the creature pass)
    c = w.transients[0]
    assert w.rng.state != state                             # FUN_0050e173: the constructor's facing draw rand(128)
    assert (c.x, c.y, c.hp, c.order, c.state, c.cast.target, c.id) == (11, 10, 30, 0xB, 0xD, u.id, 0)
    assert u.id not in [o.id for o in w.units.values() if o is c] and c not in w.units.values()
    run(sim, 40)
    (st,), (rel,) = [e for e in w.fight_log if isinstance(e, CastStarted)], [e for e in w.fight_log if isinstance(e, CastReleased)]
    assert st.tick == t0 + 1 and rel.tick == t0 + 2          # step 2 of the next tick starts it, windup 1 (+0x134)
    assert rel.level == 40 and st.caster == 0               # level = power - 30 + Mind 30
    assert [e for e in w.fight_log if isinstance(e, Damage) and e.target == u.id]
    assert not w.transients                                 # deleted after the recovery (+0x136)


def test_hidden_caster_whose_target_left_is_deleted_after_one_tick():
    w = world()
    u = walker(w, 1, 10, 10)
    c = traps.cast_at_unit(w, 5, 5, u, FIRE_ARROW, 10)
    w.remove_unit(u.id)
    sim = Simulation(w)
    sim.step()
    assert not w.transients and c.done


def test_sized_unit_triggers_every_footprint_cell_record():
    w = world()
    u = walker(w, 1, 10, 10, hp=1000)
    w.slots.lift(u)
    u.stats = traps.CasterStats(token_size=2)               # a 2 x 2 footprint (vtable +0x1c)
    traps.set_record(w, 10, 11, (FIRE_ARROW, 1, 10, 11, 10, 11))
    traps.set_record(w, 11, 11, (FIRE_ARROW, 1, 11, 11, 11, 11))
    w.slots.place(u)                                        # FUN_0055020a: the effect test runs per footprint cell
    assert len(w.transients) == 2


def test_instant_21_cell_cast():
    w = world()
    c = traps.cast_at_cell(w, 5, 5, 12, 12, 3, 20)          # Wall of Fire at a cell
    sim = Simulation(w)
    sim.step()
    assert c.phase == 5 and w.transients                    # tick 1: the start (FUN_00519998), windup 1
    sim.step()
    assert w.carriers and w.carriers[0].kind == "area" and w.carriers[0].centre == (12, 12)    # tick 2: FUN_00519db8 at the cell
    run(sim, 6)                                             # recovery 1 + rand(0..3) + complication 0
    assert not w.transients and c.done


# --- real maps -------------------------------------------------------------------------------------------------------------------------------

def _map_world(n):
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.world import World
    m = open_map("scenario/%d.alm" % n, GFS)
    w = World.from_map(m, AssetCache(GFS))
    return m, w


@pytest.mark.skipif(GFS is None, reason="game files not present")
def test_map_93_section_9_teleport_records_and_a_walker_through_one():
    m, w = _map_world(93)
    assert traps.load_map(w, m) == 6                        # 7 records, (98, 72) lies on a static block cell: refused
    assert (98, 72) not in w.cell_effects
    assert w.cell_effects[(21, 20)] == (TELEPORT, 100, 21, 20, 26, 118)
    from engine.cellslots import _size
    u = next(o for o in w.units.values() if o.move_type == 1 and o.hp > 0 and _size(o) == 1)
    from engine.sim.place import cell_free
    start = next(c for c in ((20, 20), (22, 20), (21, 19), (21, 21), (20, 19), (22, 21)) if cell_free(w, u, *c))
    w.move_unit(u.id, *start)
    sim = Simulation(w)
    sim.step([MoveUnits(u.owner, (u.id,), (21, 20))])
    for _ in range(200):
        sim.step()
        if (u.x, u.y) == (26, 118):
            break
    assert (u.x, u.y, u.order) == (26, 118, 0xC)


@pytest.mark.skipif(GFS is None, reason="game files not present")
def test_map_76_spell_traps_shoot_the_unit_that_enters():
    m, w = _map_world(76)
    assert traps.load_map(w, m) == 15
    assert w.cell_effects[(91, 33)] == (1, 70, 91, 33, 91, 33)  # Fire Arrow, power 70, from the trap cell itself
    from engine.cellslots import _size
    u = next(o for o in w.units.values() if o.move_type == 1 and o.hp > 0 and _size(o) == 1)
    from engine.sim.place import cell_free
    start = next(c for c in ((90, 33), (92, 33), (91, 32), (91, 34), (90, 32), (92, 34)) if cell_free(w, u, *c))
    w.move_unit(u.id, *start)
    u.hp = u.hp_max = 5000
    sim = Simulation(w)
    sim.step([MoveUnits(u.owner, (u.id,), (91, 33))])
    for _ in range(120):
        sim.step()
    rel = [e for e in w.fight_log if isinstance(e, CastReleased) and e.caster == 0]
    assert rel and rel[0].spell == 1 and rel[0].level == 70
    assert [e for e in w.fight_log if isinstance(e, Damage) and e.target == u.id and e.attacker == 0 and e.tick == rel[0].tick]


@pytest.mark.skipif(GFS is None, reason="game files not present")
def test_map_53_set_trap_instant():
    from engine.sim import triggers
    m, w = _map_world(53)
    script = triggers.enable(w, m)
    assert not w.cell_effects                               # map 53 has no section 9 cell records
    (i,) = [c.index for c in script.instants if c.type == 25]
    triggers.run_instant(w, script, i)
    assert w.cell_effects == {(15, 121): (TELEPORT, 255, 15, 121, 13, 22)}
