"""Pins from the combat research close-out (docs/engine/combat.md section 16): the byte timers, the s16 HP, the hit sound rule of
message 0x73, Bless / Curse inputs and the Invisibility end on a swing, monster damage = template + weapon (hand computed)."""

import pytest

from engine.rng import Rng
from engine.sim import AttackUnit, Simulation
from engine.sim.combat import hero_delay
from engine.view.damage import HitSoundGate, hit_sound_kind
from engine.world import UNIT_ID_BASE
from helpers import GFS, needs_data
from test_engine_combat import damages, fighter, ids, swing_starts, world


class _NoDelay(Rng):
    """The recovery draw `rand(3)` always 0 (every other draw is the CRT stream)."""
    __slots__ = ()

    def rand(self, n):
        return 0 if n == 3 else super().rand(n)


# --- 2. the byte timers ------------------------------------------------------------------------------

def test_a_windup_of_zero_wraps_to_256_ticks():
    """`dec byte; movsx; test; jne` at 0x50f50d: timer 0 -> 255 -> ... -> 0 takes 256 ticks (the data has no such row)."""
    w = world()
    a, foe = fighter(w, 1, 10, 10, windup=0, recovery=4), fighter(w, 2, 11, 10, owner=2, hp=1000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    starts = swing_starts(sim, a, 400)
    hits = [e.tick for e in damages(w)]
    assert hits and hits[0] == starts[0] + 256


def test_a_recovery_of_zero_wraps_to_256_ticks():
    """Recovery timer 0 (recovery 0, no hero delay, draw 0): the phase 7 decrement wraps, the next swing starts 256 + 2 ticks after the hit."""
    w = world()
    w.rng = _NoDelay(w.rng.state)
    a, foe = fighter(w, 1, 10, 10, windup=5, recovery=0), fighter(w, 2, 11, 10, owner=2, hp=100000)
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    starts = swing_starts(sim, a, 700)
    hits = [e.tick for e in damages(w)]
    assert len(hits) >= 2 and hits[1] - hits[0] == 5 + 256 + 2


def test_start_timer_is_a_byte():
    w = world()
    a, foe = fighter(w, 1, 10, 10, windup=250, recovery=4), fighter(w, 2, 11, 10, owner=2, hp=100000)
    a.combat.range = 1
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    starts = swing_starts(sim, a, 300)
    assert damages(w)[0].tick == starts[0] + 250


@needs_data
def test_no_data_row_can_wrap_a_timer_or_the_hp():
    """The install's numbers: windup 1..21 (monsters), 6..20 (weapons), recovery 1..38 / 4..16, dying time <= 18, so the largest timer is
    21 + arrow flight (range 20: 25) and 38 + 12 + 3; HP max <= 18432; the largest blow stays far from the s16 limits."""
    from allods2.assets import AssetCache
    from engine.sim.combatstats import monster_stats
    a = AssetCache(GFS)
    ts = a.unit_stats().types
    items = a.items()
    assert all(t.get("windup") != 0 and t.get("recovery") != 0 for t in ts)
    assert max(t.get("windup") for t in ts) + (20 * 256 + 128) // 200 < 128      # also below the signed byte
    assert max(t.get("recovery") for t in ts) + 12 + 3 < 128
    assert all(d.fields["windup"] != 0 and d.fields["recovery"] != 0 for d in items.defs if d.kind == "weapon")
    assert max(t.get("dying_time") for t in ts) <= 18
    assert max(t.get("hp_max") for t in ts) < 32767
    worst = 0
    for t in ts:
        if t.kind == "monster":
            r = monster_stats(t, items).record
            lo, sp = ((r.lo & 0x7F) * 15, r.sp * 15) if r.lo & 0x80 else (r.lo, r.sp)
            worst = max(worst, lo + sp + r.lo2 + r.sp2 + r.elo + r.esp)
    assert worst < 32767 - 10001                    # a hit on the lowest corpse HP (-10001, the decay floor) cannot wrap


def test_hero_delay_is_clamped_to_twelve():
    assert hero_delay(500, 0) == 12 and hero_delay(0, 100) == 0


# --- 1. message 0x73: sound rule ------------------------------------------------------------------------

def test_hit_sound_kinds():
    # the kind comes from the view's OLD HP (0x412a77-0x412aa4; the new HP is stored only afterwards at 0x412ace)
    assert hit_sound_kind(50, 50, 100) == 0                 # a blow that did not change the HP
    assert hit_sound_kind(100, 60, 100) == 1                # at least half left before the blow
    assert hit_sound_kind(100, 49, 100) == 1                # old HP decides: a big blow from full health is still "easy"
    assert hit_sound_kind(49, 40, 100) == 2                 # old HP below half (`hp_max / 2` = 50)
    assert hit_sound_kind(10, -9, 100) == 2
    assert hit_sound_kind(-10, -20, 100) is None            # old HP -10 or less: silent
    assert hit_sound_kind(10, -10, 100) == 2
    assert hit_sound_kind(40, 60, 100) == 2                 # a heal also plays, kind from the old HP
    assert hit_sound_kind(10, 5, 5) == 1 and hit_sound_kind(10, 2, 5) == 1 and hit_sound_kind(1, 0, 5) == 2


def test_hit_sound_gate_throttles_kinds_1_and_2_per_unit():
    g = HitSoundGate()
    assert g.allow(1, 1, 0) and not g.allow(1, 2, 1499) and g.allow(1, 2, 1500)
    assert g.allow(2, 1, 10) and g.allow(1, 0, 1501) and g.allow(1, 0, 1502)


# --- 5. Bless / Curse inputs and the Invisibility end ---------------------------------------------------

def _hits(w, attacker, foe, n=12):
    sim = Simulation(w)
    sim.step([AttackUnit(attacker.owner, ids(attacker), foe.id)])
    for _ in range(400):
        sim.step()
        if len(damages(w)) >= n:
            break
    return [e.amount for e in damages(w)]


def test_bless_always_hits_for_the_maximum_and_curse_for_the_minimum():
    for field, expect in (("bless", 7), ("curse", 3)):
        w = world(seed=5)
        a, foe = fighter(w, 1, 10, 10, lo=3, sp=4, windup=3, recovery=2), fighter(w, 2, 11, 10, owner=2, hp=100000)
        setattr(a, field, 101)                              # `c > rand(100)` with rand 0..100: 101 always fires (100 misses on a draw of 100)
        assert set(_hits(w, a, foe)) == {expect}
    w = world(seed=5)
    a, foe = fighter(w, 1, 10, 10, lo=3, sp=4, windup=3, recovery=2), fighter(w, 2, 11, 10, owner=2, hp=100000)
    assert len(set(_hits(w, a, foe))) > 2                   # without the effects the spread shows


def test_a_chance_of_zero_never_fires_but_still_draws():
    w1, w2 = world(seed=9), world(seed=9)
    res = []
    for w, ch in ((w1, None), (w2, 0)):
        a, foe = fighter(w, 1, 10, 10, lo=3, sp=4, windup=3, recovery=2), fighter(w, 2, 11, 10, owner=2, hp=100000)
        a.bless = ch
        res.append(_hits(w, a, foe, 6))
    assert res[0] != res[1]                                  # the Bless draw is spent even at chance 0 and shifts the stream
    w3 = world(seed=9)
    a, foe = fighter(w3, 1, 10, 10, lo=3, sp=4, windup=3, recovery=2), fighter(w3, 2, 11, 10, owner=2, hp=100000)
    a.bless = 0
    assert all(3 <= d <= 7 for d in _hits(w3, a, foe))


def test_invisibility_ends_when_the_swing_starts():
    w = world()
    a, foe = fighter(w, 1, 10, 10, windup=6, recovery=4), fighter(w, 2, 11, 10, owner=2, hp=1000)
    a.hidden = True
    sim = Simulation(w)
    sim.step([AttackUnit(1, ids(a), foe.id)])
    for _ in range(40):
        sim.step()
        if a.invis_ending or not a.hidden:
            break
    assert a.invis_ending or not a.hidden
    sim.step()
    assert not a.hidden and not a.invis_ending               # dropped by the effect pass of the next creature tick


# --- 3. monster damage = template + weapon (hand computed, docs/engine/combat.md 16.3) -------------------

HAND = {   # name: (skill, lo, sp, kind, elo, esp, elem, range)
    "Orc_Sword": (50 + 3, 8 + 4, 8 + 4, 1, 0, 0, 0, 1),                # template 8..16 + Bronze Long Sword 4/4, to-hit +3
    "Goblin_Pike": (15 + 1, 4 + 4, 4 + 4, 4, 0, 0, 0, 1),            # template 4..8 + Bronze Pike 4/4, to-hit +1
    "Orc_Sword.5": (420 + 4, 0x91 + 9, 17 + 9, 1, 0, 0, 0, 1),        # 262..517 stored /15 (0x91, 17) + the weapon's 9/9 -> 390..780
    "Dragon": (100 + 100, 10, 15 - 10, 0, 1, 7, 1, 8),                # flame thrower: to-hit := own to-hit (added again), fire 1..8
    "Bat_Sonic": (50 + 5, 1, 4 - 1, 5, 0, 0, 0, 4),                   # damage kind 3 (sure hit) + Sonic Beam 0/0, to-hit +5, shooting
}


@needs_data
@pytest.mark.parametrize("name", sorted(HAND))
def test_monster_template_plus_weapon(name):
    from allods2.assets import AssetCache
    from engine.sim.combatstats import monster_stats
    a = AssetCache(GFS)
    t = {x.name: x for x in a.unit_stats().types}[name]
    st = monster_stats(t, a.items())
    r = st.record
    skill, lo, sp, kind, elo, esp, elem, rng = HAND[name]
    assert (r.skill, r.lo, r.sp, r.kind, r.elo, r.esp, r.elem, st.range) == (skill, lo, sp, kind, elo, esp, elem, rng)
    assert st.sure_hit == (name == "Bat_Sonic")


@needs_data
def test_which_monsters_get_weapon_bonuses():
    from collections import Counter
    from allods2.assets import AssetCache
    from engine.sim.combatstats import monster_stats
    a = AssetCache(GFS)
    items = a.items()
    c = Counter()
    for t in a.unit_stats().types:
        if t.kind != "monster":
            continue
        base, full = monster_stats(t, None).record, monster_stats(t, items).record
        if (base.lo, base.sp) != (full.lo, full.sp):
            c["damage"] += 1
        elif base.elo != full.elo:
            c["element"] += 1
        elif base.kind != full.kind:
            c["type only"] += 1
    assert c == {"damage": 36, "element": 5, "type only": 56}
