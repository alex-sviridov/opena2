"""Monster AI (I3): the squad group handler, sight, target score, hit reaction, flee, determinism.  Synthetic worlds, always run.
Spec: docs/engine/ai.md (A§ = its sections)."""

import argparse

import pytest
import numpy as np

from allods2.formats.unitstats import MONSTER, UnitType
from engine.sim import MoveUnits, Simulation, replay
from engine.sim import ai
from engine.sim.combatstats import ArmourBlock, AttackRecord, CombatStats
from engine.world import UNIT_ID_BASE, Damage, Player, Unit, World

EAST = 64


def world(n=48, seed=1, heights=None):
    h = np.zeros((n, n), np.int8) if heights is None else heights
    w = World(np.zeros((n, n), np.uint16), h, "syn", seed=seed)
    w._cost = np.full((n, n), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True, relations=(18,) + (1,) * 15)
    w.players[2] = Player(2, 1, relations=(1, 18) + (0,) * 14)
    w.players[3] = Player(3, 2, relations=(1, 0, 18) + (0,) * 13)
    w.ai_sleep = False                  # the sleep gate (A§15) is tested on its own; the other tests keep the squads awake
    return w


def stats(scan=6, mind=10, wimpy=0, withdraw=0, token=1, move=1, speed=24):
    return UnitType(MONSTER, 1, "Test", 1, 1, {"scan_range": scan, "mind": mind, "wimpy": wimpy, "withdraw": withdraw,
                                                 "token_size": token, "movement_type": move, "speed": speed, "turn_rate": 32}, (), ())


def unit(w, uid, x, y, owner, squad=0, hp=40, scan=6, speed=24, lo=3, windup=6, recovery=4, rng=1, **kw):
    u = Unit(UNIT_ID_BASE + uid, 1, owner, x, y, uid=uid, hp=hp, hp_max=hp, facing=EAST, squad=squad,
             stats=stats(scan, speed=speed, **kw))
    u.mover.turn_rate = 32
    u.combat = CombatStats(AttackRecord(skill=500, lo=lo, sp=0), ArmourBlock(0, 0), windup=windup, recovery=recovery, range=rng)
    w.add_unit(u)
    return u


def hero(w, uid, x, y, **kw):
    return unit(w, uid, x, y, 1, 0, hp=500, scan=0, **kw)


def damages(w):
    return [e for e in w.fight_log if isinstance(e, Damage)]


def ai_log(sim):
    return [(t, c) for t, c in sim.log if getattr(c, "ai", False)]


def run(sim, n):
    for _ in range(n):
        sim.step()


# --- sight (A§4.1) --------------------------------------------------------------------------------------------------------------

def test_sight_on_flat_ground_reaches_the_scan_range_straight_and_less_diagonally():
    w = world()
    cells = ai.sight(w, 24, 24, 6)
    assert (30, 24) in cells and (31, 24) not in cells          # (6 << 7) + 64 - 6 * 128 = 64 > 0; the seventh cell is dark
    assert (24, 18) in cells and (24, 17) not in cells
    assert (28, 28) in cells and (29, 29) not in cells          # a diagonal step costs 181: 832 - 4 * 181 = 108 > 0, 5 * 181 > 832


def test_a_ridge_higher_than_the_observer_shortens_the_sight_and_lower_ground_lengthens_it():
    h = np.zeros((48, 48), np.int8)
    h[:, 27:29] = 127
    w = world(heights=h)
    cells = ai.sight(w, 24, 24, 6)
    assert (28, 24) in cells and (29, 24) not in cells and (30, 24) not in cells        # 576 - 255 - 255 < 0 two cells into the ridge
    assert (30, 24) in ai.sight(world(), 24, 24, 6)
    h2 = np.zeros((48, 48), np.int8)
    h2[:, 28:] = -50
    w2 = world(heights=h2)
    assert (31, 24) in ai.sight(w2, 24, 24, 6) and (33, 24) not in ai.sight(w2, 24, 24, 6)         # downhill adds light


