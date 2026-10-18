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
        if u.order == 0 and not u.mover.step_ticks:
            return n
    raise AssertionError("order never ended")


def test_move_to_straight_arrives_and_stops():
    w = world()
    u = unit(w, 1, 10, 10)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 18, 10)])
    run(sim, u)
    assert (u.x, u.y) == (18, 10) and (u.sub_x, u.sub_y) == (128, 128)
    assert u.action == "idle" and u.state == 0 and not u.path and u.mover.goal is None


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
        if u.order == 0:
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
        if u.order == 0:
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
    big.hp = 0
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
    the second sees an idle blocker, re-plans round it, finds no way and stops; both end on their cells."""
    w = corridor()
    a = unit(w, 1, 10, 10)
    b = unit(w, 2, 11, 10)                                  # adjacent, facing each other
    b.facing = 192
    sim = Simulation(w)
    sim.step([MoveTo(a.id, 20, 10), MoveTo(b.id, 5, 10)])
    for _ in range(400):
        sim.step()
    assert (a.x, a.y) == (10, 10) and (b.x, b.y) == (11, 10)        # nobody passed
    assert a.mover.parked and a.order == 1                          # the waiting unit idles, its order stays
    assert not a.mover.waiting and a.facing == 64
    assert not b.mover.parked and b.order == 0                     # b re-planned (no way) and its order ended


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


def test_human_unit_behind_a_walker_turns_to_it_and_stays_parked_until_reordered():
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
    for _ in range(50):
        sim.step()
    assert (a.x, a.y) == (10, 10)                           # still parked: nothing restarts the order
    sim.step([MoveTo(a.id, 20, 10)])                        # a new command does
    assert not a.mover.parked
    run(sim, a)
    assert (a.x, a.y) == (20, 10)
