"""Group orders 1, 2, 5, 0x11, 0x13, 0xff and the G / L / swarm commands (docs/engine/ai.md 14).  Synthetic worlds, always run."""

import copy

from engine.sim import Guard, MoveUnits, Simulation, StandStill, Swarm, replay
from engine.sim import ai
from engine.sim.movement import set_guard
from engine.world import AiGroup
from test_engine_ai import damages, hero, run, unit, world


def squad(w, ids):
    """The AiGroup of computer player 2's squad 1 (after `Simulation(w, ai=True)`)."""
    return w.ai_groups[(2, 1)]


def human_world(enemy_at=None, hero_scan=6, enemy_scan=0, **kw):
    w = world()
    h = unit(w, 1, 20, 24, 1, 0, hp=500, scan=hero_scan, **kw)
    m = unit(w, 2, enemy_at[0], enemy_at[1], 2, 0, hp=500, scan=enemy_scan, lo=0) if enemy_at else None
    return w, h, m


# --- the commands: intake, new group, member orders (FUN_005709d9 / FUN_00570bde / FUN_0057063e) --------------------------------

def test_guard_command_makes_a_group_with_order_1_member_order_0xb_and_the_floor_radius():
    w, h, _ = human_world()
    sim = Simulation(w)
    sim.step([Guard(1, (h.id,))])
    g = w.groups[h.order_group]
    assert g.order == 1 and h.order == 0xB and h.anchor == (20, 24)
    assert (g.radius, g.base) == (10, 10)                       # reach 0 + 6 = 6 < MinimalGuardRange: the floor 10 (G), not 20 (0x12)
    assert not (h.mode_go or h.mode_attack or h.mode_look)


def test_guard_radius_is_the_reach_when_it_exceeds_the_floor():
    w, h, _ = human_world(hero_scan=12)
    sim = Simulation(w)
    sim.step([Guard(1, (h.id,))])
    assert w.groups[h.order_group].radius == 12


def test_guard_in_mid_step_anchors_on_the_cell_being_entered():
    w, h, _ = human_world()
    sim = Simulation(w)
    sim.step([MoveUnits(1, (h.id,), (30, 24))])
    run(sim, 4)
    assert (h.sub_x, h.sub_y) != (128, 128) and h.mover.step_target is not None
    target = h.mover.step_target
    sim.step([Guard(1, (h.id,))])
    assert h.anchor == tuple(target) and h.order == 0xB


def test_stand_still_command_sets_order_0x17_group_0x13_and_never_fights():
    w, h, m = human_world((21, 24))
    sim = Simulation(w, ai=True)
    sim.step([StandStill(1, (h.id,))])
    g = w.groups[h.order_group]
    assert g.order == 0x13 and h.order == 0x17 and h.anchor == (20, 24)
    run(sim, 100)
    assert not h.mode_attack and h.ai.target is None and not [e for e in damages(w) if e.attacker == h.id]


def test_swarm_command_is_a_move_group_with_group_order_5_and_formation_targets():
    w = world()
    a = unit(w, 1, 20, 24, 1, 0)
    b = unit(w, 2, 21, 25, 1, 0)
    sim = Simulation(w)
    sim.step([Swarm(1, (a.id, b.id), (30, 30))])
    g = w.groups[a.order_group]
    assert g.order == 5 and g.target == (30, 30) and b.order_group == g.id
    assert a.order == 1 and b.order == 1                        # order 1 (move) like cmd 0x16, formation offsets kept
    assert a.mover.goal == (29, 29) and b.mover.goal == (30, 30)   # rigid shape round the truncated centroid (21, 25)
    assert g.speed != 0


def test_swarm_with_nobody_to_fight_walks_and_stops_like_a_move_group_even_with_the_ai_off():
    w = world()
    a = unit(w, 1, 20, 24, 1, 0)
    sim = Simulation(w)
    sim.step([Swarm(1, (a.id,), (24, 24))])
    run(sim, 200)
    assert (a.x, a.y) == (24, 24) and a.stopped


def test_swarm_attacks_what_it_sees_on_the_way_and_resumes_the_walk_when_the_pool_is_empty():
    w, h, m = human_world((24, 24), hero_scan=6)
    sim = Simulation(w, ai=True)
    sim.step([Swarm(1, (h.id,), (40, 24))])
    run(sim, 8)                                                 # tick 6 is the pass
    assert h.mode_attack and h.ai.target == m.id and h.order == 1
    w.remove_unit(m.id)
    run(sim, 20)
    assert h.mode_go and not h.mode_attack and h.mover.goal == (39, 24)   # clamped to size - 9


