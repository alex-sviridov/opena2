"""Combat stats builders (I1): template + equipment -> attack record and armour block.  Synthetic templates always run;
the data.bin tests need the install.  Spec: docs/engine/combat.md section 6."""

import math

import pytest

from allods2.formats.unitstats import HUMAN, MONSTER, UnitType
from engine.rng import Rng
from engine.sim.combat import take_hit, take_hit_detail
from engine.sim.combatstats import (SURE_HIT_KIND, ArmourBlock, AttackRecord, CombatStats, human_stats, monster_stats,
                                    unit_combat_stats)
from helpers import GFS, needs_data


def tmpl(kind=MONSTER, equipment=("", ""), **fields):
    return UnitType(kind, 1, "t", 1, 1, dict(fields), tuple(equipment), ())


def monster(**kw):
    base = dict(to_hit=15, damage_min=4, damage_max=8, damage_kind=-1, defence=30, absorption=2, windup=7, recovery=3,
                prot_fire=50, prot_water=0, prot_air=0, prot_earth=0, prot_astral=0,
                res_blade=0, res_axe=0, res_bludgeon=0, res_pike=30, res_shooting=0)
    base.update(kw)
    return tmpl(MONSTER, **base)


def human(**kw):
    base = dict(body=41, reaction=39, mind=25, spirit=21, mana_max=-1, gender=0, windup=-1, recovery=-1,
                skill_general=0, skill_blade=25, skill_axe=0, skill_bludgen=0, skill_pike=0, skill_shooting=0)
    base.update(kw)
    return tmpl(HUMAN, **base)


# --- monsters from the template alone -----------------------------------------------------------

def test_monster_record_and_block_come_from_the_template():
    st = monster_stats(monster())
    assert st.record == AttackRecord(skill=15, lo=4, sp=4)
    assert (st.block.defence, st.block.absorb, st.block.prot[1], st.block.res[4]) == (30, 2, 50, 30)
    assert (st.windup, st.recovery, st.range, st.human, st.sure_hit) == (7, 3, 1, False, False)


def test_large_damage_is_stored_divided_by_15_with_bit_7():
    st = monster_stats(monster(damage_min=262, damage_max=517))
    assert (st.record.lo, st.record.sp) == (0x80 | 17, 17)
    st = monster_stats(monster(damage_min=4, damage_max=300))          # spread beyond min + 255 also scales
    assert (st.record.lo, st.record.sp) == (0x80 | 0, 19)


def test_damage_kinds():
    k1 = monster_stats(monster(damage_kind=1)).record
    assert (k1.lo, k1.sp, k1.lo2, k1.sp2) == (0, 0, 4, 4)
    k2 = monster_stats(monster(damage_kind=2)).record
    assert (k2.elo, k2.esp) == ((-4) & 0xFF, (-4) & 0xFF)
    k3 = monster_stats(monster(damage_kind=SURE_HIT_KIND))
    assert k3.sure_hit and (k3.record.lo, k3.record.sp) == (4, 4)


def test_template_minus_one_keeps_the_constructor_default_zero():
    st = monster_stats(monster(to_hit=-1, defence=-1, absorption=-1))
    assert (st.record.skill, st.block.defence, st.block.absorb) == (0, 0, 0)


# --- humans from the recompute ------------------------------------------------------------------

def test_human_recompute_without_equipment():
    st = human_stats(human())
    b, r = 1.1 ** 41, 1.1 ** 39
    assert st.record.skill == int((b + r) / 5) and st.record.lo == st.record.sp == int(b / 20)
    assert st.block.defence == 39 // 3
    assert st.block.prot == [0, 10, 10, 10, 10, 10]
    assert (st.windup, st.recovery, st.range, st.has_weapon, st.human) == (8, 4, 1, False, True)


