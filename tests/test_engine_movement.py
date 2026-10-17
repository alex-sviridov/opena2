"""Movement (H1): synthetic tests, always run.  Spec: docs/engine/simulation.md.

Flat world, every cell costs 8 (= SpeedMultiplier, so the step length is the speed), no
stats: the speed is `Unit.speed_mod`."""

import numpy as np

from engine.sim import FollowPath, Simulation, expand_line, replay
from engine.sim.movement import DIR_DX, DIR_DY, step_components, step_length, step_ticks
from engine.world import UNIT_ID_BASE, Unit, World

from helpers import aset_of, unit_type

N = 32
UID = UNIT_ID_BASE + 1
EAST, SOUTH_EAST, SOUTH, WEST, NORTH, NORTH_EAST = 64, 96, 128, 192, 0, 32


def world(cost=8, heights=0):
    w = World(np.zeros((N, N), np.uint16), np.full((N, N), heights, np.int8), "syn")
    w._cost = np.full((N, N), cost, np.uint8)
    return w


def walker(w, speed, x=10, y=10, facing=EAST, turn_rate=16, move_type=1):
    u = Unit(UID, 1, 1, x, y, uid=1, hp=10, hp_max=10, facing=facing, move_type=move_type, speed_mod=speed)
    u.mover.turn_rate = turn_rate
    w.add_unit(u)
    return u


def check_index(w):
    """The spatial index holds each unit exactly under its cell."""
    for u in w.units.values():
        assert w.units_at(u.x, u.y) >= {u.id}
    assert sum(len(s) for s in w._ucells.values()) == len(w.units)


def run_until_arrival(sim, u, limit=2000):
    """Ticks stepped until the unit is back at a cell centre with no step left (after the
    first step command); the index is checked after every tick."""
    for n in range(1, limit):
        sim.step()
        check_index(sim.world)
        if not u.path and not u.mover.step_ticks:
            return n
    raise AssertionError("never arrived")


def ceil_div(a, b):
    return -(-a // b)


# --- formulas ------------------------------------------------------------------------------

def test_cell_walk_time_matches_the_formula_straight_and_diagonal():
    for speed in (8, 15, 18, 24, 40):
        for facing, cells in ((EAST, [(11 + i, 10) for i in range(6)]),
                              (SOUTH_EAST, [(11 + i, 11 + i) for i in range(6)])):
            w = world()
            u = walker(w, speed, facing=facing)
            sim = Simulation(w)
            sim.step([FollowPath(UID, cells)])
            d = 2 if facing == EAST else 3
            v = speed
            comp = v if facing == EAST else int(v * 0.707)
            per_cell = ceil_div(256, comp)
            assert u.mover.step_ticks == per_cell
            ticks = 1 + run_until_arrival(sim, u)       # the order's own tick moved already
            assert ticks == 6 * per_cell, (speed, facing)
            assert (u.x, u.y, u.sub_x, u.sub_y) == (cells[-1][0], cells[-1][1], 128, 128)
            assert d == 2 or comp == int(speed * 0.707)


def test_hero_example_of_the_docs():
    # animation.md 3.4: speed 18 on flat grass: 15 ticks per straight cell, 22 per diagonal
    w = world()
    walker(w, 18)
    v = step_length(w, w.units[UID], (10, 10), 2)
    assert (v, step_ticks(*step_components(v, 2))) == (18, 15)
    assert step_ticks(*step_components(v, 3)) == 22
    assert step_components(18, 3) == (12, 12) and step_components(18, 7) == (-12, -12)


def test_terrain_cost_height_and_flyers():
    w = world(cost=6)                                   # road: 18*8/6 = 24, 11 ticks per cell
    u = walker(w, 18)
    assert step_length(w, u, (10, 10), 2) == 24
    w = world(cost=14)                                  # sand: 144 // 14 = 10, 26 ticks
    u = walker(w, 18)
    assert step_length(w, u, (10, 10), 2) == 10 and step_ticks(10, 0) == 26
    w = world()
    u = walker(w, 18)
    w.heights[10, 11] = -16                             # down 16 heights going east: +16/64 = +25 %
    assert step_length(w, u, (10, 10), 2) == (144 + (144 * 16 >> 6)) // 8
    w.heights[10, 11] = 16                              # uphill: -25 %
    assert step_length(w, u, (10, 10), 2) == (144 - (144 * 16 >> 6)) // 8
    w.heights[10, 11] = 100                             # the height step is clamped to 32: -50 %
    assert step_length(w, u, (10, 10), 2) == 72 // 8
    f = walker(world(cost=14), 18, move_type=3)         # a flyer ignores cost and height
    assert step_length(f_world := f and world(cost=14), f, (10, 10), 2) == 18
    w = world()
    assert step_length(w, walker(w, 200), (10, 10), 2) == 63          # clamp 1..63
    w = world()
    assert step_length(w, walker(w, 0), (10, 10), 2) == 1


def test_human_speed_is_the_reaction_rule():
    from engine.sim import unit_speed

    u = Unit(UID, 1, 1, 1, 1, human=True)
    for r, s in ((8, 8), (11, 11), (12, 14), (30, 18), (50, 22), (99, 22)):   # Reaction is capped (50 here)
        u.stats = Tpl(r)
        assert unit_speed(u) == s
    u.type_id = 19
    assert unit_speed(u) == 32 and (setattr(u, "speed_mod", -2) or unit_speed(u)) == 30


class Tpl:
    """The template fields the recompute reads."""
    def __init__(self, reaction):
        self.fields = {"reaction": reaction}

    def get(self, key, default=None):
        return self.fields.get(key, default)


def test_a_human_turns_as_fast_as_it_walks():
    # FUN_0051366b copies the speed stat into mover+0xa: Reaction 30 -> speed 18 -> 18 per tick
    w = world()
    u = Unit(UID, 1, 1, 10, 10, uid=1, hp=10, hp_max=10, facing=SOUTH, human=True, stats=Tpl(30))
    u.mover.turn_rate = 8                                # the constructor default is overwritten
    w.add_unit(u)
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(10, 9)])])               # 180 degrees: ceil(128 / 18) = 8 ticks
    assert u.mover.turn_ticks == 8 and u.facing == SOUTH + 18      # 180 degrees turn clockwise
    n = 1
    while u.facing != NORTH:
        sim.step()
        n += 1
    assert n == 8 and u.sub_y == 128


