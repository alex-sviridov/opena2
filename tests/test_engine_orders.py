"""Orders (H3): command intake, groups, formation, group speed, the group pass, Stop, "No way".
Synthetic worlds, always run; one test per rule of docs/engine/simulation.md "Orders (H3)" (R = click-to-move-research)."""

import numpy as np

from engine.sim import MoveTo, MoveUnits, SelectUnits, SetFormation, Simulation, Stop, replay
from engine.world import UNIT_ID_BASE, NoWay, Player, Unit, World

EAST = 64


def world(n=32, cost=8):
    w = World(np.zeros((n, n), np.uint16), np.zeros((n, n), np.int8), "syn")
    w._cost = np.full((n, n), cost, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    w.players[2] = Player(2, 1)
    return w


def unit(w, uid, x, y, speed=24, owner=1, hp=10):
    u = Unit(UNIT_ID_BASE + uid, 1, owner, x, y, uid=uid, hp=hp, hp_max=10, facing=EAST, speed_mod=speed)
    u.mover.turn_rate = 32
    w.add_unit(u)
    return u


def ids(*us):
    return tuple(u.id for u in us)


def run_until(sim, cond, limit=3000):
    for _ in range(limit):
        if cond():
            return
        sim.step()
    raise AssertionError("condition never met")


def tick_to(sim, phase):
    """Step until the next step() is the one whose counter has `& 15 == phase`."""
    while (sim.world.tick & 15) != phase:
        sim.step()


# --- intake (R 3.1) ----------------------------------------------------------------------------

def test_intake_needs_ids_and_a_valid_first_unit_of_the_player():
    w = world()
    a, b, foe = unit(w, 1, 10, 10), unit(w, 2, 12, 10), unit(w, 3, 14, 10, owner=2)
    sim = Simulation(w)
    sim.step([MoveUnits(1, (), (20, 20)), MoveUnits(1, ids(foe), (20, 20)), MoveUnits(1, (9999,), (20, 20)),
              MoveUnits(7, ids(a), (20, 20)), Stop(1, ()), Stop(1, ids(foe))])
    assert not w.groups and a.order == b.order == foe.order == 0
    sim.step([MoveUnits(1, (9999, a.id), (20, 20))])                    # first id invalid: the whole command drops
    assert not w.groups and a.order == 0
    sim.step([MoveUnits(1, (a.id, 9999, foe.id, b.id), (20, 20))])      # later invalid ids are skipped silently
    (g,) = w.groups.values()
    assert g.members == [a.id, b.id] and a.order == b.order == 1 and foe.order == 0


def test_a_dead_unit_is_not_ordered():
    w = world()
    a, d = unit(w, 1, 10, 10), unit(w, 2, 12, 10, hp=0)
    Simulation(w).step([MoveUnits(1, (a.id, d.id), (20, 20))])
    assert list(w.groups.values())[0].members == [a.id] and d.order == 0


def test_at_most_253_ids_are_taken():
    w = World(np.zeros((40, 40), np.uint16), np.zeros((40, 40), np.int8), "syn")
    w.players[1] = Player(1, 0, human=True, formation=0)
    us = [unit(w, i + 1, 8 + i % 20, 8 + i // 20) for i in range(260)]
    Simulation(w).step([MoveUnits(1, ids(*us), (30, 30))])
    (g,) = w.groups.values()
    assert len(g.members) == 253 and g.members == [u.id for u in us[:253]]
    assert us[253].order == 0 and us[252].order == 1


def test_target_cell_uses_the_low_byte_and_is_clamped_per_axis():
    w = world()
    a, b = unit(w, 1, 10, 10), unit(w, 2, 12, 12)
    w.players[1].formation = 0
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(a), (0, 40))])                           # x < 8 -> 8, y > H - 9 -> 23
    assert a.mover.goal == (8, 23)
    sim.step([MoveUnits(1, ids(b), (256 + 15, 16))])                    # u16 field: only the low byte counts
    assert b.mover.goal == (15, 16)
    assert w.groups[2].target == (15, 16)                               # the group target is not clamped
    sim.step([MoveUnits(1, ids(a), (3, 3))])
    assert w.groups[3].target == (3, 3) and a.mover.goal == (8, 8)


# --- groups (R 3.1) ----------------------------------------------------------------------------

