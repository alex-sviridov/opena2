"""The spell flights as client projectiles (K9 follow-up): `FUN_0046707e` makes the missile of a unit-target cast on the cast action's ShootDelay tick,
lifetime `trunc(dist / 200)` (Fire Ball `/ 0x180`), age 0, footprint-centre start; the server carrier is independent.  Synthetic worlds, always run.
Docs: docs/engine/rendering.md "Arrows and shots", docs/engine/effects.md."""

import types

from engine.sim import effects
from engine.world import SpellCast

from test_engine_bolts import FakeAssets, FakeSet, caster, foe, start, world

C = 256
FIRE_ARROW, FIRE_BALL, ICE_MISSILE, DIAMOND_DUST = 1, 2, 5, 16


def cast(spell, delay=8, **kw):
    w = world()
    w.assets = FakeAssets(FakeSet(delay=delay))
    c = caster(w, **kw)
    t = foe(w, 2, 27, 20)
    w.tick = 30
    start(w, c, t, spell=spell)
    return w, c, t


def test_the_four_missile_spells_make_a_client_flight_at_the_shoot_delay_tick():
    for spell, pid, speed in ((FIRE_ARROW, 10, 200), (FIRE_BALL, 12, 0x180), (ICE_MISSILE, 18, 200), (DIAMOND_DUST, 40, 200)):
        w, c, t = cast(spell)
        (a,) = [x for x in w.arrows if x.pid == pid]
        assert (a.shooter, a.target, a.born, a.spell, a.speed, a.live) == (c.id, t.id, 38, True, speed, False)


def test_other_spells_make_no_flight():
    for spell in (10, 11, 20, 21, 27, 28, 29, 4, 7):        # Lightning / Spray have bolts; Bless, Haste, Shield, Curse, Slow, protections, Blizzard: lifetime 0
        w, c, t = cast(spell)
        assert not w.arrows, spell


def test_a_cell_cast_makes_the_flight_through_the_cast_action_too():
    """The `0x86` handler picks the target by the spell's kind: a cell target is `+0x90 / +0x94 = cell * 256 + 0x80` (`0x415370`); `0x8b` is the hidden caster's."""
    w = world()
    w.assets = FakeAssets(FakeSet(delay=3))
    c = caster(w)
    w.tick = 10
    effects.spawn_cast_fx(w, c, FIRE_ARROW, None, (27, 20))
    (a,) = w.arrows
    assert (a.target, a.cell, a.born, a.spell) == (None, (27, 20), 13, True)
    run(w, 3)
    assert a.live and a.age == 1
    run(w, a.steps)
    assert (a.x, a.y) == (27 * C + 128, 20 * C + 128) and a.steps == 0


def test_the_hidden_casters_0x8b_form_is_made_at_once_with_age_minus_one():
    w = world()
    w.assets = FakeAssets(FakeSet(delay=3))
    c = caster(w)
    c.type_id = 0
    t = foe(w, 2, 27, 20)
    w.tick = 10
    effects.spawn_cast_fx(w, c, FIRE_ARROW, t, None, 8)                  # the message's flight ticks
    (a,) = w.arrows
    assert (a.live, a.age, a.steps, a.born) == (True, -1, 8, 10) and (a.x, a.y) == (c.x * C + 128, c.y * C + 128)
    effects.arrow_system(w)                                              # the same view step: the projectile list ticks it once
    assert (a.age, a.steps) == (0, 7)
    for _ in range(7):
        effects.arrow_system(w)
    assert (a.x, a.y) == (t.x * C + t.sub_x, t.y * C + t.sub_y) and a.steps == 0
    effects.spawn_cast_fx(w, c, FIRE_ARROW, t, None, 0)
    assert len(w.arrows) == 1                                            # a flight of 0 ticks is never seen
    c.type_id = 1
    effects.spawn_cast_fx(w, c, 20, t, None, 8)
    assert len(w.arrows) == 1                                            # Bless: no flight at all


def test_no_flight_for_a_missing_delay_or_a_vanished_target():
    w = world()
    w.assets = FakeAssets(FakeSet(delay=12, n=12))
    c = caster(w)
    effects.spawn_cast_fx(w, c, FIRE_ARROW, foe(w, 3, 27, 20), None)
    assert not w.arrows                                                  # ShootDelay past the sequence never fires
    w.assets = FakeAssets(FakeSet(delay=1))
    t = foe(w, 4, 27, 20)
    effects.spawn_cast_fx(w, c, FIRE_ARROW, t, None)
    del w.units[t.id]
    run(w, 3)
    assert not w.arrows                                                  # `FUN_0046707e` returns when the target lookup fails


def run(w, ticks):
    for _ in range(ticks):
        w.tick += 1
        effects.arrow_system(w)


def test_the_flight_lasts_dist_over_200_steps_and_lands_on_the_targets_centre():
    w, c, t = cast(FIRE_ARROW)
    run(w, 7)
    assert w.arrows and not w.arrows[0].live                 # before ShootDelay: nothing
    run(w, 1)
    a = w.arrows[0]
    assert a.live and a.age == 1 and a.steps == (7 * C) // 200 - 1       # 7 cells = 1792 units -> 8 steps, one already made
    run(w, a.steps)
    assert (a.x, a.y) == (t.x * C + t.sub_x, t.y * C + t.sub_y) and a.steps == 0
    run(w, 1)
    assert not w.arrows


def test_the_fire_ball_is_slower_and_the_trail_keeps_six_pre_move_points():
    w, c, t = cast(FIRE_BALL)
    run(w, 8)
    a = w.arrows[0]
    assert a.steps + a.age == (7 * C) // 0x180                           # 1792 / 384 = 4 steps
    w, c, t = cast(FIRE_ARROW)
    seen = []
    for _ in range(14):                                       # the swing tick .. the arrival
        w.tick += 1
        for a in w.arrows:
            if a.live:
                seen.append((a.x, a.y))                       # the position after the previous step = before this one
        effects.arrow_system(w)
        if w.arrows and w.arrows[0].live and w.arrows[0].age == 1:
            origin = (w.arrows[0].trail[0])
    assert origin == effects.shoot_origin(w, c)               # the first trail point is the start: the position before the first move
    w, c, t = cast(FIRE_ARROW)
    run(w, 8 + 5)
    a = w.arrows[0]
    assert a.age == 6 and len(a.trail) == 6
    run(w, 1)
    assert len(a.trail) == 6 and a.trail[0] != origin        # the oldest point dropped
