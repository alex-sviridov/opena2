"""Combat formulas (I1): `take_hit`, gaps, octant, timers, the attack matrix.  Pure functions, synthetic inputs,
always run.  Spec: docs/engine/combat.md (C§ in the names = its sections)."""

import pytest

from engine.rng import Rng
from engine.sim.combat import (HitResult, attack_extra, attack_gap, can_attack, hero_delay, in_attack_range, octant,
                               reach_gap, resist, take_hit_detail)
from engine.sim.combatstats import ArmourBlock, AttackRecord
from engine.sim.pathfinding import Foot


class Script:
    """RNG double: `rand(n)` returns the next scripted value (checked against `n`) and records the call; `rand(0)` draws nothing."""

    def __init__(self, *values):
        self.values = list(values)
        self.calls = []

    def rand(self, n):
        if n == 0:
            return 0
        self.calls.append(n)
        v = self.values.pop(0)
        assert 0 <= v <= n, "scripted %d outside 0..%d" % (v, n)
        return v


def rec(**kw):
    return AttackRecord(**kw)


def blk(defence=0, absorb=0, prot=None, res=None):
    b = ArmourBlock(defence, absorb)
    if prot:
        b.prot = list(prot)
    if res:
        b.res = list(res)
    return b


def hit(r, b, *draws, **kw):
    return take_hit_detail(r, b, Script(*draws), **kw)


# --- the roll ----------------------------------------------------------------------------------

def test_hit_needs_skill_plus_roll_above_defence():
    r, b = rec(skill=53, lo=12, sp=12), blk(defence=70)
    assert hit(r, b, 0, 100 + 18).damage == 12                 # roll 18: 53 + 18 = 71 > 70
    assert hit(r, b, 0, 100 + 17).damage == 0                  # roll 17: 70 is not > 70
    assert hit(r, b, 0, 100 + 17).hit is False


def test_roll_of_90_or_more_always_hits_roll_below_minus_90_changes_nothing():
    r, b = rec(skill=0, lo=5, sp=0), blk(defence=1000)
    assert hit(r, b, 190).damage == 5 and hit(r, b, 189).damage == 0       # roll 90 / 89
    assert hit(r, b, 0).damage == 0                                       # roll -100
    assert hit(rec(skill=2000, lo=5, sp=0), blk(defence=10), 0).damage == 5   # skill beats the defence even at roll -100


def test_hit_probability_is_the_counted_rolls_over_201():
    def p(skill, defence):
        n = sum(1 for d in range(201) if hit(rec(skill=skill, lo=1), blk(defence=defence), d).hit)
        return n
    assert p(53, 70) == 83 and p(16, 100) == 16 and p(0, 10_000) == 11 and p(500, 0) == 201


def test_sure_hit_flag_skips_the_roll_and_the_absorption_but_still_draws_it():
    r, b = rec(skill=0, lo=10, sp=0), blk(defence=1000, absorb=4)
    s = Script(0)
    res = take_hit_detail(r, b, s, sure_hit=True)
    assert res.damage == 10 and s.calls == [200]


# --- draws and their order --------------------------------------------------------------------

def test_spread_is_drawn_before_the_roll_and_zero_spread_draws_nothing():
    s = Script(3, 150)
    take_hit_detail(rec(skill=100, lo=4, sp=6), blk(), s)
    assert s.calls == [6, 200]
    s = Script(150)
    take_hit_detail(rec(skill=100, lo=4, sp=0), blk(), s)
    assert s.calls == [200]


def test_damage_is_min_plus_the_spread_draw():
    r = rec(skill=500, lo=12, sp=12)
    assert [hit(r, blk(absorb=5), d, 200).damage for d in (0, 6, 12)] == [7, 13, 19]


# --- absorption, resistance ---------------------------------------------------------------------

def test_absorption_is_subtracted_and_floors_at_zero():
    r = rec(skill=500, lo=10, sp=0)
    assert hit(r, blk(absorb=3), 200).damage == 7
    assert hit(r, blk(absorb=10), 200).damage == 0
    assert hit(r, blk(absorb=99), 200).damage == 0


def test_resistance_percent_by_attack_type_with_the_plus_075_truncation():
    table = [resist(x, 30) for x in range(8)]
    assert table == [0, 1, 2, 2, 3, 4, 4, 5]
    assert resist(10, 100) == 0 and resist(10, 0) == 10
    for kind in range(1, 6):
        res = [0] * 6
        res[kind] = 50
        assert hit(rec(skill=500, lo=9, sp=0, kind=kind), blk(res=res), 200).damage == 5      # 4.5 + .75 -> 5


def test_attack_type_zero_reads_resistance_slot_zero_only():
    res = [0, 90, 90, 90, 90, 90]
    assert hit(rec(skill=500, lo=9, sp=0, kind=0), blk(res=res), 200).damage == 9