def test_every_command_makes_a_new_group_and_the_unit_leaves_the_old_one():
    w = world()
    a, b, c = unit(w, 1, 10, 10), unit(w, 2, 12, 10), unit(w, 3, 14, 10)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(a, b, c), (20, 20))])
    g1 = a.order_group
    assert b.order_group == c.order_group == g1 and w.groups[g1].members == list(ids(a, b, c))
    sim.step([MoveUnits(1, ids(b), (21, 20))])
    g2 = b.order_group
    assert g2 != g1 and w.groups[g1].members == [a.id, c.id] and w.groups[g2].members == [b.id]
    assert w.groups[g1].target == (20, 20)                              # the old group keeps its order
    sim.step([MoveUnits(1, ids(a, c), (22, 20))])                       # g1 is now empty ...
    assert g1 in w.groups and not w.groups[g1].members
    sim.step([Stop(1, ids(a))])                                         # ... and deleted by the next command
    assert g1 not in w.groups


def test_repeated_ids_move_the_unit_to_the_tail():
    w = world()
    a, b = unit(w, 1, 10, 10), unit(w, 2, 12, 10)
    Simulation(w).step([MoveUnits(1, (a.id, b.id, a.id), (20, 20))])
    assert list(w.groups.values())[0].members == [b.id, a.id]


# --- formation (R 3.2, 4.1) ----------------------------------------------------------------------

def line(w, n=3, gap=1, x0=10, y=10, **kw):
    return [unit(w, i + 1, x0 + i * gap, y, **kw) for i in range(n)]


def test_formation_off_sends_everybody_to_the_clicked_cell():
    w = world()
    us = line(w)
    sim = Simulation(w)
    sim.step([SetFormation(1, 0)])
    sim.step([MoveUnits(1, ids(*us), (20, 20))])
    assert [u.mover.goal for u in us] == [(20, 20)] * 3 and list(w.groups.values())[0].speed == 0


def test_formation_on_translates_the_shape_around_the_truncated_centroid():
    w = world()
    us = line(w, n=3, gap=2)                                            # x 10, 12, 14: centroid 12
    us[0].sub_x = 200                                                   # 10*256+200, 12*256+128, 14*256+128
    sim = Simulation(w)
    sim.step([SetFormation(1, 2)])
    assert w.players[1].formation == 2
    sim.step([MoveUnits(1, ids(*us), (20, 15))])
    # sums: 2760 + 3200 + 3712 = 9672 // 3 = 3224 -> cell 12 (truncating division)
    assert [u.mover.goal for u in us] == [(18, 15), (20, 15), (22, 15)]
    cx = (sum((u.x << 8) | u.sub_x for u in us)) // 3 >> 8
    assert cx == 12


def test_centroid_truncates_the_sum_not_the_cells():
    w = world()
    a, b = unit(w, 1, 10, 10), unit(w, 2, 11, 10)
    b.sub_x = 127                                                       # positions 2688 and 2943: mean 2815.5 -> 2815 -> cell 10
    w.players[1].formation = 2
    Simulation(w).step([MoveUnits(1, ids(a, b), (20, 20))])
    assert a.mover.goal == (20, 20) and b.mover.goal == (21, 20)        # centroid cell 10, offsets 0 and +1


def test_formation_auto_keeps_the_shape_only_for_a_tight_group():
    w = world(n=40)
    tight = line(w, n=3, gap=2)                                         # every member within 2 of centroid 12
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(*tight), (20, 20))])                     # default client mode 1 = Auto
    assert [u.mover.goal for u in tight] == [(18, 20), (20, 20), (22, 20)]
    w2 = world(n=40)
    wide = line(w2, n=3, gap=3, x0=10)                                  # 10, 13, 16: the ends are 3 from 13
    Simulation(w2).step([MoveUnits(1, ids(*wide), (20, 20))])
    assert [u.mover.goal for u in wide] == [(20, 20)] * 3               # spread-out group: formation off


def test_server_mode_mapping_and_default():
    assert Player(1, 0).formation == 1
    from engine.sim.orders import SERVER_FORMATION
    assert SERVER_FORMATION == (0, 2, 1)
    w = world()
    sim = Simulation(w)
    sim.step([SetFormation(1, 3), SetFormation(9, 1), SetFormation(1, -1)])
    assert w.players[1].formation == 1                                  # invalid modes / players ignored


def test_formation_wrap_quirk_sends_a_member_to_the_far_edge():
    w = world()                                                         # 32 wide: clamp range [8, 23]
    a, b = unit(w, 1, 10, 10), unit(w, 2, 15, 10)                       # centroid cell 12 (3200+... = 12.5 -> 12): offsets -2, +3
    w.players[1].formation = 2
    Simulation(w).step([MoveUnits(1, ids(a, b), (1, 12))])
    assert a.mover.goal == (23, 12)                                     # 1 - 2 = -1 & 0xff = 255 -> clamped to W - 9
    assert b.mover.goal == (8, 12)                                      # 1 + 3 = 4 -> clamped up to 8 (no wrap)


