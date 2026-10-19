"""Spell math (I4a): flight time, level, damage, recovery.  Spec: docs/data/spells.md 9, 9c."""

import pytest

from allods2.formats import spelldefs
from engine.rng import Rng
from engine.sim import spells as sp
from engine.sim.combatstats import ArmourBlock
from spell_helpers import fire_arrow


def test_flight_ticks_is_truncated_distance_over_speed():
    s = fire_arrow()
    assert sp.flight_ticks(s, 7 * 256, 0) == 8                  # 1792 // 200
    assert sp.flight_ticks(s, 3 * 256, 4 * 256) == 6            # sqrt(768^2 + 1024^2) = 1280 // 200
    assert sp.flight_ticks(s, 0, 0) == 0


def test_lightning_and_prismatic_spray_release_at_ten():
    s = fire_arrow()
    object.__setattr__(s, "number", 10)
    assert sp.flight_ticks(s, 9 * 256, 0) == 10                 # FUN_00519db8 0x51be87: the server override
    assert sp.client_flight_ticks(s, 9 * 256, 0) == 5           # FUN_00519998: the visual message


def test_direct_delivery_has_no_flight():
    s = fire_arrow()
    s.fields["delivery"] = 1
    assert sp.flight_ticks(s, 5 * 256, 0) == 0


def test_level_from_skill_and_mind_clamps():
    assert sp.level_from(skill=40, mind=25) == 35               # 40 - 30 + 25
    assert sp.level_from(skill=0, mind=10) == 0                 # negative -> 0
    assert sp.level_from(skill=300, mind=100) == 255


def test_spell_damage_bounds_level_1_and_99():
    fa = fire_arrow()
    for level, lo, hi in ((1, 5, 10), (30, 10, 20), (99, 21, 43)):
        seen = {sp.spell_damage(fa, level, ArmourBlock(), Rng(seed)) for seed in range(400)}
        assert min(seen) == lo and max(seen) == hi


def test_spell_damage_protection_and_draw_order():
    fa = fire_arrow()
    block = ArmourBlock(prot=[0, 50, 0, 0, 0, 0])               # fire protection 50 %
    got = {sp.spell_damage(fa, 1, block, Rng(seed)) for seed in range(400)}
    assert got == {spelldefs.damage_taken(d, 50) for d in range(5, 11)}
    r = Rng(7)
    sp.spell_damage(fa, 1, ArmourBlock(), r)
    ref = Rng(7)
    ref.rand(200)                                               # FUN_00516f6f draws the to-hit roll even for a spell (combat.take_hit_detail)
    ref.rand(5)                                                 # then the elemental spread
    assert r.state == ref.state


def test_immune_target_takes_nothing_and_draws_nothing():
    r = Rng(7)
    assert sp.spell_damage(fire_arrow(), 1, ArmourBlock(), r, immune=True) == 0
    assert r.state == Rng(7).state


def test_recovery_ticks_formula():
    # +0x135 + hero_delay + rand(0..3) + complication (learned spell)
    assert sp.recovery_ticks(4, 2, 3, Rng(1)) in range(4 + 2 + 3, 4 + 2 + 3 + 4)
    assert sp.recovery_ticks(4, 0, 0, Rng(1)) in range(4, 8)


def test_wrapper_range_and_cost():
    w = sp.Wrapper(1)
    fa = fire_arrow()
    assert sp.wrapper_range(fa, w, level=1) == 7
    assert sp.wrapper_range(fa, w, level=60) == 9               # 7 + 60 // 30
    assert sp.wrapper_range(fa, sp.Wrapper(1, 1), level=1) == 7