def test_worked_example_b_goblin_pike_against_troll():
    r = rec(skill=16, lo=8, sp=8, kind=4)
    b = blk(defence=100, absorb=10, res=[0, 0, 0, 0, 30, 0])
    got = [hit(r, b, d, 200).damage for d in range(9)]
    assert got == [0, 0, 0, 1, 2, 2, 3, 4, 4]


def test_resistance_above_100_percent_heals_in_the_part_and_total_is_floored():
    r = rec(skill=500, lo=10, sp=0)
    res = [0, 150, 0, 0, 0, 0]
    assert hit(rec(skill=500, lo=10, sp=0, kind=1), blk(res=res), 200).damage == 0


# --- the stored-/15 damage ---------------------------------------------------------------------

def test_scaled_damage_bytes_count_times_15_for_monsters_only():
    r = rec(skill=500, lo=0x91, sp=17)
    assert hit(r, blk(), 0, 200).damage == (0x11) * 15
    assert hit(r, blk(), 255, 200).damage == 17 * 15 + 255
    assert hit(r, blk(), 0, 200, human=True).damage == 0x91 + 0


# --- second part, elemental part ---------------------------------------------------------------

def test_second_part_ignores_the_roll_and_uses_the_water_protection():
    r = rec(skill=0, lo=0, sp=0, lo2=10, sp2=0)
    assert hit(r, blk(defence=1000, prot=[0, 0, 50, 0, 0, 0]), 0).damage == 5          # trunc(10 * 50 / 100 + 0.75)
    assert hit(r, blk(defence=1000), 0).damage == 10


def test_elemental_part_needs_the_attack_roll_or_an_empty_physical_part():
    # physical 0, elemental 3 + rand(2) fire, 50 % protection
    r = rec(skill=0, lo=0, sp=0, elo=3, esp=2, elem=1)
    b = blk(defence=1000, prot=[0, 50, 0, 0, 0, 0])
    assert hit(r, b, 0, 2).damage == resist(5, 50)                      # roll draw first, then the elemental spread
    # physical present: the elemental part appears only when skill + roll > defence (not by the 90 rule)
    r2 = rec(skill=0, lo=1, sp=0, elo=4, esp=0, elem=2)
    assert hit(r2, blk(defence=1000), 190).damage == 1                   # 90 rule: physical only
    assert hit(rec(skill=2000, lo=1, sp=0, elo=4, esp=0, elem=2), blk(defence=10), 100).damage == 5


def test_each_element_reads_its_own_protection():
    for e in range(1, 6):
        prot = [0] * 6
        prot[e] = 100
        assert hit(rec(skill=0, lo=0, sp=0, elo=9, esp=0, elem=e), blk(prot=prot), 0).damage == 0
        prot[e] = 0
        assert hit(rec(skill=0, lo=0, sp=0, elo=9, esp=0, elem=e), blk(prot=prot), 0).damage == 9


# --- Bless, Curse, immune --------------------------------------------------------------------

def test_bless_forces_maximum_when_the_chance_beats_the_draw_and_draws_first():
    r = rec(skill=500, lo=4, sp=6)
    s = Script(49, 200)                                    # bless draw 49 < chance 50 -> max, no spread draw
    assert take_hit_detail(r, blk(), s, bless=50).damage == 10 and s.calls == [100, 200]
    s = Script(50, 3, 200)                                 # 50 is not < 50 -> normal draw
    assert take_hit_detail(r, blk(), s, bless=50).damage == 7 and s.calls == [100, 6, 200]


def test_curse_forces_minimum():
    r = rec(skill=500, lo=4, sp=6)
    s = Script(10, 200)
    assert take_hit_detail(r, blk(), s, curse=50).damage == 4 and s.calls == [100, 200]
    s = Script(60, 6, 200)
    assert take_hit_detail(r, blk(), s, curse=50).damage == 10 and s.calls == [100, 6, 200]


def test_bless_then_curse_both_draw():
    r = rec(skill=500, lo=4, sp=6)
    s = Script(10, 10, 200)
    assert take_hit_detail(r, blk(), s, bless=50, curse=50).damage == 10 and s.calls == [100, 100, 200]


def test_immune_defender_takes_zero_without_a_draw():
    s = Script()
    assert take_hit_detail(rec(skill=500, lo=9, sp=9), blk(), s, immune=True).damage == 0 and s.calls == []


def test_damage_is_never_negative_and_zero_armour_passes_everything():
    assert hit(rec(skill=500, lo=3, sp=0), blk(), 200).damage == 3
    assert hit(rec(skill=500, lo=0, sp=0), blk(absorb=50), 200).damage == 0
    assert isinstance(hit(rec(), blk(), 100), HitResult)


def test_max_armour_stops_everything_but_the_90_rule_hit_is_absorbed():
    r = rec(skill=100, lo=20, sp=20)
    b = blk(defence=32767, absorb=32767)
    assert all(hit(r, b, d, x).damage == 0 for d in (0, 20) for x in range(0, 201, 10))


# --- the RNG integration ---------------------------------------------------------------------