# --- group speed (R 4.3) ---------------------------------------------------------------------------

def test_group_speed_is_the_minimum_and_only_set_in_formation():
    w = world()
    fast, slow = unit(w, 1, 10, 10, speed=30), unit(w, 2, 12, 10, speed=18)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(fast, slow), (20, 10))])                 # Auto, tight: formation active
    g = list(w.groups.values())[0]
    assert g.speed == 18
    from engine.sim.movement import step_length
    assert step_length(w, fast, (10, 10), 2) == 18 == step_length(w, slow, (12, 10), 2)   # the fast one walks at the group speed
    w.players[1].formation = 0
    sim.step([MoveUnits(1, ids(fast, slow), (20, 12))])                 # a new group, formation off: speed 0
    g2 = fast.order_group
    assert w.groups[g2].speed == 0
    assert step_length(w, fast, (10, 10), 2) == 30 and step_length(w, slow, (12, 10), 2) == 18   # own speeds again


def test_group_speed_is_fixed_for_the_groups_life():
    w = world()
    a, b = unit(w, 1, 10, 10, speed=30), unit(w, 2, 12, 10, speed=18)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(a, b), (20, 10))])
    b.speed_mod = 40                                                    # Haste after the order does not change it
    assert w.groups[a.order_group].speed == 18
    from engine.sim.movement import walk_speed
    assert walk_speed(w, b) == 18 and walk_speed(w, a) == 18


# --- cancel semantics and the mid-step timeline (R 3.4) -----------------------------------------------

def test_reorder_mid_step_finishes_the_step_then_plans_from_the_new_cell():
    w = world()
    u = unit(w, 1, 10, 10)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(u), (20, 10))])
    assert u.mover.step_ticks and (u.x, u.sub_x) == (10, 128 + 24)      # the first step began in the order's tick
    for _ in range(3):
        sim.step()
    first_end = u.mover.step_target
    steps_before = u.mover.step_ticks
    sim.step([MoveUnits(1, ids(u), (10, 20))])                          # re-order to a different side mid-step
    assert u.mover.step_ticks == steps_before and u.mover.step_target == first_end     # never aborted
    assert u.mover.goal == (10, 20) and u.order == 1 and u.state == 1   # (the Brain tick sets state 1 again)
    # the step runs to its centre; on the snap tick no new step starts
    while True:
        sim.step()
        if not u.mover.step_ticks:
            break
    assert (u.x, u.y, u.sub_x, u.sub_y) == (11, 10, 128, 128) and u.state == 0
    assert u.mover.dest == (20, 10)                                     # still the old plan: no new plan on the snap tick
    sim.step()                                                          # next tick: static plan from the new cell
    assert u.mover.dest == (10, 20) and u.mover.static_path[-1] == (10, 20)
    assert u.mover.last_plan.cells[0] != (12, 10)
    run_until(sim, lambda: u.order != 1)
    assert (u.x, u.y) == (10, 20)


def test_reorder_to_the_same_destination_reuses_the_plan():
    w = world()
    u = unit(w, 1, 10, 10)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(u), (20, 10))])
    run_until(sim, lambda: u.x == 12 and not u.mover.step_ticks)
    plan = u.mover.last_plan
    sim.step([MoveUnits(1, ids(u), (20, 10))])
    sim.step([MoveUnits(1, ids(u), (20, 10))])
    for _ in range(5):
        sim.step()
    assert u.mover.last_plan is plan                                    # no new static plan, no hitch
    run_until(sim, lambda: u.order != 1)
    assert (u.x, u.y) == (20, 10)


def test_order_on_an_idle_unit_plans_and_starts_walking_in_the_same_tick():
    w = world()
    u = unit(w, 1, 10, 10)
    Simulation(w).step([MoveUnits(1, ids(u), (20, 10))])
    assert u.mover.dest == (20, 10) and u.mover.step_ticks and u.action == "move"


def test_reorder_while_turning_stops_the_turn_at_the_current_facing():
    w = world()
    u = unit(w, 1, 10, 10)
    u.facing = u.mover.target_facing = 0
    u.mover.turn_rate = 16
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(u), (20, 10))])                          # east: 64 away, four turn ticks
    sim.step()
    assert u.action == "turn" and u.facing == 32
    sim.step([Stop(1, ids(u))])
    assert u.mover.target_facing == u.facing == 32 and u.order == 0xC


# --- arrival and the group pass (R 4.4) -----------------------------------------------------------------

