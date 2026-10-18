"""MoveTo (H2): the move driver with the planners, synthetic worlds, always run.
Spec: docs/engine/simulation.md section 7."""

import numpy as np

from engine.sim import MoveTo, Simulation, replay
from engine.world import UNIT_ID_BASE, Player, Unit, World

EAST = 64


def world(n=32, cost=8):
    w = World(np.zeros((n, n), np.uint16), np.zeros((n, n), np.int8), "syn")
    w._cost = np.full((n, n), cost, np.uint8)
    return w


def wall(w, cells):
    for x, y in cells:
        w._block[y, x] = 5
    w.block_rev += 1


def unit(w, uid, x, y, speed=24, owner=1):
    u = Unit(UNIT_ID_BASE + uid, 1, owner, x, y, uid=uid, hp=10, hp_max=10, facing=EAST, speed_mod=speed)
    u.mover.turn_rate = 32
    w.add_unit(u)
    return u


def run(sim, u, limit=3000, watch=None):
    for n in range(1, limit):
        sim.step()
        if watch:
            watch(sim.world, u)
        if u.order != 1 and not u.mover.step_ticks:
            return n
    raise AssertionError("order never ended")


def test_move_to_straight_arrives_and_stops():
    w = world()
    u = unit(w, 1, 10, 10)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 18, 10)])
    run(sim, u)
    assert (u.x, u.y) == (18, 10) and (u.sub_x, u.sub_y) == (128, 128)
    assert u.action == "idle" and u.state == 0 and not u.path
    assert u.order == 0xC and u.stopped and u.anchor == (18, 10)      # the group pass ended the order (R 4.4)


def test_move_to_walks_around_a_wall_and_never_enters_it():
    w = world()
    wall(w, [(14, y) for y in range(9, 22)])
    u = unit(w, 1, 10, 12)
    sim = Simulation(w)
    seen = []

    def watch(world, unit_):
        assert not world.blocked(unit_.x, unit_.y), (unit_.x, unit_.y)
        seen.append((unit_.x, unit_.y))

    sim.step([MoveTo(u.id, 18, 12)])
    run(sim, u, watch=watch)
    assert (u.x, u.y) == (18, 12)
    assert any(y >= 22 or y < 9 for _, y in seen)           # went round the wall's end


def test_unreachable_target_stops_at_the_fallback_cell_without_error():
    w = world()
    wall(w, [(x, y) for x in range(14, 19) for y in range(14, 19)])       # a solid block
    u = unit(w, 1, 10, 16)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 16, 16)])                        # inside the block
    run(sim, u)
    assert max(abs(u.x - 16), abs(u.y - 16)) == 3           # ring 3 is the first with labelled cells
    assert u.mover.static_path == [] or u.mover.arrived


def test_blocked_target_in_a_closed_pocket_ends_the_order_immediately():
    w = world()
    ring = [(x, y) for x in range(14, 19) for y in range(14, 19) if max(abs(x - 16), abs(y - 16)) == 2]
    wall(w, ring)
    u = unit(w, 1, 10, 16)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 16, 16)])                        # free cell, enclosed: unreachable
    run(sim, u)
    assert (u.x, u.y) != (16, 16)
    assert max(abs(u.x - 16), abs(u.y - 16)) == 3


def test_changing_the_target_forces_a_static_replan():
    w = world()
    u = unit(w, 1, 10, 10)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 20, 10)])
    for _ in range(10):
        sim.step()
    assert u.mover.dest == (20, 10)
    sim.step([MoveTo(u.id, 10, 20)])
    sim.step()
    assert u.mover.dest == (10, 20)
    run(sim, u)
    assert (u.x, u.y) == (10, 20)


def test_hop_plans_avoid_a_standing_unit():
    w = world()
    u = unit(w, 1, 10, 10)
    b = unit(w, 2, 14, 10)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 20, 10)])
    first = list(u.path)
    assert (14, 10) not in first                            # the hop plan routes round the blocker

    def watch(world, unit_):
        assert (unit_.x, unit_.y) != (b.x, b.y)

    run(sim, u, watch=watch)
    assert (u.x, u.y) == (20, 10)