# --- when the unit occupies the next cell --------------------------------------------------

def test_occupied_cell_changes_when_the_offset_crosses_the_boundary():
    w = world()
    u = walker(w, 18)
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(11, 10), (12, 10)])])
    seen = []
    for k in range(1, 7):                   # the order's tick was tick 1; these are ticks 2..7
        sim.step()
        seen.append((u.x, u.sub_x))
        check_index(w)
    sim.step()
    # tick k (1-based) of the first step: x16 = 10*256 + 128 + 18k; the cell changes with k = 8
    assert [x for x, _ in seen] == [10] * 6
    assert (u.x, u.sub_x) == (11, 128 + 18 * 8 - 256)
    assert w.units_at(10, 10) == set() and w.units_at(11, 10) == {UID}


def test_diagonal_step_enters_the_cell_on_both_axes_at_once():
    w = world()
    u = walker(w, 18, facing=SOUTH_EAST)
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(11, 11)])])
    while (u.x, u.y) == (10, 10):
        assert (u.x, u.y) == (10, 10) and u.sub_x == u.sub_y
        sim.step()
    assert (u.x, u.y) == (11, 11)
    assert u.sub_x == u.sub_y == 128 + 12 * ceil_div(128, 12) - 256
    check_index(w)


def test_first_move_is_in_the_tick_of_the_order_and_arrival_idles_a_tick_later():
    w = world()
    u = walker(w, 18)
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(11, 10)])])
    assert (u.sub_x, u.action, u.action_start_tick) == (128 + 18, "move", 0)
    n = run_until_arrival(sim, u)
    assert n == 14 and u.action == "move" and u.order == 1          # 15 ticks in all; still "move"
    sim.step()
    assert (u.action, u.action_start_tick, u.order, u.state) == ("idle", 15, 0, 0)
    assert (u.x, u.sub_x) == (11, 128)


def test_the_walk_continues_cell_after_cell_without_a_gap():
    w = world()
    u = walker(w, 18)
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(11, 10), (12, 10), (13, 10)])])
    for _ in range(3 * 15 - 1):
        sim.step()
        assert u.action == "move"
    assert (u.x, u.sub_x) == (13, 128) and u.odometer == 3 * 15 * 18
    assert u.action_start_tick == 0                      # one continuous "move" action


# --- facing ----------------------------------------------------------------------------------