def test_arrival_leaves_order_1_until_the_group_pass():
    w = world()
    u = unit(w, 1, 10, 10)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(u), (11, 10))])
    run_until(sim, lambda: (u.x, u.sub_x) == (11, 128) and not u.mover.step_ticks)
    assert u.order == 1 and not u.stopped                              # at the goal, waiting for the pass
    arrival = w.tick
    sim.step()
    assert u.order == 1
    while (w.tick & 15) != 6:
        assert u.order == 1
        sim.step()
    assert u.order == 1                                                # the pass runs at the start of the next step
    sim.step()
    assert u.order == 0xC and u.stopped and u.anchor == (11, 10) and not u.mover.arrived and u.state == 0
    assert w.tick - arrival <= 17


def test_arrival_at_a_fallback_cell_ends_at_the_pass():
    w = world()
    for y in range(12, 19):
        for x in range(14, 19):
            w._block[y, x] = 5
    w.block_rev += 1
    u = unit(w, 1, 10, 15)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(u), (16, 15))])                          # inside the block: ends on a ring cell
    run_until(sim, lambda: u.order != 1)
    assert u.order == 0xC and (u.x, u.y) != (16, 15) and max(abs(u.x - 16), abs(u.y - 15)) > 1


def test_failure_ends_the_order_at_once_not_at_the_pass():
    w = world()
    for x in range(9, 12):
        for y in range(9, 12):
            if (x, y) != (10, 10):
                w._block[y, x] = 5                                     # the unit is walled in
    w.block_rev += 1
    u = unit(w, 1, 10, 10)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(u), (20, 10))])
    assert u.order == 0xC and u.stopped and u.anchor == (10, 10) and not u.mover.failed   # same tick (R 7)
    assert w.events == [NoWay(1, 0)]                                  # no fallback cell at all: packed end 0 = cell (0, 0)


def test_parked_unit_is_restarted_by_the_pass_every_16_ticks():
    w = world()
    a = unit(w, 1, 10, 10)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(a), (20, 10))])
    while a.mover.step_ticks:
        sim.step()
    a.mover.parked = True                                              # as after a blocker wait: only the pass restarts it
    start = (a.x, a.y)
    while (w.tick & 15) != 5:                                          # nothing but the pass (tick & 15 == 6) restarts it
        sim.step()
        assert a.mover.parked and (a.x, a.y) == start
    sim.step()
    assert a.mover.parked                                              # the pass runs at the start of the next step
    sim.step()
    assert not a.mover.parked and a.mover.step_ticks                   # restarted and walking in the same tick
    run_until(sim, lambda: a.order != 1)
    assert (a.x, a.y) == (20, 10)


def test_group_pass_stops_a_unit_next_to_a_blocked_group_target():
    w = world()
    blocker = unit(w, 1, 15, 10, owner=2)
    a = unit(w, 2, 12, 10)
    w.players[1].formation = 0
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(a), (15, 10))])                         # the target is held by another unit
    run_until(sim, lambda: a.mover.parked)
    assert a.order == 1 and max(abs(a.x - 15), abs(a.y - 10)) == 1
    for _ in range(40):                                                # restarted and parked again in each pass
        sim.step()
        assert a.order == 1 and max(abs(a.x - 15), abs(a.y - 10)) == 1


# --- Stop (R 5) -------------------------------------------------------------------------------------------

def test_stop_finishes_the_step_and_sets_order_0xc_on_the_own_cell():
    w = world()
    u = unit(w, 1, 10, 10)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(u), (20, 10))])
    for _ in range(3):
        sim.step()
    cell = (u.x, u.y)
    sim.step([Stop(1, ids(u))])
    assert u.order == 0xC and u.anchor == cell and not u.mover.waiting and not u.mover.parked
    assert u.mover.step_ticks and w.groups[u.order_group].order == 3    # the step is not aborted
    run_until(sim, lambda: not u.mover.step_ticks)
    assert (u.x, u.sub_x) == (11, 128)
    for _ in range(40):
        sim.step()
    assert (u.x, u.y) == (11, 10) and u.order == 0xC and u.state == 0   # no further plan


def test_stop_makes_a_new_group_with_group_order_3():
    w = world()
    a, b = unit(w, 1, 10, 10), unit(w, 2, 12, 10)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(a, b), (20, 10))])
    g1 = a.order_group
    sim.step([Stop(1, ids(a))])
    assert a.order_group != g1 and w.groups[a.order_group].order == 3 and w.groups[g1].members == [b.id]
    assert b.order == 1


# --- "No way" (R 6.3) -------------------------------------------------------------------------------------