def test_long_walk_replans_the_static_path_after_the_refresh_rate():
    w = world(n=64)
    u = unit(w, 1, 10, 10, speed=40)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 50, 50)])
    top = 0
    plans = 0
    last = u.mover.static_path[:]
    for _ in range(3000):
        sim.step()
        top = max(top, u.mover.consumed)
        if u.mover.consumed == 0 and u.mover.static_path and u.mover.static_path != last[1:]:
            plans += 1
        last = u.mover.static_path[:]
        if u.order != 1:
            break
    assert (u.x, u.y) == (50, 50)
    assert top <= 17                                        # > StaticRefreshRate (16) triggers a re-plan


def test_move_to_is_deterministic_and_replayable():
    def build():
        w = world()
        wall(w, [(14, y) for y in range(9, 22)])
        unit(w, 1, 10, 12)
        unit(w, 2, 12, 20)
        return Simulation(w)

    a, b = build(), build()
    cmds = [MoveTo(UNIT_ID_BASE + 1, 20, 12), MoveTo(UNIT_ID_BASE + 2, 20, 11)]
    a.step(cmds)
    for _ in range(300):
        a.step()
    replay(b, a.log, 301)
    assert a.world.dump_hash() == b.world.dump_hash()


def test_rejected_orders_change_nothing():
    w = world()
    u = unit(w, 1, 10, 10)
    sim = Simulation(w)
    before = w.dump_hash()
    sim.step([MoveTo(999, 12, 12), MoveTo(u.id, 99, 99)])
    assert u.order == 0
    assert w.dump_hash() == before


def test_human_player_unit_searches_without_a_level_limit():
    w = world(n=64)
    w.players[1] = Player(1, 0, human=True)
    wall(w, [(30, y) for y in range(8, 55)])                # long wall, gap at y >= 55
    u = unit(w, 1, 20, 12, speed=40)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 40, 12)])
    assert u.mover.last_plan.found and u.mover.last_plan.limit == 1000
    ai = unit(w, 2, 20, 14, owner=2)
    sim.step([MoveTo(ai.id, 40, 14)])
    sim.step()
    assert not ai.mover.last_plan.found                     # the computer's search stops at dist + 5


def test_dynamic_list_lives_one_step_and_the_static_plan_is_renewed_every_17_cells():
    w = world(n=64)
    u = unit(w, 1, 10, 10, speed=40)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 50, 10)])                        # 40 cells straight
    plans, last = 0, None
    for _ in range(3000):
        sim.step()
        if u.mover.last_plan is not last:
            plans, last = plans + 1, u.mover.last_plan
        if u.mover.step_ticks == 0:
            assert u.path == [] or u.order == 0             # cleared at every step end (FUN_00555b38)
        if u.order != 1:
            break
    assert (u.x, u.y) == (50, 10)
    assert plans == 1 + 40 // 17 + 1 or plans == 1 + 40 // 17    # first plan + a re-plan per 17 hop plans


def test_live_layer_unit_stamps_are_class_specific():
    """FUN_00550de0 stamps 0x40 for ground classes, FUN_00550e12 0x80 for class 3; masks 0x41/0x44 see
    only 0x40, 0x82 only 0x80 (docs/engine/simulation.md 7.3)."""
    from engine.sim.movement import live_cells, unit_stamp
    w = world()
    walker = unit(w, 1, 5, 5)
    ghost = unit(w, 2, 9, 9)
    flyer = unit(w, 3, 12, 12)
    ghost.move_type, flyer.move_type = 2, 3
    assert unit_stamp(walker) == 0x40 and unit_stamp(ghost) == 0x40 and unit_stamp(flyer) == 0x80
    assert live_cells(w, walker) == {(9, 9)}     # the flyer is invisible to ground
    assert live_cells(w, ghost) == {(5, 5)}
    assert live_cells(w, flyer) == set()                                # a flyer sees no ground unit
    other = unit(w, 4, 20, 20)
    other.move_type = 3
    assert live_cells(w, flyer) == {(20, 20)}                           # but sees another flyer