def test_sight_stays_inside_the_playable_area():
    w = world()
    cells = ai.sight(w, 10, 24, 20)
    assert all(8 <= x <= 48 - 9 for x, _ in cells) and min(x for x, _ in cells) == 8


# --- target score (A§5) ---------------------------------------------------------------------------------------------------------

def test_score_is_distance_then_facing_and_a_melee_walker_never_targets_a_flyer():
    w = world()
    me = unit(w, 1, 20, 20, 2, 1)
    near, far = hero(w, 2, 22, 20), hero(w, 3, 25, 20)
    assert ai.score(w, me, near) < ai.score(w, me, far)
    assert ai.score(w, me, near) == 2 * 256 + 0                  # facing east: octant of an eastern target is 64
    fly = hero(w, 4, 21, 20, move=3)
    fly.move_type = 3
    assert ai.score(w, me, fly) == ai.NO_TARGET


def test_a_small_clever_unit_scores_ranged_walkers_better_and_ghosts_worse():
    w = world()
    me = unit(w, 1, 20, 20, 2, 1, mind=15)
    archer = hero(w, 2, 24, 20, rng=4)
    ghost = hero(w, 3, 24, 21, move=2)
    ghost.move_type = 2
    plain = 4 * 256 + ai.mv._fold(me.facing, ai.cb.octant(ai.foot(me), ai.foot(archer)) & 255)
    assert ai.score(w, me, archer) == plain - (plain >> 2)
    base = 4 * 256 + ai.mv._fold(me.facing, ai.cb.octant(ai.foot(me), ai.foot(ghost)) & 255)
    assert ai.score(w, me, ghost) == base + (base >> 1)


# --- noticing, chasing, attacking, returning ---------------------------------------------------------------------------------

def test_the_hero_inside_the_scan_range_is_attacked_after_the_next_pass():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1)
    h = hero(w, 2, 25, 20)
    sim = Simulation(w, ai=True)
    run(sim, 6)
    assert m.ai.target is None and not m.mode_attack               # the first pass is at tick 6, not before
    sim.step()
    assert m.ai.target == h.id and m.mode_attack and m.target == h.id
    run(sim, 200)
    assert damages(w) and damages(w)[0].attacker == m.id


def test_a_hero_outside_the_scan_range_is_ignored():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1)
    hero(w, 2, 28, 20)                                           # 8 cells: dark
    sim = Simulation(w, ai=True)
    run(sim, 200)
    assert m.ai.target is None and not damages(w) and (m.x, m.y) == (20, 20)
    assert not any(isinstance(c, ai.AttackUnit) for _, c in sim.log)


def test_the_monster_returns_to_its_post_after_the_hero_outruns_its_sight():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1)
    h = hero(w, 2, 25, 20, speed=32)
    sim = Simulation(w, ai=True)
    run(sim, 8)
    assert m.mode_attack
    sim.step([MoveUnits(1, (h.id,), (44, 20))])
    far = 0
    for _ in range(300):
        sim.step()
        far = max(far, m.x)
    assert far > 22                                               # it chased
    run(sim, 700)
    assert (m.x, m.y) == (20, 20) and m.ai.target is None
    assert m.mode_look                                            # back on the post it looks around again


def test_an_alert_reaches_the_whole_squad_but_not_another_squad():
    w = world()
    a = unit(w, 1, 20, 20, 2, 1)
    b = unit(w, 2, 20, 30, 2, 1)                                  # 10 cells from a: out of its own sight
    c = unit(w, 3, 20, 31, 2, 7)                                  # another squad
    h = hero(w, 4, 24, 20)
    sim = Simulation(w, ai=True)
    run(sim, 7)
    assert a.ai.target == h.id and b.ai.target == h.id and b.mode_attack
    assert c.ai.target is None and not c.mode_attack