def test_no_way_event_when_the_fallback_is_more_than_one_cell_away():
    w = world()
    for y in range(12, 19):
        for x in range(14, 19):
            w._block[y, x] = 5
    w.block_rev += 1
    u = unit(w, 1, 10, 15)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(u), (16, 15))])
    assert w.events == [NoWay(1, 0)]
    assert "events" not in w.dump()                                    # not part of the dump / hash


def test_no_way_is_silent_when_the_end_is_adjacent_to_the_target():
    w = world()
    w._block[15, 16] = 5                                               # the target cell itself is blocked
    w.block_rev += 1
    u = unit(w, 1, 10, 15)
    Simulation(w).step([MoveUnits(1, ids(u), (16, 15))])
    assert w.events == [] and u.mover.last_plan.reason == "fallback"


def test_no_way_threshold_is_two_for_a_building_cell():
    w = world()
    w._block[15, 16] = 5
    w._block[14:17, 17:19] = 5                                         # the ring around (16,15) is partly closed
    w.block_rev += 1
    w._claim[(16, 15)] = 12345                                         # a structure holds the target cell
    from engine.sim.movement import _maybe_no_way
    from engine.sim.pathfinding import PathResult
    u = unit(w, 1, 10, 15)
    u.mover.goal = (16, 15)
    _maybe_no_way(w, u, PathResult(end=(14, 15)))                       # distance 2: silent for a building cell
    assert w.events == []
    _maybe_no_way(w, u, PathResult(end=(13, 15)))                       # distance 3: message
    assert len(w.events) == 1
    del w._claim[(16, 15)]
    _maybe_no_way(w, u, PathResult(end=(14, 15)))                       # distance 2, not a building: message
    assert len(w.events) == 2


# --- determinism ---------------------------------------------------------------------------------------------

def test_dump_shows_formation_only_when_it_is_not_the_default():
    w = world()
    h0 = w.dump_hash()
    assert all(len(p) == 7 for p in w.dump()["players"])
    w.players[1].formation = 2
    assert w.dump()["players"][0][-1] == {"formation": 2} and w.dump_hash() != h0
    w.players[1].formation = 1
    assert w.dump_hash() == h0


def test_replaying_the_command_log_gives_the_same_hash():
    def fresh():
        w = world()
        line(w, n=4, gap=2)
        return w
    a = fresh()
    sa = Simulation(a)
    cmds = {0: [SelectUnits(1, tuple(a.units))], 1: [SetFormation(1, 2)],
            2: [MoveUnits(1, tuple(a.units), (22, 20))], 40: [Stop(1, (UNIT_ID_BASE + 2,))],
            60: [MoveUnits(1, tuple(a.units)[:2], (9, 9)), MoveTo(UNIT_ID_BASE + 4, 15, 15)]}
    for t in range(300):
        sa.step(cmds.get(t, ()))
    b = fresh()
    sb = Simulation(b)
    replay(sb, sa.log, 300)
    assert b.dump_hash() == a.dump_hash() != fresh().dump_hash()
    assert a.groups and a.dump()["groups"]


def test_replay_gives_the_same_hash_when_driven_in_chunks():
    def fresh():
        w = world()
        line(w, n=3, gap=1)
        return w
    a, b = fresh(), fresh()
    sa, sb = Simulation(a), Simulation(b)
    sa.step([MoveUnits(1, tuple(a.units), (25, 25))])
    sb.step([MoveUnits(1, tuple(b.units), (25, 25))])
    for _ in range(200):
        sa.step()
    for _ in range(40):
        for _ in range(5):
            sb.step()
    assert a.dump_hash() == b.dump_hash()


# --- the install --------------------------------------------------------------------------------------------

def test_a_campaign_group_walks_and_replays_to_the_same_hash():
    import pytest
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from helpers import GFS
    if GFS is None:
        pytest.skip("game files not present")
    assets = AssetCache(None)

    def fresh():
        return World.from_map(open_map("10", None), assets)

    a = fresh()
    mine = [u for u in a.units.values() if u.owner == 3][:4]       # player 3: map 10 gives the human player no units
    cx = sum(u.x for u in mine) // len(mine) + 6
    cy = sum(u.y for u in mine) // len(mine)
    sim = Simulation(a)
    sim.step([MoveUnits(3, ids(*mine), (cx, cy)), SetFormation(3, 2)])
    for _ in range(300):
        sim.step()
    assert all(u.mover.dest is not None for u in mine)
    start = {u.id: (u.x, u.y) for u in fresh().units.values()}
    assert any((u.x, u.y) != start[u.id] for u in mine)
    b = fresh()
    replay(Simulation(b), sim.log, 301)
    assert a.dump_hash() == b.dump_hash()
    assert all(u.order in (1, 0xC) for u in mine)