def test_live_layer_holds_footprint_and_entered_cell_of_others_only():
    from engine.sim.movement import live_cells
    w = world()
    me = unit(w, 1, 5, 5)
    big = unit(w, 2, 10, 10)
    big.stats = type("S", (), {"token_size": 2})()
    big.mover.step_target = (11, 10)
    assert live_cells(w, me) == {(x, y) for x in (10, 11, 12) for y in (10, 11)}
    assert (5, 5) not in live_cells(w, me)                              # own footprint released
    big.hp = 0                                                          # a dying unit keeps its stamps (FUN_00510a70)
    assert live_cells(w, me) == {(x, y) for x in (10, 11, 12) for y in (10, 11)}
    w.remove_unit(big.id)                                               # ... until it is removed (FUN_00553891)
    assert live_cells(w, me) == set()


# --- blocker wait (FUN_0056fc69 via FUN_00555411; docs/engine/simulation.md 7.4) ---------------------------

def corridor(human=True, n=32):
    """A one-cell-wide east-west corridor along y = 10 (walls above and below)."""
    w = world(n)
    wall(w, [(x, y) for x in range(n) for y in (9, 11)])
    if human:
        w.players[1] = Player(1, 0, human=True)
    return w


def test_head_on_in_a_one_cell_corridor_nobody_swaps():
    """The exe has no swap: the first unit in list order waits (turns to face the other, brain mode 10 -> 0),
    the second sees a walking blocker too?  No: `a` waits for the walking `b`; `b` re-plans round `a`, finds no way
    and stops at once (failure = order 0xc).  The group pass at tick & 15 == 6 restarts the parked `a`, which now
    sees an idle blocker, finds no way and stops too.  Both end on their cells."""
    w = corridor()
    a = unit(w, 1, 10, 10)
    b = unit(w, 2, 11, 10)                                  # adjacent, facing each other
    b.facing = 192
    sim = Simulation(w)
    sim.step([MoveTo(a.id, 20, 10), MoveTo(b.id, 5, 10)])
    for _ in range(4):
        sim.step()
    assert (a.x, a.y) == (10, 10) and (b.x, b.y) == (11, 10)        # nobody passed
    assert a.mover.parked and a.order == 1 and not a.mover.waiting and a.facing == 64   # the waiting unit idles
    assert b.order == 0xC and b.stopped                              # b: no way, stopped at once (failure)
    while w.tick < 7:                                                # the pass at tick 6 restarts a
        sim.step()
    sim.step()
    assert a.order == 1 and not a.mover.parked                       # restarted: it sees an idle blocker, re-plans
    for _ in range(100):                                             # round it (no way in a corridor): it spins, the
        sim.step()                                                   # order stays 1 and nobody passes
    assert (a.x, a.y) == (10, 10) and (b.x, b.y) == (11, 10) and a.order == 1


def test_blocker_verdicts():
    from engine.sim.movement import blocker_verdict
    w = corridor()
    a = unit(w, 1, 10, 10)
    b = unit(w, 2, 11, 10)
    a.order = b.order = 1
    a.mover.goal = (20, 10)
    assert blocker_verdict(w, a, (11, 10)) == 2             # blocker at a centre in a move mode: wait (the swap code)
    a.mover.goal = (11, 10)
    assert blocker_verdict(w, a, (11, 10)) == 0             # my own destination: never wait
    a.mover.goal = (20, 10)
    b.order = 0
    assert blocker_verdict(w, a, (11, 10)) == 0             # idle blocker: go round
    b.order = 1
    b.mover.parked = True
    assert blocker_verdict(w, a, (11, 10)) == 0             # a parked unit is mode 0
    b.mover.parked, b.sub_x = False, 200
    assert blocker_verdict(w, a, (11, 10)) == 1             # mid-step blocker
    a.mover.step_target = (11, 10)
    assert blocker_verdict(w, a, (11, 10)) == 0             # ... unless I last entered that cell
    a.mover.step_target, b.sub_x, b.hp = None, 128, 0
    assert blocker_verdict(w, a, (11, 10)) == 0             # dead blocker


def test_only_size_one_units_of_the_human_player_wait():
    from engine.sim.movement import blocker_verdict
    w = corridor()
    a = unit(w, 1, 10, 10)
    b = unit(w, 2, 11, 10)
    a.order = b.order = 1
    a.mover.goal = (20, 10)
    assert blocker_verdict(w, a, (11, 10)) == 2
    a.stats = type("S", (), {"token_size": 2})()
    assert blocker_verdict(w, a, (11, 10)) == 0             # size 2: re-plan
    a.stats = None
    w.players[1].human = False
    assert blocker_verdict(w, a, (11, 10)) == 0             # computer player: re-plan