def test_a_hostile_beyond_the_pool_radius_is_ignored_even_when_visible():
    w = world()
    a = unit(w, 1, 12, 20, 2, 1, scan=20)                        # sees far
    b = unit(w, 2, 12, 21, 2, 1, scan=0)
    hero(w, 3, 12 + 19, 20)                                      # inside a's sight window (19 rings) and the pool radius 21
    sim = Simulation(w, ai=True)
    g = w.ai_groups[(2, 1)]
    assert g.radius == 21 and g.base == 21                   # centroid (12, 21): the sub-cell mean rounds the cell up; 1 + 20
    run(sim, 7)
    assert a.ai.target is not None                               # 19 <= 20: inside


# --- rates and quirks ---------------------------------------------------------------------------------------------------------

def test_the_ai_thinks_every_sixteen_ticks_starting_at_tick_six():
    w = world()
    unit(w, 1, 20, 20, 2, 1)
    h = hero(w, 2, 40, 20)
    sim = Simulation(w, ai=True)
    run(sim, 100)
    w.move_unit(h.id, 24, 20)                                    # appears in the sight window at tick 100
    run(sim, 40)
    pass_ticks = [t for t, c in ai_log(sim)]
    assert pass_ticks and all(t & 15 == 6 for t in pass_ticks)
    assert pass_ticks[0] == 6 or min(t for t in pass_ticks if t >= 100) == 102          # reaction at the next pass after tick 100


def test_the_pool_radius_is_the_reach_floored_at_twenty_then_grows_once_by_three_to_five():
    w = world()
    for i, (x, y) in enumerate([(20, 20), (20, 29)]):
        unit(w, i + 1, x, y, 2, 1)
    g = None
    sim = Simulation(w, ai=True)
    g = w.ai_groups[(2, 1)]
    assert g.base == g.radius == 14 + 6 - 4 or g.base == g.reach               # centroid (20, 24), spread 5, reach 5 + 6 = 11
    assert g.reach == 11 and g.radius == 11
    run(sim, 7)
    assert g.radius in (14, 15, 16) and g.seen == 1               # base 11 + 4 + rand(-1..1)
    r = g.radius
    run(sim, 100)
    assert g.radius == r


def test_a_hit_unit_without_a_target_runs_ten_cells_away_from_its_attacker():
    w = world(64)
    m = unit(w, 1, 40, 24, 2, 1, scan=0)
    shooter = hero(w, 2, 10, 24)                                 # 30 cells away: revealed by the hit mark but beyond the pool radius
    sim = Simulation(w, ai=True)
    ai.on_hit(w, shooter, m)
    assert m.ai.hit_cell == ai.word(50, 24) and m.ai.alerted == 1 and m.ai.mark_cell == ai.word(10, 24)
    m.hp = 30
    run(sim, 7)
    assert m.ai.target is None and m.mode_go and m.mover.goal == (50, 24)    # damaged, hit just now, no target: it goes there


def test_a_never_hit_unit_with_a_fresh_failure_stamp_goes_to_the_raw_cell_zero_without_clamp():
    """ai.md 3 (CONFIRMED): the ctor leaves +0x9c = 0, so a stamp on a never-hit unit sends it to cell (0, 0); the exe feeds the raw cell to the
    planner (the static plan takes the nearest reached ring cell), nothing clamps it."""
    w = world(64)
    m = unit(w, 1, 30, 30, 2, 1, scan=0)
    sim = Simulation(w, ai=True)
    assert m.ai.hit_cell == 0 and m.ai.stamp == 0xFFDC
    m.ai.stamp = (w.tick >> 4) & 0xFFFF
    run(sim, 7)
    assert m.mode_go and m.mover.goal == (0, 0)
    run(sim, 20)
    assert m.x < 30 and m.y < 30                                 # walks towards the corner as far as the plan goes


