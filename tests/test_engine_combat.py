"""Combat (I1): the attack order, the approach, the swing timeline and the hit.  Synthetic worlds, always run.
Spec: docs/engine/combat.md (C§ = its sections)."""

import numpy as np
import pytest

from allods2.formats.unitstats import MONSTER, UnitType
from engine.sim import AttackUnit, MoveUnits, Simulation, Stop, replay
from engine.sim.combat import BRAIN_SWING, attack_gap, combat_stats
from engine.sim.combatstats import ArmourBlock, AttackRecord, CombatStats
from engine.world import UNIT_ID_BASE, Damage, Died, Player, Unit, World

EAST = 64


def world(n=40, seed=1):
    w = World(np.zeros((n, n), np.uint16), np.zeros((n, n), np.int8), "syn", seed=seed)
    w._cost = np.full((n, n), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    w.players[2] = Player(2, 1)
    return w


def fighter(w, uid, x, y, owner=1, hp=100, skill=500, lo=3, sp=0, windup=6, recovery=4, rng=1, defence=0, absorb=0, move_type=1,
            speed=24, facing=EAST):
    u = Unit(UNIT_ID_BASE + uid, 1, owner, x, y, uid=uid, hp=hp, hp_max=hp, facing=facing, speed_mod=speed, move_type=move_type)
    u.mover.turn_rate = 32
    u.combat = CombatStats(AttackRecord(skill=skill, lo=lo, sp=sp), ArmourBlock(defence, absorb), windup=windup, recovery=recovery,
                           range=rng)
    w.add_unit(u)
    return u


def ids(*us):
    return tuple(u.id for u in us)


def damages(w):
    return [e for e in w.fight_log if isinstance(e, Damage)]


def run(sim, ticks):
    for _ in range(ticks):
        sim.step()


def run_until(sim, cond, limit=2000):
    for _ in range(limit):
        if cond():
            return
        sim.step()
    raise AssertionError("condition never met")


def swing_starts(sim, a, ticks):
    """Ticks (world.tick of the step) at which `a`'s brain order became a swing."""
    out, prev = [], a.brain_order
    for _ in range(ticks):
        t = sim.world.tick
        sim.step()
        if a.brain_order == BRAIN_SWING and prev != BRAIN_SWING:
            out.append(t)
        prev = a.brain_order
    return out


# --- the order (C§2) -------------------------------------------------------------------------------

def test_the_command_sets_order_3_and_mode_0_the_group_pass_sets_mode_5():
    w = world()
    a, foe = fighter(w, 1, 10, 10), fighter(w, 2, 20, 10, owner=2)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])                  # tick 0
    assert (a.order, a.target, a.mode_attack, a.mode_go, a.range) == (3, foe.id, False, False, 1)
    (g,) = w.groups.values()
    assert g.order == 0 and g.members == [a.id]
    while w.tick & 15 != 6:
        sim.step()
        assert not a.mode_attack                              # nothing happens before the group pass
    sim.step()                                                # the step with tick & 15 == 6
    assert a.mode_attack and a.state == 1                     # mode 5 ran in the same tick: the approach started


def test_a_self_target_stops_the_member_and_an_unknown_target_changes_no_order():
    w = world()
    a, b = fighter(w, 1, 10, 10), fighter(w, 2, 12, 10)
    sim = Simulation(w)
    sim.step([MoveUnits(1, ids(a, b), (30, 30))])
    assert a.order == b.order == 1
    sim.step([AttackUnit(1, ids(a), 9999)])                   # unknown id: dropped, but the group was made (0x4f5283)
    assert a.order == 1 and len(w.groups) >= 1 and a.id in list(w.groups.values())[-1].members
    sim.step([AttackUnit(1, ids(a, b), b.id)])
    assert a.order == 3 and a.target == b.id
    assert b.order == 0xC and not b.mode_attack and b.target is None      # the target itself is stopped (FUN_0056dba1)


def test_ground_melee_cannot_attack_a_flyer_but_a_shooter_can():
    w = world()
    melee, bow, bat = fighter(w, 1, 10, 10), fighter(w, 2, 10, 12, rng=4), fighter(w, 3, 14, 10, owner=2, move_type=3)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(melee, bow), bat.id)])
    assert melee.order == 0xC and melee.target is None        # refused: stands
    assert bow.order == 3 and bow.target == bat.id and bow.range == 4