def test_ai_unit_replans_round_a_friend_instead_of_waiting():
    w = world()
    w.players[1] = Player(1, 0, human=False)
    a = unit(w, 1, 10, 10)
    b = unit(w, 2, 11, 10)
    b.order = 1
    sim = Simulation(w)
    sim.step([MoveTo(a.id, 20, 10)])
    assert not a.mover.waiting and not a.mover.parked and a.path
    assert (11, 10) not in a.path
    run(sim, a)
    assert (a.x, a.y) == (20, 10)


def test_human_unit_behind_a_walker_turns_to_it_and_is_restarted_by_the_group_pass():
    w = corridor()
    a = unit(w, 1, 10, 10)
    b = unit(w, 2, 11, 10)
    b.order = 1                                             # b is under a move order (mode 1)
    b.mover.goal = (30, 10)
    sim = Simulation(w)
    a.facing = 128                                          # facing away: a real turn is needed
    sim.step([MoveTo(a.id, 20, 10)])
    assert a.mover.waiting and a.state == 1 and a.action == "turn"
    for _ in range(40):
        if a.mover.parked:
            break
        sim.step()
    assert a.mover.parked and a.facing == 64 and a.action == "idle"
    b.order, b.mover.goal = 0, None                         # b leaves the way
    w.move_unit(b.id, 14, 12, 128, 128)
    while (w.tick & 15) != 5:                               # parked until the pass (tick & 15 == 6) restarts it
        sim.step()
        assert a.mover.parked and (a.x, a.y) == (10, 10)
    sim.step()
    sim.step()
    assert not a.mover.parked                               # R 4.4: FUN_0056c8af, no new command needed
    run(sim, a)
    assert (a.x, a.y) == (20, 10)


# --- list removal rules of FUN_00555dc2 / FUN_00555411 (simulation.md 7.2), one test per rule ---

def _hop_state(static, here=(10, 10), path=()):
    from engine.sim import movement as mv
    w = world(n=64)
    u = unit(w, 1, *here)
    u.mover.static_path = list(static)
    u.mover.tail = static[-1] if static else here
    u.mover.goal = u.mover.dest = u.mover.tail
    u.path = list(path)
    return mv, w, u


def test_hop_plan_pops_the_static_head_when_within_the_lookup_distance_even_for_a_tail_goal():
    mv, w, u = _hop_state([(11, 10), (12, 10), (13, 10)])           # n <= 5: goal = tail; head at d = 1 <= 3
    mv._hop_plan(w, u)
    assert u.mover.static_path == [(12, 10), (13, 10)] and u.mover.last_hop_goal == (13, 10)
    assert u.path[-1] == (13, 10)


def test_hop_plan_keeps_the_static_head_when_it_is_far():
    mv, w, u = _hop_state([(15, 10), (16, 10), (17, 10)])           # d = 5 > 3: no pop
    mv._hop_plan(w, u)
    assert u.mover.static_path == [(15, 10), (16, 10), (17, 10)]


def test_hop_plan_long_plan_aims_at_the_head_when_far_and_at_element_3_when_near():
    far = [(15 + i, 10) for i in range(8)]
    mv, w, u = _hop_state(far)                                      # n = 8 > 5, d = 5 > 3: goal = head, no pop
    mv._hop_plan(w, u)
    assert u.mover.last_hop_goal == (15, 10) and len(u.mover.static_path) == 8
    near = [(11 + i, 10) for i in range(8)]
    mv, w, u = _hop_state(near)                                     # d = 1 <= 3: goal = element 3, then pop
    mv._hop_plan(w, u)
    assert u.mover.last_hop_goal == (14, 10) and u.mover.static_path == near[1:]


def test_hop_plan_with_an_empty_static_plan_pops_nothing_and_fails_on_an_empty_hop():
    mv, w, u = _hop_state([])
    u.mover.tail = (10, 10)
    mv._hop_plan(w, u)                                              # n = 0: tail goal = own cell, nothing planned
    assert u.path == [] and u.mover.static_path == [] and u.mover.failed