def test_the_attacker_cell_is_revealed_to_the_squad_for_twenty_one_passes():
    w = world()
    a = unit(w, 1, 24, 24, 2, 1, scan=0)
    b = unit(w, 2, 24, 26, 2, 1, scan=0)
    shooter = hero(w, 3, 30, 24)                                  # nobody sees it
    sim = Simulation(w, ai=True)
    ai.on_hit(w, shooter, a)
    run(sim, 7)
    assert a.ai.target == shooter.id and b.ai.target == shooter.id
    for _ in range(25):
        run(sim, 16)
    assert a.ai.mark_cell == 0 and a.ai.target is None


def test_flee_cell_is_three_cells_beyond_on_the_ray_from_the_enemies_and_clamped():
    w = world()
    me = unit(w, 1, 20, 20, 2, 1)
    foe = hero(w, 2, 17, 20)
    assert ai.flee_cell(w, me, [foe]) == ai.word(23, 20)
    me2 = unit(w, 3, 9, 9, 2, 5)
    foe2 = hero(w, 4, 12, 12)
    assert ai.flee_cell(w, me2, [foe2]) == ai.word(8, 8)         # 6 cells away is clamped to the border


def test_a_wimpy_monster_with_a_hostile_in_range_steps_away_every_pass():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1, hp=40, wimpy=10)
    m.hp = 8
    hero(w, 2, 24, 20)
    sim = Simulation(w, ai=True)
    run(sim, 7)
    assert m.mode_go and m.mover.goal == (17, 20)


def test_the_idle_look_around_turns_rarely_and_at_once_after_a_hit():
    w = world()
    m = unit(w, 1, 24, 24, 2, 1)
    sim = Simulation(w, ai=True)
    run(sim, 7)
    assert m.mode_look
    faces = set()
    for _ in range(3000):
        sim.step()
        faces.add(m.facing)
    assert 5 < len(faces)                                         # it turned many times over 3000 ticks, a few dozen turns
    m.ai.alerted = 1
    f = m.mover.target_facing
    sim.step()
    assert m.ai.alerted == 0 and m.mover.target_facing != f


# --- determinism and the log (A§10) -------------------------------------------------------------------------------------------