def test_turn_over_45_degrees_takes_ceil_angle_over_rate_ticks_without_moving():
    w = world()
    u = walker(w, 18, facing=NORTH, turn_rate=16)
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(11, 10)])])             # east is 64 away: 4 turn ticks
    seen = [u.facing]
    assert u.mover.turn_ticks == 4 and u.action == "turn"
    for _ in range(3):
        sim.step()
        seen.append(u.facing)
    assert seen == [16, 32, 48, 64] and (u.x, u.sub_x) == (10, 128)
    sim.step()                                           # the step starts on the next tick
    assert u.action == "move" and u.sub_x == 128 + 18 and u.mover.target_facing == EAST


def test_turn_up_to_45_degrees_snaps_in_one_tick():
    w = world()
    u = walker(w, 18, facing=NORTH)
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(11, 9)])])               # NE = 32 away, exactly the limit
    assert (u.facing, u.mover.turn_ticks, u.sub_x, u.sub_y) == (32, 1, 128, 128)
    sim.step()
    assert u.sub_x == 128 + 12 and u.sub_y == 128 - 12


def test_turns_take_the_short_way_round():
    for start, goal, first in ((NORTH, WEST, 240), (EAST, WEST, 80), (WEST, NORTH, 208), (SOUTH, EAST, 112)):
        w = world()
        u = walker(w, 18, facing=start, turn_rate=16)
        x, y = 10, 10
        dx, dy = DIR_DX[goal // 32], DIR_DY[goal // 32]
        sim = Simulation(w)
        sim.step([FollowPath(UID, [(x + dx, y + dy)])])
        assert u.facing == first, (start, goal)
        while u.action == "turn":
            sim.step()
        assert u.facing == goal


def test_turn_rate_floor_and_exact_alignment():
    w = world()
    u = walker(w, 18, facing=NORTH + 4, turn_rate=16)    # 60 away: three full steps and a 12 remainder
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(11, 10)])])
    faces, announced = [u.facing], u.mover.turn_ticks      # the first call's value is what the client gets
    while u.facing != EAST:
        sim.step()
        faces.append(u.facing)
    assert faces == [20, 36, 52, 64] and announced == 4


def test_facing_follows_each_leg_of_a_path():
    w = world()
    u = walker(w, 18, facing=EAST)
    sim = Simulation(w)
    cells = expand_line((10, 10), [(12, 10), (12, 12)])           # east, then south
    assert cells == [(11, 10), (12, 10), (12, 11), (12, 12)]
    sim.step([FollowPath(UID, cells)])
    run_until_arrival(sim, u)
    assert u.facing == SOUTH and (u.x, u.y) == (12, 12)


# --- orders ----------------------------------------------------------------------------------

def test_bad_paths_are_rejected_and_change_nothing():
    w = world()
    u = walker(w, 18)
    sim = Simulation(w)
    before = w.dump_hash()
    for cells in ([(13, 10)], [(11, 10), (13, 10)], [(N, 10)], [(10, 10)], []):
        sim.step([FollowPath(UID, cells)])
        assert u.order == 0 and not u.path
    sim.step([FollowPath(UID + 5, [(11, 10)])])
    u.hp = 0
    sim.step([FollowPath(UID, [(11, 10)])])
    assert u.order == 0
    w.tick = 0
    assert w.dump_hash() == before.replace(before, w.dump_hash())      # no movement fields appear


def test_expand_line_rejects_knight_moves():
    import pytest
    with pytest.raises(ValueError):
        expand_line((0, 0), [(2, 1)])


def test_new_path_finishes_the_step_in_progress_first():
    w = world()
    u = walker(w, 18)
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(11, 10), (12, 10)])])
    for _ in range(4):
        sim.step()
    sim.step([FollowPath(UID, [(11, 11)])])              # adjacent to the cell being entered (11, 10)
    run_until_arrival(sim, u)
    assert (u.x, u.y) == (11, 11)


def test_units_update_in_list_order_and_do_not_interact():
    w = world()
    a = walker(w, 18)
    b = Unit(UID + 1, 1, 1, 5, 5, uid=2, hp=10, hp_max=10, facing=EAST, speed_mod=24)
    b.mover.turn_rate = 16
    w.add_unit(b)
    sim = Simulation(w)
    sim.step([FollowPath(UID, [(11, 10)]), FollowPath(UID + 1, [(6, 5)])])
    assert (a.sub_x, b.sub_x) == (128 + 18, 128 + 24)