def test_foreign_ids_and_dead_first_unit_are_rejected_like_every_command():
    w = world()
    a, foe = fighter(w, 1, 10, 10), fighter(w, 2, 14, 10, owner=2)
    dead = fighter(w, 3, 10, 12, hp=0)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(foe), a.id), AttackUnit(1, ids(dead), foe.id), AttackUnit(7, ids(a), foe.id)])
    assert a.order == dead.order == foe.order == 0 and not w.groups


# --- approach and the swing timeline (C§3, C§4) -------------------------------------------------------

def test_first_hit_comes_windup_ticks_after_the_swing_starts_and_swings_repeat_with_the_recovery():
    w = world()
    a, foe = fighter(w, 1, 10, 10, windup=6, recovery=4), fighter(w, 2, 13, 10, owner=2, hp=1000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    starts = swing_starts(sim, a, 200)
    hits = [e.tick for e in damages(w)]
    assert len(starts) >= 3 and len(hits) >= 3
    assert hits[0] == starts[0] + 6                           # the damage lands `windup` ticks after the swing start
    # recovery timer drawn at the hit: 4 + rand(0..3); the next swing is windup + recovery + 2 after the previous start
    for s, nxt in zip(starts, starts[1:]):
        assert 6 + 4 + 2 <= nxt - s <= 6 + 4 + 3 + 2


def test_exact_period_follows_the_recovery_draw():
    w = world(seed=77)
    a, foe = fighter(w, 1, 10, 10, windup=5, recovery=3), fighter(w, 2, 11, 10, owner=2, hp=1000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    seen = []
    prev_phase = 0
    for _ in range(300):
        sim.step()
        if a.phase == 7 and prev_phase == 5:
            seen.append((w.tick - 1, a.timer))                # hit tick and the recovery timer just drawn
        prev_phase = a.phase
    assert len(seen) >= 4
    starts = []
    w2 = world(seed=77)
    a2, foe2 = fighter(w2, 1, 10, 10, windup=5, recovery=3), fighter(w2, 2, 11, 10, owner=2, hp=1000)
    sim2 = Simulation(w2)
    sim2.step([AttackUnit(1, ids(a2), foe2.id)])
    starts = swing_starts(sim2, a2, 300)
    for (hit, rec), s, nxt in zip(seen, starts, starts[1:]):
        assert hit == s + 5 and nxt == hit + rec + 2          # period = windup + recovery draw + 2


def test_damage_accumulates_on_hp_and_death_is_logged_once_hp_goes_below_zero():
    w = world()
    a, foe = fighter(w, 1, 10, 10, lo=4), fighter(w, 2, 11, 10, owner=2, hp=10)
    a.stats = UnitType(MONSTER, 1, "t", 1, 1, {"token_size": 1}, (), ())            # "has a template" (+0x3c != 0) for last_attacker
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    run_until(sim, lambda: foe.hp <= 0)
    run(sim, 200)
    ds = damages(w)
    assert [d.amount for d in ds][:3] == [4, 4, 4] and [d.hp for d in ds][:3] == [6, 2, -2]       # HP is the exe's s16 (combat.md 12)
    assert [e for e in w.fight_log if isinstance(e, Died)] == [Died(ds[2].tick, foe.id, a.id)]
    assert foe.last_attacker == a.id
    assert a.order == 0xC and not a.mode_attack               # the order ended at the executor pass after the removal (C§12.2)


def test_a_miss_logs_the_blow_with_zero_damage():
    w = world()
    a, foe = fighter(w, 1, 10, 10, skill=-3000), fighter(w, 2, 11, 10, owner=2, hp=10, defence=1000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    run_until(sim, lambda: len(damages(w)) >= 3)
    assert all(d.amount == 0 for d in damages(w)) and foe.hp == 10
    assert any(not d.hit for d in damages(w))


def test_unit_turns_to_the_exact_octant_before_the_first_swing():
    w = world()
    a, foe = fighter(w, 1, 10, 10, facing=192), fighter(w, 2, 11, 10, owner=2, hp=1000)   # facing west, target east
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    starts = swing_starts(sim, a, 100)
    assert starts and a.facing == EAST


def test_approach_arrives_adjacent_and_swings_when_facing_the_target():
    w = world()
    a, foe = fighter(w, 1, 8, 10), fighter(w, 2, 20, 13, owner=2, hp=1000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    run_until(sim, lambda: damages(w))
    assert attack_gap(*[__import__("engine.sim.pathfinding", fromlist=["foot"]).foot(u) for u in (a, foe)]) == 1
    assert max(abs(a.x - foe.x), abs(a.y - foe.y)) == 1


def test_a_target_that_walks_away_is_followed():
    w = world()
    a, foe = fighter(w, 1, 8, 10), fighter(w, 2, 12, 10, owner=2, hp=1000, speed=12)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id), MoveUnits(2, ids(foe), (30, 10))])
    run(sim, 120)
    assert foe.x > 14
    assert max(abs(a.x - foe.x), abs(a.y - foe.y)) <= 3 and a.mode_attack          # still chasing within a few cells
    run_until(sim, lambda: damages(w), 4000)                  # and it eventually catches the slower target


def test_a_hit_is_lost_when_the_target_leaves_reach_during_the_wind_up():
    w = world()
    a, foe = fighter(w, 1, 10, 10, windup=8, recovery=4), fighter(w, 2, 11, 10, owner=2, hp=1000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    run_until(sim, lambda: a.brain_order == BRAIN_SWING)
    w.move_unit(foe.id, 14, 10)                               # teleport three cells away mid-swing
    run_until(sim, lambda: a.phase == 7)
    assert damages(w) == []                                   # the range test at the hit failed: no blow, no log
    run_until(sim, lambda: a.done)
    assert a.phase == 0


def test_a_new_order_does_not_interrupt_the_swing():
    w = world()
    a, foe = fighter(w, 1, 10, 10, windup=8, recovery=4), fighter(w, 2, 11, 10, owner=2, hp=1000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    run_until(sim, lambda: a.brain_order == BRAIN_SWING)
    run(sim, 2)
    sim.step([MoveUnits(1, ids(a), (30, 30))])
    assert a.order == 1 and a.brain_order == BRAIN_SWING and a.phase == 5
    run_until(sim, lambda: len(damages(w)) == 1)              # the blow lands as scheduled
    run_until(sim, lambda: a.brain_order == 0)
    assert (a.x, a.y) == (10, 10)                             # it only starts walking after the swing
    run(sim, 30)
    assert (a.x, a.y) != (10, 10)


def test_stop_during_an_attack_ends_it():
    w = world()
    a, foe = fighter(w, 1, 10, 10), fighter(w, 2, 11, 10, owner=2, hp=1000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    run_until(sim, lambda: damages(w))
    sim.step([Stop(1, ids(a))])
    assert a.order == 0xC and not a.mode_attack
    run_until(sim, lambda: a.brain_order == 0)
    n = len(damages(w))
    run(sim, 100)
    assert len(damages(w)) == n


def test_each_hit_draws_from_the_world_rng_so_two_seeds_give_two_fights():
    def fight(seed):
        w = world(seed=seed)
        a, foe = fighter(w, 1, 10, 10, skill=0, lo=3, sp=6), fighter(w, 2, 11, 10, owner=2, hp=1000, defence=20)
        sim = Simulation(w)
        sim.step([AttackUnit(1, ids(a), foe.id)])
        run(sim, 400)
        return [(d.tick, d.amount) for d in damages(w)], w.dump_hash()
    a, b, c = fight(5), fight(5), fight(6)
    assert a == b and a != c


def test_replay_gives_the_same_world_hash():
    def build():
        w = world(seed=3)
        a, b = fighter(w, 1, 8, 10, skill=40, lo=2, sp=5), fighter(w, 2, 9, 12, skill=40, lo=2, sp=5)
        foe = fighter(w, 3, 20, 10, owner=2, hp=500, defence=30)
        return w, (a, b, foe)
    w1, (a, b, foe) = build()
    sim = Simulation(w1)
    sim.step([AttackUnit(1, ids(a, b), foe.id)])
    run(sim, 150)
    sim.step([MoveUnits(1, ids(a), (5, 5))])
    run(sim, 150)
    w2, _ = build()
    sim2 = Simulation(w2)
    replay(sim2, sim.log, w1.tick)
    assert w2.dump_hash() == w1.dump_hash() and w1.fight_log == w2.fight_log