def crowd():
    w = world(64, seed=5)
    for i in range(10):
        unit(w, i + 1, 10 + (i % 5) * 4, 12 + (i // 5) * 5, 2, 1 + i // 3)
    h = hero(w, 20, 17, 15, speed=40)
    return w, h


def run_crowd(ticks=500):
    w, h = crowd()
    sim = Simulation(w, ai=True)
    run(sim, ticks // 2)
    sim.step([MoveUnits(1, (h.id,), (40, 40))])            # the hero stood among them, now it leaves
    run(sim, ticks - ticks // 2)
    return sim


def test_ten_monsters_replay_to_the_same_hash():
    a = run_crowd()
    b = run_crowd()
    assert a.world.dump_hash() == b.world.dump_hash()
    assert damages(a.world)                                        # the scenario fights
    w, h = crowd()
    c = Simulation(w, ai=True)
    replay(c, [(t, cmd) for t, cmd in a.log], 501)
    assert c.world.dump_hash() == a.world.dump_hash()


def test_every_ai_action_is_logged_with_the_ai_flag_and_replays_from_the_log_alone():
    a = run_crowd(300)
    logged = ai_log(a)
    assert logged
    w, h = crowd()
    c = Simulation(w, ai=True)
    replay(c, a.log, 301)
    assert ai_log(c) == logged


def test_the_ai_is_opt_in_and_changes_nothing_when_off():
    w, h = crowd()
    ref = w.dump_hash()
    sim = Simulation(w)
    run(sim, 100)
    assert not w.ai_on and "ai" not in w.dump() and not sim.log
    assert all(u.x == u.x for u in w.units.values()) and ref != ""


# --- the debug overlay (A§10) ---------------------------------------------------------------------------------------------------

def test_overlay_reports_the_sight_ring_post_target_and_mode_of_a_selected_monster():
    w = world(96)
    m = unit(w, 1, 40, 40, 2, 1)
    h = hero(w, 2, 44, 40)
    sim = Simulation(w, ai=True)
    run(sim, 7)
    info = ai.overlay(w, m)
    assert (46, 40) in info["sight"] and (47, 40) not in info["sight"]          # the aggro area: 6 cells on flat ground
    g = w.ai_groups[(2, 1)]
    assert (40 + g.radius, 40) in info["ring"] and (40 - g.radius, 40 + g.radius) in info["ring"]
    assert info["post"] == (40, 40) and info["target"] == (44, 40)
    assert info["label"].startswith("attack order 0xb t=2 R=%d" % g.radius)
    assert ai.overlay(w, h) is None                                               # the hero is in no squad


def test_the_ai_debug_flag_parses_and_the_draw_list_draws_the_overlay():
    from allods2.assets import AssetCache
    from engine.ui import DebugFlags
    from engine.view import Camera, DrawOptions, build_draw_list
    flags = DebugFlags.parse("ai")
    assert flags.ai and flags.any()
    w = world(96)
    m = unit(w, 1, 40, 40, 2, 1)
    hero(w, 2, 44, 40)
    sim = Simulation(w, ai=True)
    run(sim, 7)
    cam = Camera(2400, 1900, w.width, w.height, 10 * 32, 10 * 32)             # cells 10..85 are in view
    opts = DrawOptions(units=False, objects=False)
    items = build_draw_list(w, cam, 7, AssetCache(None), opts, flags, (m.id,), None, ai_info={m.id: ai.overlay(w, m)})
    kinds = {i.kind for i in items}
    assert {"ai_sight", "ai_radius", "ai_post", "ai_target", "ai_text"} <= kinds
    plain = build_draw_list(w, cam, 7, AssetCache(None), opts, flags, (m.id,), None)
    assert not {i.kind for i in plain} & {"ai_sight", "ai_text"}                  # no info, no overlay


# --- the dead list server+0xa88 (A§4 step 6) ---------------------------------------------------------------------------------

def test_a_dying_body_is_a_target_only_when_no_living_enemy_is_in_the_pool():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1)
    body = hero(w, 2, 24, 20)
    body.hp = -3                                                  # dying, still in the world (death.py keeps it until HP < -9)
    living = hero(w, 3, 25, 20)
    cells = {(24, 20), (25, 20)}
    assert [u.id for u in ai._hostiles_on(w, 2, cells)] == [living.id]
    assert [u.id for u in ai._hostiles_on(w, 2, {(24, 20)})] == [body.id]       # empty pool: the 0xa88 list is added back
    assert ai._hostiles_on(w, 2, {(30, 30)}) == []


def test_a_monster_keeps_attacking_the_body_of_the_last_hero():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1)
    body = hero(w, 2, 24, 20)
    body.hp = -3
    body.hp_max = 500
    sim = Simulation(w, ai=True)
    run(sim, 7)
    assert m.ai.target == body.id


def test_a_hit_between_neutral_owners_declares_war_both_ways_but_not_between_allies():
    w = world()
    w.players[3].relations = (0, 0, 18) + (0,) * 13
    w.players[2].relations = (0, 18, 0) + (0,) * 13
    a = unit(w, 1, 20, 20, 2, 1)
    b = unit(w, 2, 21, 20, 3, 2)
    ai.on_hit(w, a, b)
    assert w.players[2].relations[2] & 1 and w.players[3].relations[1] & 1
    w.players[2].relations = (0, 18, 2) + (0,) * 13                # allied: bits 0..1 non-zero, left alone
    w.players[3].relations = (0, 2, 18) + (0,) * 13
    ai.on_hit(w, a, b)
    assert w.players[2].relations[2] == 2 and w.players[3].relations[1] == 2


# --- the human's stand-ground pass (group order 3, FUN_0057309d; A§14) --------------------------------------------------------

def _stand_world(gap, hero_rng=1, mon_scan=0):
    w = world()
    h = unit(w, 1, 20, 24, 1, 0, hp=500, scan=6, rng=hero_rng)
    m = unit(w, 2, 20 + gap, 24, 2, 0, hp=500, scan=mon_scan, lo=0)
    return w, h, m


def test_human_squads_start_in_a_stand_ground_group_when_the_ai_is_on():
    w, h, m = _stand_world(1)
    assert not w.groups
    Simulation(w, ai=True)
    g = w.groups[h.order_group]
    assert g.order == 3 and g.members == [h.id] and h.order == 0xC
    assert m.order_group == 0                       # the monster squad is an AI group, not a command group


def test_a_stand_ground_melee_unit_attacks_an_adjacent_hostile_at_the_next_pass():
    w, h, m = _stand_world(1)
    sim = Simulation(w, ai=True)
    run(sim, 6)
    assert not h.mode_attack                        # tick & 15 == 6 has not come yet
    run(sim, 2)
    assert h.mode_attack and h.ai.target == m.id
    run(sim, 60)
    assert any(e.attacker == h.id and e.target == m.id for e in damages(w))
    assert h.order == 0xC                           # the stand order is untouched (brain mode 5 only)


def test_a_stand_ground_melee_unit_ignores_a_hostile_that_is_visible_but_not_adjacent():
    w, h, m = _stand_world(3)
    sim = Simulation(w, ai=True)
    run(sim, 80)
    assert not damages(w) and not h.mode_attack and h.ai.target is None
    assert (h.x, h.y) == (20, 24)                   # and it does not walk after it (no guard scan, no chase)


def test_a_stand_ground_ranged_unit_attacks_a_hostile_inside_its_range_only():
    w, h, m = _stand_world(3, hero_rng=4)
    sim = Simulation(w, ai=True)
    run(sim, 8)
    assert h.mode_attack and h.ai.target == m.id
    w2, h2, m2 = _stand_world(5, hero_rng=4)
    run(Simulation(w2, ai=True), 80)
    assert not h2.mode_attack and h2.ai.target is None


def test_score_stand_cuts_off_what_is_not_in_reach_and_keeps_the_facing_term():
    w, h, m = _stand_world(1)
    s = ai.score_stand(w, h, m)
    assert s == ai.score(w, h, m) or s in (2 * ai.score(w, h, m), ai.score(w, h, m) >> 1)   # the preference clause differs
    assert s < 2 * 256 * 2                          # distance 1: one row of 256 (times the preference factor) plus the facing change
    far = unit(w, 3, 25, 24, 2, 0, scan=0)
    assert ai.score_stand(w, h, far) == ai.NO_TARGET and ai.score(w, h, far) != ai.NO_TARGET


def test_a_stand_ground_unit_whose_target_left_returns_to_brain_mode_zero():
    w, h, m = _stand_world(1)
    sim = Simulation(w, ai=True)
    run(sim, 8)
    assert h.mode_attack
    w.remove_unit(m.id)
    run(sim, 16)
    assert not h.mode_attack and not h.mode_look and not h.mode_go


def test_a_unit_that_stopped_after_a_move_scans_for_enemies_every_pass_group_order_4():
    w = world()
    h = unit(w, 1, 20, 24, 1, 0, hp=500, scan=6)
    sim = Simulation(w, ai=True)
    sim.step([MoveUnits(1, (h.id,), (22, 24))])
    run(sim, 100)
    assert h.stopped and (h.x, h.y) == (22, 24)
    m = unit(w, 2, 23, 24, 2, 0, hp=500, scan=0, lo=0)
    run(sim, 40)
    assert any(e.attacker == h.id and e.target == m.id for e in damages(w))


def test_nothing_changes_for_the_human_when_the_ai_is_off():
    w, h, m = _stand_world(1)
    sim = Simulation(w)
    run(sim, 100)
    assert not damages(w) and not w.groups and not h.mode_attack


def test_easy_difficulty_halves_the_wimpy_threshold():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1, hp=40, wimpy=10)
    m.hp, m.tweak = 8, 1                                          # 8 > 10 >> 1: not wimpy any more
    hero(w, 2, 24, 20)
    sim = Simulation(w, ai=True)
    run(sim, 7)
    assert not (m.mode_go and m.mover.goal == (17, 20))
    m.hp = 5
    run(sim, 16)
    assert m.mode_go and m.mover.goal[0] < m.x                    # 5 <= 10 >> 1: it flees west, away from the hero


def _run_cli_capturing_setup(monkeypatch, argv):
    import engine.__main__ as cli
    seen = {}

    def fake_setup(a):
        seen["difficulty"] = a.difficulty
        raise ValueError("stop")                                 # main() reports it through argparse
    with monkeypatch.context() as mp:
        mp.setattr(cli, "_setup", fake_setup)
        with pytest.raises(SystemExit):
            cli.main(argv)
    return seen


def test_cli_run_difficulty_option_defaults_to_medium_and_reaches_the_world(monkeypatch):
    # `run --difficulty 1|2|3` = Easy / Medium / Hard of the new-game screen (ai.md 10.1); default 2 = no tweak
    assert _run_cli_capturing_setup(monkeypatch, ["run", "10"]) == {"difficulty": 2}
    assert _run_cli_capturing_setup(monkeypatch, ["run", "10", "--difficulty", "3"]) == {"difficulty": 3}
    import engine.__main__ as cli
    got = {}

    class Stop(Exception):
        pass

    def fake_from_map(m, assets, **kw):
        got.update(kw)
        raise Stop
    monkeypatch.setattr("allods2.cli.open_map", lambda *a: None)
    monkeypatch.setattr("allods2.assets.AssetCache", lambda *a: None)
    monkeypatch.setattr(cli.World, "from_map", staticmethod(fake_from_map))
    ns = argparse.Namespace(map="10", install=None, cmd="run", seed=1, difficulty=1)
    with pytest.raises(Stop):
        cli._setup(ns)
    assert got["difficulty"] == 1


def test_cli_run_rejects_a_difficulty_outside_1_to_3(monkeypatch):
    import engine.__main__ as cli
    with pytest.raises(SystemExit):
        cli.main(["run", "10", "--difficulty", "4"])


# --- the flee list FUN_0054ec6a + FUN_00567a16 (A§9) and the hidden-unit clause ----------------------------------------------

def test_the_flee_list_holds_ground_occupants_only_once_per_footprint_cell_and_no_flyers():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1)
    big = hero(w, 2, 24, 20, token=2)                    # footprint 24..25 x 20..21: 4 cells inside the square, listed 4 times
    fly = hero(w, 3, 20, 24, move=3)
    fly.move_type = 3                     # a flyer holds rec+8, never read by FUN_00551edb
    small = hero(w, 4, 20, 16)
    near = ai._enemies(w, m, 10)
    assert [c.id for c in near].count(big.id) == 4
    assert fly.id not in [c.id for c in near]
    assert [c.id for c in near].count(small.id) == 1
    assert ai._enemies(w, m, 3) == []
    assert sorted(c.id for c in ai._enemies(w, m, 4)) == sorted([big.id, big.id, small.id])   # footprint cells (24,20) and (24,21) are inside radius 4