# --- the handlers ---------------------------------------------------------------------------------------------------------------

def test_guard_pass_attacks_inside_the_radius_and_returns_to_the_post_without_the_stamp_table():
    w, h, m = human_world((24, 24), hero_scan=6, enemy_scan=0)
    sim = Simulation(w, ai=True)
    sim.step([Guard(1, (h.id,))])
    run(sim, 8)
    assert h.mode_attack and h.ai.target == m.id
    h.x, h.y = 20, 24                                           # stays; now pull the target away
    w.remove_unit(m.id)
    far = unit(w, 3, 40, 24, 2, 0, hp=500, scan=0, lo=0)
    h.mover.goal, h.mode_go = None, False
    h.ai.stamp = (w.tick + 1) >> 4                              # a fresh failure stamp: order 0x12 would go to hit_cell, order 1 ignores it
    run(sim, 16)
    assert far.id not in (h.ai.target,)
    assert h.mover.goal != (0, 0)


def test_guard_pass_ignores_a_hostile_beyond_the_radius():
    w, h, m = human_world((33, 24), hero_scan=14)               # 13 cells away: inside the sight (14), radius 14 -> 17..19 after the first pass
    sim = Simulation(w, ai=True)
    sim.step([Guard(1, (h.id,))])
    g = w.groups[h.order_group]
    run(sim, 8)
    assert h.ai.target == m.id and 17 <= g.radius <= 19
    g.radius = 5                                                # shrink the pool: the hostile is outside it now
    g.seen = 1
    run(sim, 16)
    assert h.ai.target is None


def test_hold_pass_walks_to_the_destination_idles_there_and_fights_without_a_radius():
    w, h, m = human_world((45, 24), hero_scan=6)
    sim = Simulation(w, ai=True)
    run(sim, 2)
    ai.set_group_order(w, w.groups[h.order_group], 2, (28, 24))
    assert w.groups[h.order_group].order == 2 and w.groups[h.order_group].target == (28, 24)
    run(sim, 14)
    assert h.mode_go and h.mover.goal == (28, 24) and h.order == 0xC       # members keep their order
    run(sim, 300)
    assert (h.x, h.y) == (28, 24) and not h.mode_go and not h.mode_attack
    w.move_unit(m.id, 33, 24)
    run(sim, 20)
    assert h.mode_attack and h.ai.target == m.id


def test_stand_still_pass_idles_every_member_and_ignores_enemies():
    w = world()
    a = unit(w, 1, 20, 24, 2, 1, scan=6)
    unit(w, 2, 21, 24, 1, 0, hp=500, scan=0, lo=0)
    sim = Simulation(w, ai=True)
    ai.set_group_order(w, squad(w, None), 0x13)
    run(sim, 100)
    assert a.order == 0x17 and a.mode_look and not a.mode_attack and a.ai.target is None


def test_empty_group_order_0xff_runs_the_guard_scan_for_each_member():
    w = world()
    a = unit(w, 1, 20, 24, 2, 1, scan=6, rng=1)
    unit(w, 2, 21, 24, 1, 0, hp=500, scan=0, lo=0)
    sim = Simulation(w, ai=True)
    run(sim, 2)
    squad(w, None).order = 0xFF
    run(sim, 8)
    assert a.mode_attack                                        # FUN_0056afac(m, 0) = FUN_0056a1fb: an adjacent enemy is engaged


def test_an_emptied_squad_is_forced_to_0xff():
    w = world()
    a = unit(w, 1, 20, 24, 2, 1)
    sim = Simulation(w, ai=True)
    w.remove_unit(a.id)
    run(sim, 8)
    assert squad(w, None).order == 0xFF


def test_set_group_order_accepts_every_scripted_order_and_rejects_the_rest():
    w, h, _ = human_world()
    sim = Simulation(w, ai=True)
    g = w.groups[h.order_group]
    for order, target in ((1, 0), (2, (30, 30)), (3, None), (4, (30, 30)), (5, (30, 30)), (0x11, None), (0x12, 0), (0x13, None)):
        ai.set_group_order(w, g, order, target)
        assert g.order == order
    try:
        ai.set_group_order(w, g, 9)
    except ValueError:
        pass
    else:
        raise AssertionError


def test_find_squad_returns_the_ai_group_or_the_humans_command_group():
    w, h, m = human_world((30, 24))
    Simulation(w, ai=True)
    assert ai.find_squad(w, 2, 0) is w.ai_groups[(2, 0)]
    assert ai.find_squad(w, 1, 0) is w.groups[h.order_group]
    assert ai.find_squad(w, 3, 0) is None