def test_human_attributes_are_capped_by_class():
    st = human_stats(human(body=90, reaction=90, spirit=90))
    assert st.record.lo == int(1.1 ** 52 / 20) and st.block.defence == 50 // 3          # male fighter caps 52 / 50 / 46
    assert st.block.prot[1] == 46 // 2
    st = human_stats(human(body=90, reaction=90, spirit=90, mana_max=40, gender=1))      # female mage caps 46 / 48 / 50 / 52
    assert st.record.lo == int(1.1 ** 46 / 20) and st.block.defence == 48 // 3 and st.block.prot[1] == 52 // 2


def test_template_windup_and_recovery_are_used_when_set():
    st = human_stats(human(windup=10, recovery=6))
    assert (st.windup, st.recovery) == (10, 6)


# --- with the item table (install) ---------------------------------------------------------------

@pytest.fixture(scope="module")
def tables():
    from allods2.assets import AssetCache
    a = AssetCache(GFS)
    return {t.name: t for t in a.unit_stats().types}, a.items()


@needs_data
def test_example_a_orc_sword_has_template_plus_weapon_and_blade_type(tables):
    T, items = tables
    st = monster_stats(T["Orc_Sword"], items)
    assert (st.record.skill, st.record.lo, st.record.sp, st.record.kind) == (53, 12, 12, 1)
    assert (st.block.defence, st.block.absorb, st.range, st.windup, st.recovery) == (50, 2, 1, 11, 4)


@needs_data
def test_example_b_goblin_pike_is_a_pike(tables):
    T, items = tables
    st = monster_stats(T["Goblin_Pike"], items)
    assert (st.record.skill, st.record.lo, st.record.sp, st.record.kind) == (16, 8, 8, 4)
    assert st.block.defence == 31                       # the pike's own defence bonus


@needs_data
def test_scaled_monster_weapon_bonus_counts_times_15(tables):
    T, items = tables
    st = monster_stats(T["Orc_Sword.5"], items)
    assert (st.record.lo, st.record.sp) == (0x9A, 26)


@needs_data
def test_bows_raise_the_range_and_use_the_shooting_type(tables):
    T, items = tables
    st = monster_stats(T["Orc_Bow"], items)
    assert st.range == 4 and st.record.kind == 5 and st.windup == 21 and st.recovery == 7


@needs_data
def test_hero_fighter_numbers(tables):
    T, items = tables
    st = human_stats(T["Fighter_Hero"], items)
    r = st.record
    # base 1.1^41 / 20 = 2, to-hit (1.1^41 + 1.1^39) / 5 = 18; blade skill 25: +75 and +5; two-handed sword 13..26, to-hit +4
    assert (r.skill, r.lo, r.sp, r.kind) == (18 + 75 + 4, 2 + 5 + 13, 2 + 13, 1)
    assert (st.windup, st.recovery, st.weapon_weight, st.reaction, st.range) == (10, 4, 57, 39, 1)
    assert st.block.defence > 13 and st.block.absorb > 0


@needs_data
def test_every_template_builds_and_has_sane_numbers(tables):
    T, items = tables
    for name, t in T.items():
        st = unit_combat_stats(t, items)
        assert isinstance(st, CombatStats), name
        r, b = st.record, st.block
        assert 0 <= r.lo <= 255 and 0 <= r.sp <= 255 and -32768 <= r.skill <= 32767, name
        assert 1 <= st.range <= 25 and b.defence >= 0 and 0 <= st.windup <= 255 and 0 <= st.recovery <= 255, name
        if t.kind == HUMAN:
            assert all(0 <= p <= 100 for p in b.prot[1:]), name


@needs_data
def test_hit_rates_of_the_worked_examples_come_out_of_the_data(tables):
    T, items = tables
    a = monster_stats(T["Orc_Sword"], items)
    d = monster_stats(T["Ogre"], items)
    hits = sum(1 for roll in range(201) if a.record.skill + (roll - 100) > d.block.defence or roll - 100 >= 90)
    assert hits == 83
    b = monster_stats(T["Goblin_Pike"], items)
    tr = monster_stats(T["Troll"], items)
    assert sum(1 for roll in range(201) if b.record.skill + (roll - 100) > tr.block.defence or roll - 100 >= 90) == 16