def test_a_structure_on_the_cells_is_not_in_the_flee_list():
    # only occupant slots (creatures) are read: with no creature near, a wimpy unit's list is empty
    w = world()
    m = unit(w, 1, 20, 20, 2, 1, wimpy=10)
    assert ai._enemies(w, m, 10) == []


def test_reach_gap_is_one_when_touching_and_grows_by_one_per_cell():
    w = world()
    a = hero(w, 1, 20, 20)
    assert ai.reach_gap(a, hero(w, 2, 21, 20)) == 1
    assert ai.reach_gap(a, hero(w, 3, 22, 20)) == 2
    assert ai.reach_gap(a, hero(w, 4, 20, 25)) == 5


def test_a_hidden_hostile_is_in_the_flee_list_only_inside_the_see_invisible_gap():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1)
    h = hero(w, 2, 22, 20)
    h.hidden = True
    assert ai.see_invisible(m) == 1
    assert ai._enemies(w, m, 10) == []                    # gap 2 > 1
    m.stats.fields["see_invisible"] = 2
    assert ai._enemies(w, m, 10) == [h]
    m.stats.fields["see_invisible"] = 1
    w.move_unit(h.id, 21, 20)
    assert ai._enemies(w, m, 10) == [h]                   # touching: gap 1


def test_a_hidden_hero_is_not_a_pool_target_until_a_member_touches_it():
    w = world()
    m = unit(w, 1, 20, 20, 2, 1)
    h = hero(w, 2, 25, 20)
    h.hidden = True
    sim = Simulation(w, ai=True)
    run(sim, 20)
    assert m.ai.target is None
    h.hidden = False
    run(sim, 16)
    assert m.ai.target == h.id