def test_take_hit_draws_from_the_real_rng_in_a_reproducible_order():
    a, b = Rng(7), Rng(7)
    r, d = rec(skill=60, lo=5, sp=5), blk(defence=50, absorb=1)
    assert [take_hit_detail(r, d, a).damage for _ in range(50)] == [take_hit_detail(r, d, b).damage for _ in range(50)]
    assert a.state == b.state


# --- geometry -------------------------------------------------------------------------------

def f(x, y, size=1, sx=128, sy=128):
    return Foot(x, y, size, sx, sy)


def test_reach_gap_counts_touching_as_one():
    assert reach_gap(f(10, 10), f(11, 10)) == 1
    assert reach_gap(f(10, 10), f(11, 11)) == 1
    assert reach_gap(f(10, 10), f(12, 10)) == 2
    assert reach_gap(f(10, 10), f(10, 10)) == 1
    assert reach_gap(f(10, 10, 2), f(12, 10)) == 1             # a 2x2 footprint reaches the cell beside it
    assert reach_gap(f(10, 10), f(14, 13)) == 4


def test_attack_gap_is_chebyshev_with_a_half_cell_of_slack():
    assert attack_gap(f(10, 10), f(11, 10)) == 1
    assert attack_gap(f(10, 10), f(11, 10, sx=128 + 100)) == 1          # 356 <= 384
    assert attack_gap(f(10, 10), f(11, 10, sx=128 + 130)) == 1          # 386: (386 + 64) >> 8 = 1
    assert attack_gap(f(10, 10), f(11, 10, sx=128 + 191)) == 1          # 447
    assert attack_gap(f(10, 10), f(11, 10, sx=128 + 192)) == 2          # 448: (448 + 64) >> 8 = 2
    assert attack_gap(f(10, 10), f(12, 10)) == 2
    assert attack_gap(f(10, 10), f(13, 12)) == 3
    assert attack_gap(f(10, 10, 2), f(12, 10)) == 1


def test_attack_gap_matches_the_formula_for_far_units():
    for dx in range(0, 40):
        d = dx * 256
        want = 1 if d <= 384 else (d + 64) >> 8
        assert attack_gap(f(10, 10), f(10 + dx, 10)) == want


def test_in_attack_range_compares_the_gap_with_the_range_byte():
    assert in_attack_range(f(10, 10), f(11, 10), 1) and not in_attack_range(f(10, 10), f(12, 10), 1)
    assert in_attack_range(f(10, 10), f(14, 10), 4)


def test_octant_follows_the_ratio_rule_and_ties():
    cases = {(0, -5): 0, (5, -5): 32, (5, 0): 64, (5, 5): 96, (0, 5): 128, (-5, 5): 160, (-5, 0): 192, (-5, -5): 224,
             (1, -5): 0, (2, -5): 0, (3, -4): 32, (4, -3): 32, (5, -2): 64, (5, -1): 64, (-1, -5): 0, (-2, -5): 0,
             (5, 2): 64, (2, 5): 128, (3, 4): 96, (-3, 4): 160, (-4, 3): 160, (-4, -3): 224}
    for (dx, dy), want in cases.items():
        assert octant(f(20, 20), f(20 + dx, 20 + dy)) == want, (dx, dy)


def test_octant_of_an_adjacent_cell_equals_the_step_facing():
    from engine.sim.movement import DIR_DX, DIR_DY
    for d in range(8):
        assert octant(f(20, 20), f(20 + DIR_DX[d], 20 + DIR_DY[d])) == d * 32


# --- timers and matrix -----------------------------------------------------------------------

def test_hero_delay_is_the_clamped_weapon_and_reaction_term():
    assert hero_delay(20, 30) == 1                       # (20 + 0) / 12
    assert hero_delay(20, 20) == 5                       # (20 + 50) / 12
    assert hero_delay(0, 60) == 0                        # negative clamps to 0
    assert hero_delay(500, 0) == 12                      # capped at 12


def test_attack_extra_ticks_only_beyond_one_cell():
    assert attack_extra(1) == 0
    assert attack_extra(2) == (2 * 256 + 128) // 200
    assert attack_extra(5) == (5 * 256 + 128) // 200


def test_attack_matrix_blocks_ground_and_ghost_melee_against_flyers():
    # attacker (movement type, range) vs target (movement type, range)
    assert not can_attack(1, 1, 3, 1)
    assert not can_attack(2, 1, 3, 1)
    assert can_attack(3, 1, 3, 1)
    assert can_attack(1, 4, 3, 1)                        # a shooter reads row 0: allowed
    assert can_attack(1, 1, 1, 1) and can_attack(1, 1, 2, 1) and can_attack(1, 1, 1, 4)
    assert can_attack(2, 1, 1, 1) and can_attack(3, 1, 2, 1)


@pytest.mark.parametrize("n", [1, 7, 199, 200])
def test_resist_zero_percent_is_identity(n):
    assert resist(n, 0) == n
