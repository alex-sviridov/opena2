"""Follow, defend and patrol orders, Brain mode 4 and the scripted unit orders (docs/engine/ai.md 14.2; engine/sim/follow.py).  Synthetic, always run."""

from allods2.formats import scenario as S
from engine.sim import Simulation, ai, follow, orders
from engine.sim import triggers as T
from engine.world import DEAD

from test_engine_ai import hero, run, stats as unit_stats, unit, world
from test_engine_triggers import ALWAYS, TRUE, rec, script, setup, trig


def two(ai_on=False, lx=40, scan=6):
    w = world()
    w.ai_on = ai_on
    a = hero(w, 1, 20, 20)
    a.stats = unit_stats(scan)
    b = hero(w, 2, lx, 20)
    g = orders._new_group(w, 1)
    orders._join(w, g, a)
    return w, a, b, g


def test_the_setters_cancel_give_the_order_the_leader_and_the_default_range():
    w, a, b, g = two()
    follow.follow_group(w, g, b, 0)
    assert (a.order, a.leader, a.follow_range, g.order) == (0x11, b.id, 3, 0)
    follow.defend_group(w, g, b, 7)
    assert (a.order, a.follow_range) == (8, 7)
    follow.follow_group(w, g, a, 5)                        # a member that is its own leader stands (FUN_0056dba1)
    assert a.order == 0xC and a.leader == b.id


def test_a_follower_beyond_its_range_takes_mode_4_walks_up_and_stays_in_range():
    w, a, b, g = two()
    follow.follow_group(w, g, b, 4)
    sim = Simulation(w)
    run(sim, 7)                                            # the group pass at tick 6
    assert a.mode_follow and a.follow_target == b.id and a.range == 4
    run(sim, 400)
    assert 2 <= max(abs(a.x - b.x), abs(a.y - b.y)) <= 4
    assert not a.mode_go and a.order == 0x11


def test_the_follower_tracks_a_moving_leader():
    w, a, b, g = two(lx=30)
    follow.follow_group(w, g, b, 3)
    sim = Simulation(w)
    run(sim, 100)
    assert T.teleport(w, b, 38, 20)                        # the leader jumps away
    run(sim, 400)
    assert max(abs(a.x - b.x), abs(a.y - b.y)) <= 3


def test_a_follower_touching_its_leader_steps_range_cells_away():
    w, a, b, g = two(lx=21)
    follow.follow_group(w, g, b, 3)
    sim = Simulation(w)
    run(sim, 7)
    assert a.mode_go and a.mover.goal == (17, 23)          # FUN_00558b92: 3 cells beyond a on the ray from the leader's cell origin (dy > dx: along y)
    assert not a.mode_follow


def test_a_dead_leader_stops_the_follower_at_the_next_pass():
    w, a, b, g = two()
    follow.follow_group(w, g, b, 3)
    b.state = DEAD
    sim = Simulation(w)
    run(sim, 7)
    assert a.order == 0xC and not a.mode_follow


def test_the_other_orders_clear_mode_4():
    w, a, b, g = two()
    follow.follow_group(w, g, b, 3)
    sim = Simulation(w)
    run(sim, 7)
    assert a.mode_follow
    from engine.sim import movement as mv
    mv.set_stand(w, a)
    assert not a.mode_follow


def test_defend_attacks_the_enemy_nearest_to_the_follower_among_those_round_the_leader():
    w = world()
    w.ai_on = True
    a = hero(w, 1, 22, 20)
    b = hero(w, 2, 24, 20)
    near = unit(w, 3, 27, 20, 2, 1)                        # 3 cells from the leader, 5 from the follower
    far = unit(w, 4, 26, 24, 2, 1)                         # 4 cells from the leader, 4 from the follower
    g = orders._new_group(w, 1)
    orders._join(w, g, a)
    follow.defend_group(w, g, b, 6)
    sim = Simulation(w)
    run(sim, 7)
    assert a.mode_attack and a.target == far.id            # FUN_0056a73b: the smallest reach gap to the follower
    assert a.order == 8


def test_defend_without_enemies_runs_the_guard_scan_and_a_close_follower_steps_away():
    w = world()
    w.ai_on = True
    a = hero(w, 1, 20, 20)
    b = hero(w, 2, 21, 20)
    g = orders._new_group(w, 1)
    orders._join(w, g, a)
    follow.defend_group(w, g, b, 3)
    sim = Simulation(w)
    run(sim, 7)
    assert a.mode_go and a.mover.goal == (17, 23)


def test_patrol_walks_between_the_start_cell_and_the_target_and_back():
    w, a, b, g = two()
    follow.patrol_group(w, g, 30, 20)
    assert a.patrol == [(20, 20), (30, 20)] and a.patrol_wp == (30, 20) and a.order == 0xA and a.anchor == (20, 20)
    sim = Simulation(w)
    seen = []
    for _ in range(900):
        sim.step()
        seen.append((a.x, a.y))
    assert (30, 20) in seen and (20, 20) in seen[seen.index((30, 20)):]       # the target, then the start again


def test_patrol_with_the_ai_on_fights_an_enemy_near_its_anchor():
    w = world()
    w.ai_on = True
    a = hero(w, 1, 20, 20)
    a.stats = unit_stats(6)
    e = unit(w, 2, 23, 20, 2, 1)
    g = orders._new_group(w, 1)
    orders._join(w, g, a)
    follow.patrol_group(w, g, 30, 20)
    sim = Simulation(w)
    run(sim, 7)
    assert a.mode_attack and a.target == e.id and not a.patrol_walk


# --- the instant (T§4 group sub-commands 10, 11, 14, 15) -----------------------------------------------------------------------

def cmd(sub, rid, *extra):
    return rec(6, rid, (S.K_CONST, sub), *extra, (S.K_GROUP, 1))


def test_the_scripted_sub_commands_give_the_squad_the_unit_orders():
    sc = script([cmd(15, 1, (S.K_UNIT, 1), (S.K_INT, 5)), cmd(11, 2, (S.K_UNIT, 1), (S.K_INT, 6)), cmd(14, 3, (S.K_X, 30), (S.K_Y, 28)),
                 cmd(10, 4, (S.K_UNIT, 1))], TRUE, [])
    w, sim, h, a, b = setup(sc)
    g = w.ai_groups[(2, 1)]
    T.run_instant(w, w.script, 0)
    assert (a.order, b.order, a.leader, a.follow_range, g.order) == (0x11, 0x11, h.id, 5, 0)
    T.run_instant(w, w.script, 1)
    assert (a.order, a.follow_range) == (8, 6)
    T.run_instant(w, w.script, 2)
    assert (a.order, a.patrol, b.patrol_wp) == (0xA, [(30, 24), (30, 28)], (30, 28)) and g.order == 0
    T.run_instant(w, w.script, 3)
    assert (a.order, a.target, b.order) == (3, h.id, 3)
    assert not w.script.unsupported


def test_an_attack_command_stops_a_member_that_is_the_target():
    w, sim, h, a, b = setup(script([cmd(10, 1, (S.K_UNIT, 2))], TRUE, []))
    T.run_instant(w, w.script, 0)
    assert a.order == 0xC and b.order == 3 and b.target == a.id        # FUN_0056d1be: the target itself stops