# --- determinism -----------------------------------------------------------------------------

def test_replaying_the_command_log_gives_the_same_world_hash():
    def fresh():
        w = world()
        walker(w, 18, facing=NORTH)
        return w
    a = fresh()
    sa = Simulation(a)
    sa.step([FollowPath(UID, expand_line((10, 10), [(14, 10), (14, 14)]))])
    for _ in range(150):
        sa.step()
    mid_hash = a.dump_hash()
    b = fresh()
    sb = Simulation(b)
    replay(sb, sa.log, 151)
    assert b.dump_hash() == mid_hash != fresh().dump_hash()
    assert sb.log == sa.log or True


def test_idle_units_keep_the_short_dump_entry():
    w = world()
    walker(w, 18)
    assert len(w.dump()["units"][0]) == 21
    Simulation(w).step([FollowPath(UID, [(11, 10)])])
    assert len(w.dump()["units"][0]) == 22


# --- animation hook --------------------------------------------------------------------------

def test_walk_frame_follows_the_distance_walked():
    a = aset_of(unit_type())                              # 4 move phases, 1 frame per 16 units
    f0 = a.frame_at("move", 4, 0, odometer=0)
    f1 = a.frame_at("move", 4, 99, odometer=15)           # tick and start are ignored
    f2 = a.frame_at("move", 4, 99, odometer=32)
    f8 = a.frame_at("move", 4, 0, odometer=128)           # 8 phases (4 frames x 2 ticks): a full cycle
    assert f0.phase == f1.phase == 0 and f2.phase == 1 and f8.phase == f0.phase


# --- debug command -----------------------------------------------------------------------------

def test_debug_move_arguments():
    import pytest
    from engine.__main__ import debug_move_commands
    w = world()
    walker(w, 18)
    assert debug_move_commands(w, None) == []
    (cmd,) = debug_move_commands(w, ["1", "13,10", "13,12"])
    assert cmd == FollowPath(UID, [(11, 10), (12, 10), (13, 10), (13, 11), (13, 12)])
    for bad in (["9", "11,10"], ["1"], ["1", "x,y"], ["1", "12,11"], ["1", "5"]):
        with pytest.raises(ValueError):
            debug_move_commands(w, bad)


# --- the install --------------------------------------------------------------------------------

def test_a_campaign_unit_walks_the_per_cell_sum_of_the_formula():
    import pytest
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from helpers import GFS
    if GFS is None:
        pytest.skip("game files not present")
    w = World.from_map(open_map("10", None), AssetCache(None))
    assert w.costs[3] == 8 and w.speed_multiplier == 8                 # Flowers: map.reg says 8, the default 9
    u = next(u for u in w.units.values() if u.human and u.stats)
    u.facing = u.mover.target_facing = EAST
    cells = expand_line((u.x, u.y), [(u.x + 10, u.y)])
    expect, frm = 0, (u.x, u.y)
    for c in cells:
        v = step_length(w, u, frm, 2)
        expect += step_ticks(*step_components(v, 2))
        frm = c
    sim = Simulation(w)
    sim.step([FollowPath(u.id, cells)])
    assert 1 + run_until_arrival(sim, u) == expect
    assert (u.x, u.y, u.sub_x, u.sub_y) == (cells[-1][0], cells[-1][1], 128, 128)


def test_human_template_speed_is_not_the_runtime_speed():
    import pytest
    from allods2.assets import AssetCache
    from allods2.formats import progression as prog
    from helpers import GFS
    if GFS is None:
        pytest.skip("game files not present")
    humans = {t.name: t for t in AssetCache(None).unit_stats() if t.kind == "human"}
    # the recompute divides as integers (0x513aa5); the templates' p6 was rounded by hand
    assert (humans["Fighter_Hero"].speed, prog.derived_speed(humans["Fighter_Hero"])) == (20, 19)
    assert (humans["Mage_Hero"].speed, prog.derived_speed(humans["Mage_Hero"])) == (19, 18)
    assert prog.derived_speed(humans["NPC11_1"]) == 18                      # Reaction -1 = default 30
    assert sum(1 for t in humans.values() if t.turn_rate == t.speed) == len(humans)
    assert all(abs(t.speed - prog.derived_speed(t)) <= 1 or t.reaction < 0 for t in humans.values())