def test_empty_hop_fails_only_for_a_tail_goal():
    mv, w, u = _hop_state([(11, 10), (12, 10)])
    for c in ((11, 10), (11, 9), (11, 11), (10, 9), (10, 11), (9, 9), (9, 10), (9, 11)):
        w._block[c[1], c[0]] = 5                                    # boxed in: every hop plan is empty
    wall_rev = w.block_rev + 1
    w.block_rev = wall_rev
    mv._hop_plan(w, u)
    assert not u.path and u.mover.failed                            # n <= 5: goal = tail, list empty -> +0x98
    mv, w2, u2 = _hop_state([(15 + i, 10) for i in range(8)])       # n > 5: head goal, no failure flag
    u2.mover.tail = (22, 10)
    w2._block[10, 14] = 5
    mv.path_grid(w2, 1)
    import engine.sim.movement as m2
    orig = m2.plan_dynamic
    m2.plan_dynamic = lambda *a, **k: orig(*a, **k).__class__(cells=[], reason="fallback")
    try:
        m2._hop_plan(w2, u2)
    finally:
        m2.plan_dynamic = orig
    assert not u2.path and not u2.mover.failed


def test_hop_plan_keeps_the_stale_dynamic_list_behind_the_new_hop():
    mv, w, u = _hop_state([(11, 10), (12, 10), (13, 10)], path=[(9, 9), (8, 8)])
    mv._hop_plan(w, u)                                              # push-front without clearing (FUN_0054e886)
    assert u.path[-2:] == [(9, 9), (8, 8)] and u.path[0] == (11, 10)


def test_hop_plan_too_long_empties_the_whole_dynamic_list(monkeypatch):
    from engine.sim import movement as mv
    from engine.sim.pathfinding import PathResult
    _, w, u = _hop_state([(11, 10), (12, 10)], path=[(9, 9)])
    monkeypatch.setattr(mv, "plan_dynamic", lambda *a, **k: PathResult(cells=[], reason="too long"))
    mv._hop_plan(w, u)
    assert u.path == [] and u.mover.failed


def test_static_replan_clears_the_dynamic_list_and_an_empty_plan_fails_at_the_own_cell():
    from engine.sim import movement as mv
    w = world(n=32)
    u = unit(w, 1, 10, 10)
    u.path = [(11, 10)]
    u.mover.goal = (20, 10)
    mv._static_plan(w, u)
    assert u.path == [] and u.mover.consumed == 0 and u.mover.tail == (20, 10) and not u.mover.failed
    for c in ((11, 10), (11, 9), (11, 11), (10, 9), (10, 11), (9, 9), (9, 10), (9, 11)):
        w._block[c[1], c[0]] = 5
    w.block_rev += 1
    u.mover.goal = (30, 10)
    u.mover.static_path = [(11, 10)]
    mv._static_plan(w, u)
    assert u.mover.static_path == [] and u.mover.failed and u.mover.tail == (10, 10)


def test_arrival_is_the_own_cell_equal_to_the_tail_and_pops_nothing():
    from engine.sim import movement as mv
    w = world(n=32)
    u = unit(w, 1, 14, 10)
    u.mover.goal = u.mover.dest = (14, 10)
    u.mover.goal = (20, 10)
    u.mover.dest = (20, 10)
    u.mover.tail = (14, 10)
    u.mover.static_path = [(14, 10)]
    assert mv._drive(w, u) is False and u.mover.arrived and u.mover.static_path == [(14, 10)]


def test_since_hop_is_a_wrapping_byte():
    from engine.sim import movement as mv
    w = world(n=32)
    u = unit(w, 1, 10, 10)
    u.mover.goal = u.mover.dest = (20, 10)
    u.mover.tail = (20, 10)
    u.mover.static_path = [(11, 10)]
    u.path = [(11, 10)]
    u.mover.since_hop = 255
    mv._drive(w, u)
    assert u.mover.since_hop == 0


# --- cell record / occupant / bit 0x10 / death (docs/engine/simulation.md 7.4, Open question 5) ----------------

def test_previous_cell_is_held_after_the_border_crossing_until_the_step_end():
    """FUN_00554fd2 0x555173: after the move `FUN_0055be86(unit, old cell, 0)` stamps the old cell again; the step
    end (FUN_00555b38) is mode 2 + mode 1 = current cell only."""
    from engine.sim.movement import live_cells
    w = world()
    me = unit(w, 1, 5, 5)
    b = unit(w, 2, 10, 10)
    b.mover.step_from, b.mover.step_target = (10, 10), (11, 10)
    assert live_cells(w, me) == {(10, 10), (11, 10)}                    # before the crossing
    w.move_unit(b.id, 11, 10, 20, 128)                                  # crossed: the unit now stands on (11, 10)
    assert live_cells(w, me) == {(10, 10), (11, 10)}                    # (10, 10) still held
    b.mover.step_from = b.mover.step_target = None                      # step end
    assert live_cells(w, me) == {(11, 10)}