def test_group_order_of_a_unit():
    w, h, m = human_world((30, 24))
    Simulation(w, ai=True)
    assert ai.group_order(w, h) == 3 and ai.group_order(w, m) == 0x12


# --- wander (FUN_00572ec4 / FUN_005708ff) ---------------------------------------------------------------------------------------

def wander_world(seed=3):
    w = world(64, seed=seed)
    a = unit(w, 1, 30, 30, 2, 1, scan=0)
    b = unit(w, 2, 31, 30, 2, 1, scan=0)
    sim = Simulation(w, ai=True)
    return w, sim, a, b


def test_wander_starts_on_the_first_members_cell_and_retargets_20_cells_away_by_the_exes_dice():
    w, sim, a, b = wander_world()
    g = squad(w, None)
    ai.set_group_order(w, g, 0x11)
    assert g.order == 0x11 and g.target == (30, 30) and g.counter == 0
    dice = copy.deepcopy(w.rng)
    run(sim, 7)                                                 # the pass at tick 6
    k = dice.rand(7)
    assert g.target == (30 + 20 * ai.WANDER_DX[k], 30 + 20 * ai.WANDER_DY[k]) and g.counter == 1
    assert a.mover.goal == (0, 0)                               # the members' own destinations (brain+0xa) were never set: cell word 0


def test_wander_redraws_until_the_cell_is_inside_the_playable_rectangle():
    w = world(64, seed=3)
    a = unit(w, 1, 10, 10, 2, 1, scan=0)                        # 10 - 20 < 8: the up / left directions are outside
    sim = Simulation(w, ai=True)
    g = squad(w, None)
    ai.set_group_order(w, g, 0x11)
    dice = copy.deepcopy(w.rng)
    run(sim, 7)
    while True:
        k = dice.rand(7)
        x, y = 10 + 20 * ai.WANDER_DX[k], 10 + 20 * ai.WANDER_DY[k]
        if 8 <= x <= 55 and 8 <= y <= 55:
            break
    assert g.target == (x, y) and a.id in g.members


def test_wander_keeps_its_target_until_the_members_get_close_or_the_counter_runs_out():
    w, sim, a, b = wander_world()
    g = squad(w, None)
    ai.set_group_order(w, g, 0x11)
    g.target, g.counter = (50, 30), 5                            # 20 away, counter low: no retarget
    run(sim, 7)
    assert g.target == (50, 30) and g.counter == 6
    g.counter = 0x33                                            # above 0x32: retarget even though far
    run(sim, 16)
    assert g.target != (50, 30) and g.counter == 1


def test_wander_replays_to_the_same_hash():
    def go():
        w, sim, a, b = wander_world(seed=9)
        ai.set_group_order(w, squad(w, None), 0x11)
        run(sim, 700)
        return sim

    s1, s2 = go(), go()
    assert s1.world.dump_hash() == s2.world.dump_hash()
    g = squad(s1.world, None)
    assert g.order == 0x11 and g.counter > 0
    w, sim, a, b = wander_world(seed=9)
    ai.set_group_order(w, squad(w, None), 0x11)
    replay(sim, s1.log, 700)
    assert sim.world.dump_hash() == s1.world.dump_hash()


def test_human_wander_group_with_the_ai_off_still_walks():
    w = world(64)
    a = unit(w, 1, 30, 30, 1, 0)
    sim = Simulation(w)
    sim.step([StandStill(1, (a.id,))])
    ai.set_group_order(w, w.groups[a.order_group], 0x11)
    run(sim, 40)
    assert a.mover.goal is not None                             # the group pass ran (swarm with an empty pool: the move pass)


# --- gating: the AI-off world is unchanged -------------------------------------------------------------------------------------

def test_the_new_group_orders_change_nothing_without_the_ai_except_swarm_and_wander():
    w, h, m = human_world((21, 24))
    sim = Simulation(w)
    sim.step([Guard(1, (h.id,))])
    run(sim, 60)
    assert not h.mode_attack and not damages(w)


def test_ai_group_dump_keeps_the_old_layout_for_order_0x12_and_grows_for_a_scripted_order():
    g = AiGroup((2, 1))
    d = g.dump()
    g.order = 1
    assert len(g.dump()) == len(d) + 3


def test_set_guard_without_a_step_target_uses_the_own_cell():
    w, h, _ = human_world()
    h.sub_x = 40
    set_guard(w, h)
    assert h.anchor == (20, 24)
