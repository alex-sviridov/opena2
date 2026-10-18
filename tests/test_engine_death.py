"""Death (I2): the dying countdown, removal, corpses, selection, attackers, XP and level-ups, loot, regeneration, determinism.
Synthetic worlds, always run, plus a few install checks.  Spec: docs/engine/combat.md section 12 (C§12.x), design 2026-10-18-death-design.md."""

import math

import numpy as np
import pytest

from allods2.formats import progression as prog
from allods2.formats.itemgen import MsvcRng, loot_item, rnd
from allods2.formats.unitstats import HUMAN, MONSTER, UnitType
from engine.sim import AttackUnit, SelectUnits, Simulation, replay
from engine.sim import death, vitals, xp
from engine.sim.combatstats import ArmourBlock, AttackRecord, CombatStats
from engine.sim.movement import live_cells
from engine.view.drawlist import death_stage as view_stage
from engine.view.drawlist import unit_frame
from engine.world import DEAD, UNIT_ID_BASE, Damage, Died, Item, LevelUp, Loot, Player, Removed, Unit, World, death_stage

from helpers import GFS


def world(n=40, seed=1):
    w = World(np.zeros((n, n), np.uint16), np.zeros((n, n), np.int8), "syn", seed=seed)
    w._cost = np.full((n, n), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    w.players[2] = Player(2, 1)
    return w


def mon(name="M", **fields):
    return UnitType(MONSTER, 1, name, 1, 1, {"token_size": 1, **fields}, (), ())


def unit(w, uid, x, y, owner=2, hp=50, stats=None, move_type=1, lo=3, skill=500, **kw):
    u = Unit(UNIT_ID_BASE + uid, 1, owner, x, y, uid=uid, hp=hp, hp_max=max(hp, 1), facing=64, move_type=move_type, stats=stats or mon(),
             server_id=uid, **kw)
    u.mover.turn_rate = 32
    u.combat = CombatStats(AttackRecord(skill=skill, lo=lo, sp=0), ArmourBlock(10, 0), windup=6, recovery=4, range=1)
    w.add_unit(u)
    return u


def hero(w, uid, x, y, skills=(0, 80, 10, 10, 10, 10), mind=30, owner=1):
    t = UnitType(HUMAN, 1, "Fighter_Hero", 1, 1, {"token_size": 1, "body": 30, "reaction": 30, "mind": mind, "spirit": 30,
                                                   "mana_max": -1, "gender": 0}, (), ())
    u = unit(w, uid, x, y, owner=owner, hp=200, stats=t, human=True)
    u.skills = skills
    u.xp, u.xp_total = prog.start_pools(skills)
    u.best_school = 1
    u.combat.record.kind = 1
    return u


def run(sim, n):
    for _ in range(n):
        sim.step()


def kill(w, victim, by=None):
    victim.hp = 0
    if by is not None:
        victim.last_attacker = by.id


# --- the timeline (C§12.1) -----------------------------------------------------------------------

def test_dying_countdown_blocks_until_the_removal_tick_then_releases_the_cell():
    w = world()
    v = unit(w, 1, 10, 10, hp=-20, stats=mon(dying_time=14))
    other = unit(w, 2, 20, 20, owner=1)
    v.order, v.state = 3, 3
    sim = Simulation(w)
    t0 = w.tick
    sim.step()
    assert (v.order, v.state, v.death_tick, v.action, v.timer) == (0, 0, t0, "dying", 13)
    assert v.combat.block.defence == 5                                   # halved once (10 -> 5)
    assert v.id in w.units and (10, 10) in live_cells(w, other)         # still blocking
    for j in range(1, 14):
        sim.step()
        assert v.id in w.units, j
    assert (10, 10) in live_cells(w, other)
    sim.step()                                                           # T0 + 14
    assert v.id not in w.units and v.id in w.corpses and v.state == DEAD
    assert (10, 10) not in live_cells(w, other)
    assert [e.tick for e in w.fight_log if isinstance(e, Removed)] == [t0 + 14]


def test_zero_dying_time_removes_one_tick_after_the_first():
    w = world()
    v = unit(w, 1, 10, 10, hp=-20, stats=mon(dying_time=0))
    sim = Simulation(w)
    sim.step()
    assert v.id in w.units
    sim.step()
    assert v.id in w.corpses


def test_a_ground_unit_at_hp_minus_5_waits_for_the_64_tick_drain_and_hp_zero_never_goes():
    w = world()
    v = unit(w, 1, 10, 10, hp=-5, stats=mon(dying_time=3, hp_regen=0))
    z = unit(w, 2, 12, 10, hp=0, stats=mon(dying_time=3))
    sim = Simulation(w)
    run(sim, 10)
    assert v.id in w.units and v.timer < 1                                # countdown done, HP still > -10
    seen = []
    for _ in range(64 * 6):
        sim.step()
        if v.id in w.corpses:
            break
        seen.append(v.hp)
    assert v.id in w.corpses and v.hp <= -10
    drains = [b - a for a, b in zip(seen, seen[1:]) if b != a]
    assert drains == [-1] * 4                                            # one HP per 64 ticks (block & 3 == 0), -5 -> -9, then -10 on the last
    assert z.id in w.units and z.hp == 0
    run(sim, 3000)
    assert z.id in w.units and z.hp == 0                                 # HP 0 is never drained


def test_a_flyer_gets_hp_minus_1000_and_leaves_without_a_corpse():
    w = world()
    f = unit(w, 1, 10, 10, hp=0, stats=mon(dying_time=5), move_type=3)
    sim = Simulation(w)
    run(sim, 5)
    assert f.id in w.units
    sim.step()
    assert f.id not in w.units and f.id not in w.corpses and f.hp == death.STAGE5_HP      # -1000, then the removal's decay step takes stage 5


def test_selection_is_dropped_at_the_first_dying_tick():
    w = world()
    v = unit(w, 1, 10, 10, owner=1, hp=40, stats=mon(dying_time=9))
    sim = Simulation(w)
    sim.step([SelectUnits(1, (v.id,))])
    assert w.players[1].selection == (v.id,)
    v.hp = 0
    sim.step()
    assert w.players[1].selection == ()


def test_revived_unit_dying_again_skips_the_first_tick_block():
    w = world()
    v = unit(w, 1, 10, 10, hp=0, stats=mon(dying_time=20))
    sim = Simulation(w)
    run(sim, 3)
    v.hp = 30                                                            # healed
    run(sim, 2)
    v.hp = -50
    defence = v.combat.block.defence
    sim.step()
    assert v.combat.block.defence == defence                             # not halved again; the stale timer counts on
    assert v.id in w.units


# --- corpses (C§12.6) ----------------------------------------------------------------------------

def test_corpse_decays_one_hp_per_32_ticks_and_leaves_at_stage_5():
    w = world()
    v = unit(w, 1, 10, 10, hp=-12, stats=mon(dying_time=1))
    sim = Simulation(w)
    run(sim, 3)
    assert v.id in w.corpses
    h0 = v.hp
    start = w.tick
    while w.tick < start + 320:
        sim.step()
    assert h0 - v.hp == 10                                               # 320 ticks / 32
    v.hp = -599
    run(sim, 64)
    assert v.id not in w.corpses and v.hp == death.STAGE5_HP


def test_death_stage_thresholds_and_the_view_copy():
    for hp, st in ((5, 0), (0, 1), (-10, 1), (-11, 2), (-20, 2), (-21, 3), (-40, 3), (-41, 4), (-600, 4), (-601, 5)):
        assert death_stage(hp) == view_stage(hp) == st, hp


def test_hero_corpse_stops_decaying_at_minus_61():
    w = world()
    h = hero(w, 1, 10, 10, owner=2)
    h.hp = -60
    h.stats = UnitType(HUMAN, 1, "Fighter_Hero", 1, 1, {"token_size": 1, "dying_time": 1, "mana_max": -1}, (), ())
    sim = Simulation(w)
    run(sim, 600)
    assert h.id in w.corpses and h.hp >= -61


class StubSet:
    """Animation set stand-in: records the action asked for."""
    idle_action = "stand"

    def __init__(self, actions):
        self.actions = {a: None for a in actions}

    def frame_at(self, action, facing, tick, **kw):
        return (action, tick)


def test_unit_frame_plays_dying_once_from_the_death_tick_then_bones_then_nothing():
    aset = StubSet(["stand", "dying", "corpse", "bones1", "bones2", "bones3"])
    u = Unit(1, 1, 2, 5, 5, hp=0, death_tick=100)
    assert unit_frame(aset, u, 107) == ("dying", 7)
    u.hp = -12
    assert unit_frame(aset, u, 150) == ("bones1", 0)
    u.hp = -30
    assert unit_frame(aset, u, 150)[0] == "bones2"
    u.hp = -50
    assert unit_frame(aset, u, 150)[0] == "bones3"
    u.hp = -700
    assert unit_frame(aset, u, 150) is None
    u.hp, u.death_tick = 0, None                                         # a map unit at HP 0: the held corpse frame
    assert unit_frame(aset, u, 150) == ("corpse", 0)


# --- attackers (C§12.2) --------------------------------------------------------------------------

def test_attackers_keep_hitting_the_body_and_stop_at_the_executor_pass_after_the_removal():
    w = world()
    a = unit(w, 1, 10, 10, owner=1, hp=100, stats=mon(), lo=4)
    v = unit(w, 2, 11, 10, hp=10, stats=mon(dying_time=3))
    sim = Simulation(w)
    sim.step([AttackUnit(1, (a.id,), v.id)])
    removed = hp_at_death = None
    for _ in range(400):
        sim.step()
        if hp_at_death is None and v.hp <= 0:
            hp_at_death = v.hp
        if removed is None and v.id in w.corpses:
            removed = w.tick
        if removed is not None and a.order == 0xC:
            break
    assert removed is not None and a.order == 0xC and not a.mode_attack
    assert v.hp < hp_at_death                                            # it kept hitting the dying body (no HP or state test, C§5.1)
    hp_log = [e.hp for e in w.fight_log if isinstance(e, Damage)]
    assert all(h > -10 for h in hp_log)                                  # blows that leave HP <= -10 are not reported (message 0x73 rule)
    assert not [e for e in w.fight_log if isinstance(e, Died) and e.unit != v.id]


def test_attack_command_on_a_corpse_is_accepted_and_stops_at_the_next_pass():
    w = world()
    a = unit(w, 1, 10, 10, owner=1, hp=100)
    v = unit(w, 2, 11, 10, hp=-30, stats=mon(dying_time=1))
    sim = Simulation(w)
    run(sim, 4)
    assert v.id in w.corpses
    sim.step([AttackUnit(1, (a.id,), v.id)])
    assert a.order == 3 and a.target == v.id
    run(sim, 20)
    assert a.order == 0xC and not a.mode_attack


def test_no_xp_for_blows_on_a_dying_unit():
    w = world()
    h = hero(w, 1, 10, 10)
    v = unit(w, 2, 11, 10, hp=-3, stats=mon(xp=100))
    pools = h.xp
    xp.damage_credit(w, h, v, 5, -3)                                     # the victim had no HP before the blow
    assert h.xp == pools


# --- XP and level-ups (C§12.7, progression §4) ---------------------------------------------------

def test_hit_credit_amount_and_pool():
    w = world()
    h = hero(w, 1, 10, 10)                                               # Mind 30: factor 1.25, school 1 = best school
    v = unit(w, 2, 11, 10, hp=50, stats=mon(xp=100))
    v.hp_max = 50
    before = h.xp[0]
    v.hp = 40                                                            # a 10 damage blow
    xp.damage_credit(w, h, v, 10, 50)
    assert h.xp[0] - before == int(int(0.5 * 100 * 10 / 50 + 1) * 1.25) == 13
    assert h.xp_total == sum(h.xp)


def test_hit_credit_needs_a_hero_a_computer_victim_and_a_living_victim():
    w = world()
    h = hero(w, 1, 10, 10)
    v = unit(w, 2, 11, 10, hp=50, stats=mon(xp=100))
    pools = h.xp
    xp.damage_credit(w, h, v, 0, 50)                                     # no damage
    v.owner = 1
    w.players[1].human = True
    xp.damage_credit(w, h, v, 5, 50)                                     # the victim's owner is the human player
    plain = unit(w, 3, 12, 10, owner=1, hp=50)
    v.owner = 2
    xp.damage_credit(w, plain, v, 5, 50)                                 # not a hero
    assert h.xp == pools
    xp.damage_credit(w, h, v, 5, 50)
    assert h.xp != pools


def test_off_school_award_is_an_eighth_and_school_5_is_exempt():
    w = world()
    h = hero(w, 1, 10, 10, skills=(0, 80, 80, 80, 80, 80))
    h.combat.record.kind = 2                                             # the weapon school is Axe, the best school is Blade
    xp.award(w, h, 80, 0)
    assert h.xp[1] - prog.start_pools(h.skills)[0][1] == (int(80 * 1.25) + 7) >> 3
    h.combat.record.kind = 5
    p5 = h.xp[4]
    xp.award(w, h, 80, 0)
    assert h.xp[4] - p5 == int(80 * 1.25)


def test_kill_credit_goes_to_the_last_hitter_only_and_applies_the_repeat_discount():
    w = world()
    h, other = hero(w, 1, 10, 10), hero(w, 5, 12, 10)
    sim = Simulation(w)
    amounts = []
    for n in range(3):
        v = unit(w, 10 + n, 11, 11 + n, hp=-20, stats=mon(xp=100, dying_time=0))
        v.server_id = 77
        v.last_attacker = h.id
        before = h.xp[0]
        run(sim, 2)
        amounts.append(h.xp[0] - before)
    assert [e for e in h.kill_list] == [[77, 3]]
    base = int(50 * 1.25)
    assert amounts == [base * 10 // (n + 10) for n in range(3)]
    assert other.xp == prog.start_pools(other.skills)[0]                 # nobody else was paid


def test_kill_credit_is_skipped_for_summoned_victims_dead_killers_and_plain_units():
    w = world()
    h = hero(w, 1, 10, 10)
    pools = h.xp
    s = unit(w, 2, 11, 10, hp=-20, stats=mon(xp=200, dying_time=0), behaviour=8)
    s.last_attacker = h.id
    d = unit(w, 3, 11, 11, hp=-20, stats=mon(xp=200, dying_time=0))
    d.last_attacker = h.id
    h.hp = -1                                                            # the killer is dying itself
    sim = Simulation(w)
    run(sim, 3)
    assert h.xp == pools and not h.kill_list


def test_level_up_raises_the_skill_and_recomputes_max_hp_and_mana():
    w = world()
    h = hero(w, 1, 10, 10)
    thr = prog._build_thresholds()
    pools = list(h.xp)
    pools[0] = thr[81] - 3
    h.xp = tuple(pools)
    h.xp_total = sum(pools)
    h.combat_before = h.combat
    xp.award(w, h, 40, 1)
    assert h.skills[1] == 81
    assert [e for e in w.fight_log if isinstance(e, LevelUp)] == [LevelUp(w.tick, h.id, 1, 81)]
    hp_max, mana = prog.derived_vitals(h.stats, h.skills, total=h.xp_total)
    assert (h.hp_max, h.mana_max) == (hp_max, mana) and h.combat is None
    assert h.hp <= h.hp_max


def test_span_cap_limits_one_award_to_the_next_threshold():
    w = world()
    h = hero(w, 1, 10, 10)
    thr = prog._build_thresholds()
    xp.award(w, h, 100_000, 1)
    assert h.xp[0] == thr[81] and h.skills[1] == 81


# --- loot (C§12.4) -------------------------------------------------------------------------------

class Scripted:
    """A world RNG that replays given `rand(n)` results and records the calls."""

    def __init__(self, values):
        self.values, self.calls = list(values), []

    def rand(self, n):
        self.calls.append(n)
        return self.values.pop(0)


def test_gold_rolls_in_the_exe_order_and_the_pile_lands_on_the_cell():
    w = world()
    w.rng = Scripted([79, 7, 99])
    unit(w, 1, 10, 10, hp=-20, stats=mon(dying_time=0, gold_chance=80, gold_base=90, gold_spread=270, item_chance=30))
    sim = Simulation(w)
    run(sim, 2)
    assert w.rng.calls == [100, 270, 100]                                # gold roll, gold spread, item roll
    (pile,) = w.items.values()
    assert (pile.x, pile.y, pile.gold, pile.codes) == (10, 10, 97, ())
    assert [e for e in w.fight_log if isinstance(e, Loot)][0].gold == 97


def test_chance_is_p_over_101_and_a_failed_roll_drops_nothing():
    w = world()
    w.rng = Scripted([80, 50])                                           # rnd(100) < 80 fails at 80
    unit(w, 1, 10, 10, hp=-20, stats=mon(dying_time=0, gold_chance=80, gold_base=90, gold_spread=270, item_chance=0))
    run(Simulation(w), 2)
    assert w.rng.calls == [100, 100] and not w.items


def test_carried_items_drop_but_not_for_summoned_or_npc_units_and_humans_never_roll():
    for kw, name, expect in (({}, "Hero", (5, 6)), ({"behaviour": 8}, "Hero", ()), ({}, "Man_NPC_Guard", ())):
        w = world()
        w.rng = Scripted([])
        t = UnitType(HUMAN, 1, name, 1, 1, {"token_size": 1, "dying_time": 0, "mana_max": -1}, (), ())
        u = unit(w, 1, 10, 10, hp=-20, stats=t, human=True, **kw)
        u.carried = (5, 6)
        run(Simulation(w), 2)
        assert w.rng.calls == []                                         # a human rolls no gold or item
        assert (tuple(next(iter(w.items.values())).codes) if w.items else ()) == expect


def test_loot_merges_into_the_pile_on_the_cell():
    w = world()
    w.rng = Scripted([0, 5, 99])
    w.add_item(Item(0x30001, 10, 10, gold=40, codes=(9,)))
    unit(w, 1, 10, 10, hp=-20, stats=mon(dying_time=0, gold_chance=50, gold_base=10, gold_spread=9))
    run(Simulation(w), 2)
    (pile,) = w.items.values()
    assert pile.gold == 40 + 15 and pile.codes == (9,)


def test_the_item_roll_uses_the_generator_with_the_unit_window_and_flags():
    from allods2.assets import AssetCache
    if GFS is None:
        pytest.skip("no install")
    assets = AssetCache(GFS)
    table = assets.items()
    t = {x.name: x for x in assets.unit_stats().types}["Orc_Sword"]
    w = world(seed=5)
    w.item_table = table
    u = unit(w, 1, 10, 10, hp=-20, stats=t, move_type=1)
    u.stats = t
    ref = MsvcRng(5)
    gold = rnd(ref, 100) < t.get("gold_chance")
    amount = t.get("gold_base") + rnd(ref, t.get("gold_spread")) if gold else 0
    item = None
    if rnd(ref, 100) < t.get("item_chance"):
        item = loot_item(table, t.get("item_value_min"), t.get("item_value_max"), t.get("item_flags"), ref)
    run(Simulation(w), 20)
    if gold or item:
        (pile,) = w.items.values()
        assert pile.gold == amount and pile.codes == ((item.code & 0xFFFF,) if item else ())
    else:
        assert not w.items
    assert w.rng.state == ref.state                                      # the same draws, in the same order


# --- regeneration (C§12.5) -----------------------------------------------------------------------

def expected_hp(uid, hp, hp_max, regen, ticks, step_end=0):
    acc = 0
    for tick in range(ticks):
        if tick & 15 != 12:
            continue
        block = tick >> 4
        k = 3 if tick - step_end > 80 else 1
        if hp < hp_max and block & 3 == uid & 3:
            t = hp * 100 + acc + hp_max * 2 * 100 * k // regen
            acc, hp = t % 100, min(t // 100, hp_max)
    return hp, acc


@pytest.mark.parametrize("uid", [1, 2, 3, 4])
def test_hp_regeneration_matches_the_formula_for_every_id_phase(uid):
    w = world()
    u = unit(w, uid, 10, 10, hp=1, stats=mon(hp_regen=100))
    u.hp_max = 80
    sim = Simulation(w)
    run(sim, 1000)
    assert (u.hp, u.hp_acc) == expected_hp(u.id, 1, 80, 100, 1000)


def test_rest_triples_the_rate_after_80_ticks_without_a_step():
    w = world()
    u = unit(w, 1, 10, 10, hp=1, stats=mon(hp_regen=100))
    u.hp_max = 800
    u.step_end = 500
    sim = Simulation(w)
    run(sim, 700)
    assert (u.hp, u.hp_acc) == expected_hp(u.id, 1, 800, 100, 700, step_end=500)


def test_regeneration_clamps_at_max_and_needs_a_nonzero_rate_and_no_combat_test():
    w = world()
    a = unit(w, 1, 10, 10, hp=79, stats=mon(hp_regen=100))
    a.hp_max = 80
    b = unit(w, 2, 12, 10, hp=10, stats=mon(hp_regen=0))
    foe = unit(w, 3, 11, 10, owner=1, hp=10_000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, (foe.id,), a.id)])                           # being attacked changes nothing
    run(sim, 2000)
    assert a.hp <= 80 and b.hp == 10


def test_humans_regenerate_hp_at_100_and_mana_every_block_at_50():
    w = world()
    t = UnitType(HUMAN, 1, "Mage", 1, 1, {"token_size": 1, "mana_max": 100}, (), ())
    u = unit(w, 4, 10, 10, hp=10, stats=t, human=True)
    u.hp_max, u.mana, u.mana_max = 100, 0, 100
    sim = Simulation(w)
    run(sim, 16 * 5)
    mana = acc = 0
    for tick in range(16 * 5):
        if tick & 15 == 12:
            k = 3 if tick > 80 else 1
            t_ = mana * 100 + acc + 100 * 100 * k // 50
            acc, mana = t_ % 100, min(t_ // 100, 100)
    assert u.mana == mana == 10


def test_dead_and_negative_hp_units_do_not_regenerate_hp_below_zero_drains():
    w = world()
    u = unit(w, 4, 10, 10, hp=-3, stats=mon(hp_regen=100, dying_time=60))
    u.hp_max = 80
    sim = Simulation(w)
    run(sim, 64 * 2)
    assert u.hp <= -4


# --- determinism ---------------------------------------------------------------------------------

def scripted_session():
    w = world(seed=9)
    a = hero(w, 1, 10, 10)
    a.combat.record.lo, a.combat.record.sp = 6, 4
    for n in range(3):
        v = unit(w, 10 + n, 12 + n, 10, hp=14, stats=mon(xp=60, dying_time=6, gold_chance=70, gold_base=5, gold_spread=20, hp_regen=100))
        v.hp_max = 14
    return w, a


def test_a_fight_with_deaths_loot_and_xp_replays_to_the_same_hash():
    cmds = [(0, AttackUnit(1, (UNIT_ID_BASE + 1,), UNIT_ID_BASE + 10)), (200, AttackUnit(1, (UNIT_ID_BASE + 1,), UNIT_ID_BASE + 11)),
            (500, AttackUnit(1, (UNIT_ID_BASE + 1,), UNIT_ID_BASE + 12))]
    hashes = []
    for _ in range(2):
        w, a = scripted_session()
        sim = Simulation(w)
        replay(sim, cmds, 1200)
        hashes.append(w.dump_json())
        assert any(isinstance(e, Removed) for e in w.fight_log) and w.items
    assert hashes[0] == hashes[1]
    w, a = scripted_session()
    sim = Simulation(w)
    run(sim, 0)
    for t in range(1200):
        sim.step([c for tk, c in cmds if tk == t])
    assert w.dump_json() == hashes[0]
    assert '"corpses"' in hashes[0]


# --- feedback: bars, picking, info panel ---------------------------------------------------------

class _Items:
    def __init__(self, picks):
        self.picks = picks


class _Ctx:
    def __init__(self, w, picks, health_bars=False):
        from engine.view.drawlist import DrawOptions
        self.world, self.items = w, _Items(picks)
        self.opts = DrawOptions(health_bars=health_bars)


def test_bars_for_hovered_and_selected_units_and_a_mana_bar_for_casters():
    from engine.view.drawlist import MANA_TIER, _bars
    from engine.view.pick import PickRect
    w = world()
    a = unit(w, 1, 10, 10, hp=50)
    b = unit(w, 2, 12, 10, hp=50)
    b.mana, b.mana_max = 30, 60
    picks = [PickRect(a.id, 0, 20, 40, 60), PickRect(b.id, 50, 20, 90, 60)]
    assert _bars(_Ctx(w, picks), ()) == []
    only_b = _bars(_Ctx(w, picks), (), hover=b.id)
    assert [i.entity for i in only_b] == [b.id, b.id]
    hp_bar, mana_bar = only_b
    assert hp_bar.bar[2] == 0 and mana_bar.bar[2] == MANA_TIER and mana_bar.sy == hp_bar.sy + 4
    assert mana_bar.bar[0] == mana_bar.bar[1] // 2                      # 30 / 60
    assert len(_bars(_Ctx(w, picks), (a.id,), hover=b.id)) == 3




def test_dying_bodies_and_corpses_are_drawn_but_never_picked_and_stage_5_vanishes():
    from test_engine_unit_draw import uassets, world_with
    from test_engine_unit_draw import unit as draw_unit
    from engine.view import DrawOptions, build_draw_list
    from test_engine_objects import cam
    alive, dying, bones, gone = (draw_unit(i, 10 + i, 10) for i in (1, 2, 3, 4))
    dying.hp, dying.death_tick = 0, 0
    bones.hp = -12
    gone.hp = -700
    w = world_with(alive, dying, bones)
    w.corpses[gone.id] = gone                                           # a corpse of the corpse list is drawn like a unit
    w.corpses[bones.id] = w.units.pop(bones.id)
    items = build_draw_list(w, cam(), 5, uassets(), DrawOptions(shadows=False))
    drawn = {i.entity for i in items if i.kind == "sprite"}
    assert alive.id in drawn and dying.id in drawn and bones.id in drawn and gone.id not in drawn
    assert [p.entity for p in items.picks] == [alive.id]


def test_info_rows_show_hp_mana_level_and_xp():
    pygame = pytest.importorskip("pygame")
    from engine.backend_pygame.interface import info_rows
    w = world()
    plain = unit(w, 1, 10, 10, hp=40)
    assert info_rows(plain) == [("HP", 0x2c), ("40/40", 0x36)]
    h = hero(w, 2, 12, 10)
    h.mana, h.mana_max = 5, 9
    rows = dict((t, y) for t, y in info_rows(h))
    assert rows["Mana"] == 0x40 and rows["5/9"] == 0x4a and rows["Level 80"] == 0x54 and ("XP %d" % h.xp_total) in rows


# --- install (skipped without the game files) ----------------------------------------------------

def test_install_templates_give_the_documented_death_and_regeneration_numbers():
    from allods2.assets import AssetCache
    if GFS is None:
        pytest.skip("no install")
    types = {t.name: t for t in AssetCache(GFS).unit_stats().types}
    orc, gob = types["Orc_Sword"], types["Goblin_Pike"]
    assert (orc.get("dying_time"), gob.get("dying_time")) == (14, 12)               # C§12.1: removal at T0 + 14 / T0 + 12
    assert orc.get("hp_max") * 2 * 100 // orc.get("hp_regen") == 160                # C§12.5: 1.60 HP per application
    assert [orc.get(k) for k in ("gold_chance", "gold_base", "gold_spread", "item_chance")] == [80, 90, 270, 30]
    w = world()
    u = unit(w, 1, 10, 10, hp=-20, stats=orc)
    u.hp_max = orc.get("hp_max")
    sim = Simulation(w)
    t0 = w.tick
    while u.id in w.units:
        sim.step()
    assert w.tick - 1 == t0 + 14 and u.id in w.corpses
    for kind in (types["Fighter_Hero"], types["Mage_Hero"]):
        assert death.dying_time(Unit(1, 1, 1, 0, 0, human=True, stats=kind)) == (8 if kind.name == "Fighter_Hero" else 12)