# --- distribution ---------------------------------------------------------------------------------

@needs_data
def test_distribution_of_20000_blows_matches_the_exact_probabilities(tables):
    T, items = tables
    a = monster_stats(T["Orc_Sword"], items)
    d = monster_stats(T["Ogre"], items)
    rng, n = Rng(20231018), 20000
    dmg = [take_hit(a.record, d.block, rng) for _ in range(n)]
    p = 83 / 201
    hits = sum(1 for x in dmg if x > 0)
    sigma = math.sqrt(n * p * (1 - p))
    assert abs(hits - n * p) < 3 * sigma
    positive = [x for x in dmg if x > 0]
    assert min(positive) == 7 and max(positive) == 19                      # 12..24 minus 5 absorption
    assert abs(sum(positive) / len(positive) - 13.0) < 0.15               # uniform on 7..19
    # every value of the support appears
    assert set(positive) == set(range(7, 20))


def test_distribution_with_resistance_has_the_exact_zero_share():
    rec = AttackRecord(skill=500, lo=8, sp=8, kind=4)                     # always hits
    blk = ArmourBlock(defence=0, absorb=10)
    blk.res[4] = 30
    rng, n = Rng(5), 18000
    got = [take_hit(rec, blk, rng) for _ in range(n)]
    for v, share in ((0, 3 / 9), (1, 1 / 9), (2, 2 / 9), (3, 1 / 9), (4, 2 / 9)):
        c = got.count(v)
        sigma = math.sqrt(n * share * (1 - share))
        assert abs(c - n * share) < 4 * sigma, (v, c)
    assert max(got) == 4


# --- extremes ---------------------------------------------------------------------------------------

def test_school_skill_extremes_add_three_to_hit_and_a_fifth_of_a_point_of_damage_per_skill_point():
    from allods2.formats import itemdefs
    class Items:                                           # a one-sword item table: blade type, no bonuses
        def parse_equipment(self, text, slot=None):
            return ("code", ()) if slot == 0 else None

        def resolve(self, code, effects=()):
            from types import SimpleNamespace
            d = SimpleNamespace(kind=itemdefs.WEAPON, fields={"attack_type": 1, "windup": -1, "recovery": -1, "two_handed": 0},
                                can_use=lambda mage: True)
            s = SimpleNamespace(damage_min=0, damage_spread=0, to_hit=0, defence=0, absorption=0, range=1, weight=10)
            return SimpleNamespace(defn=d, stats=s, effects=())
    t = human(equipment=("sword",) + ("",) * 9)
    base = human_stats(t, Items(), skills=(0, 0, 0, 0, 0, 0)).record
    top = human_stats(t, Items(), skills=(0, 100, 0, 0, 0, 0)).record
    over = human_stats(t, Items(), skills=(0, 250, 0, 0, 0, 0)).record          # clamped to 100 like the recompute
    assert top.skill - base.skill == 300 and top.lo - base.lo == 20 and top.sp == base.sp
    assert over == top


def test_attribute_extremes_stay_in_byte_and_word_range():
    st = human_stats(human(body=250, reaction=250, spirit=250))
    assert 0 <= st.record.lo == st.record.sp <= 255 and st.record.skill == int((1.1 ** 52 + 1.1 ** 50) / 5)
    assert st.block.prot[1] == 46 // 2
    tiny = human_stats(human(body=0, reaction=0, spirit=0))
    assert (tiny.record.skill, tiny.record.lo, tiny.block.defence, tiny.block.prot[1]) == (0, 0, 0, 0)


def test_hard_difficulty_adds_50_to_to_hit_and_defence_of_a_monster():
    st = monster_stats(monster(), hard=True)
    assert (st.record.skill, st.block.defence) == (15 + 0x32, 30 + 0x32)
    assert monster_stats(monster()).record.skill == 15