# --- sleeping squads (A§15: FUN_0055b5f1 awake map, FUN_00570087 / FUN_0056dca2 gates) ----------------------------------------

def _sleep_world(mx, my=8, hx=8, hy=8):
    w = world(n=64)
    w.ai_sleep = True
    hero(w, 1, hx, hy)
    m = unit(w, 2, mx, my, 2, squad=1)
    return w, m


def test_a_squad_wakes_only_within_two_blocks_of_eight_cells_of_a_human_unit():
    for mx, awake in ((8, True), (31, True), (32, False), (47, False)):         # hero block 1 -> blocks -1..3 -> cells 0..31
        w, _ = _sleep_world(mx)
        ai.enable(w)
        assert w.ai_groups[(2, 1)].awake is awake, mx
    w, _ = _sleep_world(8, my=40)                                               # the same test on the other axis (block 5 vs 1)
    ai.enable(w)
    assert not w.ai_groups[(2, 1)].awake


def test_a_wounded_member_or_the_keep_awake_flag_keeps_a_far_squad_awake():
    w, m = _sleep_world(50)
    ai.enable(w)
    g = w.ai_groups[(2, 1)]
    assert not g.awake
    m.hp -= 1
    ai.wake(w)
    assert g.awake
    m.hp = m.hp_max
    ai.wake(w)
    assert not g.awake
    g.keep_awake = True
    ai.wake(w)
    assert g.awake


def test_without_the_sleep_switch_every_squad_is_awake():
    w, _ = _sleep_world(50)
    w.ai_sleep = False
    ai.enable(w)
    assert w.ai_groups[(2, 1)].awake


def test_a_sleeping_squad_does_not_think_or_look_around_and_wakes_when_the_hero_comes():
    w, m = _sleep_world(50)
    sim = Simulation(w, ai=True)
    run(sim, 200)
    assert m.state == ai.SLEEP_STATE and not m.mode_look and w.ai_groups[(2, 1)].seen == 0
    h = w.units[UNIT_ID_BASE + 1]
    h.x = 44                                                    # next to it (teleport: the hero's walk is not under test)
    run(sim, 16)
    g = w.ai_groups[(2, 1)]
    assert g.awake and g.seen == 1 and m.state != ai.SLEEP_STATE


def test_a_sleeping_member_with_a_step_in_progress_finishes_the_step():
    w, m = _sleep_world(50)
    sim = Simulation(w, ai=True)
    m.mover.step_ticks = 3
    assert not ai.asleep(w, m)
    m.mover.step_ticks = 0
    assert ai.asleep(w, m)
    m.brain_order = 1                                           # a swing in progress is Brain order 1
    assert not ai.asleep(w, m)