def test_occupant_is_the_unit_whose_current_footprint_holds_the_cell():
    """FUN_00551edb returns rec+4, written by FUN_005503af for the footprint at the unit's own cell only."""
    from engine.sim.movement import _blocker
    w = corridor()
    a = unit(w, 1, 10, 10)
    b = unit(w, 2, 12, 10)
    b.mover.step_from, b.mover.step_target = (12, 10), (11, 10)         # b is entering (11, 10): stamps it, no occupant
    assert _blocker(w, a, (11, 10)) is None
    assert _blocker(w, a, (12, 10)) is b
    w.move_unit(b.id, 11, 10, 20, 128)                                  # crossed: the slot moves, (12, 10) is only stamped
    assert _blocker(w, a, (11, 10)) is b and _blocker(w, a, (12, 10)) is None


def test_occupant_is_the_first_unit_to_enter_the_cell():
    """FUN_005503af: an occupied slot is not overwritten (first come, first served); list order does not matter."""
    from engine.sim.movement import _blocker
    w = world()
    a = unit(w, 1, 5, 5)
    late = unit(w, 2, 20, 20)
    early = unit(w, 3, 21, 20)
    w.move_unit(early.id, 10, 10)
    w.move_unit(late.id, 10, 10)                                        # shares the cell, entered second
    assert _blocker(w, a, (10, 10)) is early
    w.move_unit(early.id, 11, 10)
    assert _blocker(w, a, (10, 10)) is late


def test_flyers_hold_no_occupant_slot_of_the_ground_kind():
    """Class 3 uses rec+8; FUN_00551edb reads rec+4 only, so a flyer is never the verdict's blocker."""
    from engine.sim.movement import _blocker
    w = world()
    a = unit(w, 1, 5, 5)
    f = unit(w, 2, 10, 10)
    f.move_type = 3
    assert _blocker(w, a, (10, 10)) is None


def test_blocker_without_occupant_is_found_among_the_ring_units_leaving_the_cell():
    """FUN_0054ec6a(cell, 1): occupants of the 3x3 whose step began on the cell and who are off-centre -> 2."""
    from engine.sim.movement import blocker_verdict
    w = corridor()
    a = unit(w, 1, 10, 10)
    a.order, a.mover.goal = 1, (20, 10)
    b = unit(w, 2, 12, 10)
    w.move_unit(b.id, 12, 10, 20, 128)
    b.mover.step_from, b.mover.step_target = (11, 10), (12, 10)         # left (11, 10): stamped, no occupant
    assert blocker_verdict(w, a, (11, 10)) == 2
    b.mover.step_from = (13, 10)                                        # began elsewhere: re-plan
    assert blocker_verdict(w, a, (11, 10)) == 0


def test_dead_occupant_still_blocks_but_the_verdict_is_replan():
    """HP < 1 -> verdict 0 (0x56fda0), the stamp stays (no release before removal)."""
    from engine.sim.movement import blocker_verdict, live_cells
    w = corridor()
    a = unit(w, 1, 10, 10)
    b = unit(w, 2, 11, 10)
    a.order = b.order = 1
    a.mover.goal = (20, 10)
    b.hp = 0
    assert (11, 10) in live_cells(w, a) and blocker_verdict(w, a, (11, 10)) == 0
    b.hp = -9                                                           # state 0x10 only at HP <= -10: still there
    assert (11, 10) in live_cells(w, a)


def test_mode_4_blocker_is_judged_like_mode_1():
    """0x56fdd0/0x56fde3: brain mode 1 and 4 share one branch (4 = FUN_0056ea52, follow driver); the model has no
    mode 4, so a move order stands for both (`_mode_move`) and the compare is against the asker's own target."""
    from engine.sim.movement import _mode_move
    w = corridor()
    b = unit(w, 2, 11, 10)
    b.order = 1
    assert _mode_move(b)
