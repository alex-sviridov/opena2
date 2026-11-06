"""Prismatic Spray chain (`FUN_00519c04` -> `FUN_00579ddf`) and the client bolts of Lightning / Prismatic Spray (projectiles 28 / 30, `FUN_0046707e`,
`FUN_0046d46a`, `FUN_0046d0ef`): target list, chain release, bolt lifetime, phases, lights, draw.  Synthetic worlds, always run.
Docs: docs/engine/effects.md 11, docs/mechanics/lighting.md 3."""

import types

import numpy as np

from engine.sim import ai, effects, spells
from engine.view import boltline, build_draw_list, lights
from engine.world import SpellCast
from helpers import projectile, sprite_file
from spell_helpers import effect_table
from test_engine_ai_casting import monster, world as cast_world
from test_engine_burning_sprites import Assets
from test_engine_objects import PLAIN, cam

SPRAY, LIGHTNING = 11, 10


def world(seed=1):
    w = cast_world(seed, True)
    w.spell_table = effect_table()
    return w


def caster(w, uid=1, x=20, y=20, level=10, **kw):
    """A mage of owner 2 that knows the Spray and Lightning, 500 mana, facing east, spell level `level` (skill - 30 + Mind with Mind 10); its enemies
    are owner 1's units."""
    return monster(w, uid, x, y, owner=2, hp=200, known=(1 << 10) | (1 << 11), mana=500, mind=10, skills=(level + 20,) * 5, **kw)


def foe(w, uid, x, y, hp=40):
    return monster(w, uid, x, y, owner=1, hp=hp)


def ids(w, units):
    return [u.id for u in units]


# --- the target list (FUN_00579ddf) ---------------------------------------------------------------------------------------------------

def test_the_list_is_the_target_then_the_nearest_foes_by_gap_then_turn():
    w = world()
    c = caster(w)
    t = foe(w, 2, 24, 20)                                       # the target, 3 free cells east (gap level 4)
    a, b, far = foe(w, 3, 22, 20), foe(w, 4, 21, 21), foe(w, 5, 26, 20)
    got = ai.spray_targets(w, c, t, 7, 7)
    order = sorted((a, b, far), key=lambda u: ai.spray_distance(c, u))
    assert got[0] is t and got[1:] == order                     # lowest (gap << 8) + turn first
    assert order == [b, a, far] and ai.spray_distance(c, b) == (1 << 8) + 32      # touching diagonally, 32 turn steps off the facing


def test_the_list_is_cut_to_count_and_the_target_is_never_listed_twice():
    w = world()
    c = caster(w)
    t = foe(w, 2, 21, 20)
    others = [foe(w, 3 + i, 22 + i, 20) for i in range(5)]
    got = ai.spray_targets(w, c, t, 3, 7)
    assert len(got) == 3 and got[0] is t and got.count(t) == 1
    assert got[1:] == others[:2]                                # target first, then the nearest two (the target took a selection round)


def test_the_reach_filter_is_score_le_reach_times_256():
    w = world()
    c = caster(w)
    t = foe(w, 2, 21, 20)
    near, edge = foe(w, 3, 22, 20), foe(w, 4, 25, 20)           # gap levels 2 and 5, both straight ahead (turn 0)
    assert ai.spray_distance(c, near) == 2 << 8 and ai.spray_distance(c, edge) == 5 << 8
    assert ai.spray_targets(w, c, t, 7, 5) == [t, near, edge]   # level 5 == reach with no turn: kept
    assert ai.spray_targets(w, c, t, 7, 4) == [t, near]


def test_an_empty_pool_gives_only_the_target_and_allies_are_not_listed():
    w = world()
    c = caster(w)
    t = foe(w, 2, 21, 20)
    friend = monster(w, 3, 22, 20, owner=2)
    assert ai.spray_targets(w, c, t, 7, 7) == [t]               # (an ally is not at war with the owner)
    assert friend not in ai.spray_targets(w, c, t, 7, 7)


def test_dying_foes_only_join_when_no_living_one_is_in_sight():
    w = world()
    c = caster(w)
    t = foe(w, 2, 21, 20)
    dying = foe(w, 3, 22, 20, hp=0)
    assert dying not in ai.spray_targets(w, c, t, 7, 7)         # t lives: the dying one stays in the dead list
    t.hp = 0
    assert dying in ai.spray_targets(w, c, t, 7, 7)             # nobody living: the dead list goes back into the pool


# --- the chain release ----------------------------------------------------------------------------------------------------------------

def start(w, c, t, spell=SPRAY, item_count=None):
    cast = SpellCast(spell, target=t.id, item_count=item_count)
    c.cast = cast
    st = effects_stats(w, c)
    assert spells.cast_start(w, c, cast, st)
    return cast, st


def effects_stats(w, c):
    from engine.sim.combat import combat_stats
    return combat_stats(w, c)


def test_the_chain_releases_every_target_at_the_cast_start_and_spends_the_mana_once():
    w = world()
    c = caster(w, level=40)                           # level 40: 40 // 20 + 2 = 4 targets
    t = foe(w, 2, 22, 20)
    foes = [foe(w, 3 + i, 23 + i, 20) for i in range(6)]
    cast, st = start(w, c, t)
    assert c.mana == 500 - w.spell_table.get(SPRAY).mana_cost
    assert cast.chain == (t.id, foes[0].id, foes[1].id, foes[2].id)
    assert [(k.target, k.kind, k.ticks_left) for k in w.carriers] == [(i, "missile", 10) for i in cast.chain]
    assert not w.unbuilt_casts
    (b,) = w.bolts                                              # the cast message starts the cast action; its ShootDelay tick makes the bolt (no unit sets here: tick 0)
    assert (b.pid, b.targets, b.born) == (30, cast.chain, w.tick)


def test_the_target_count_is_capped_at_seven_and_floors_at_two():
    w = world()
    c = caster(w, level=0)
    t = foe(w, 2, 22, 20)
    [foe(w, 3 + i, 23, 18 + i) for i in range(8)]
    assert len(start(w, c, t)[0].chain) == 2
    w = world()
    c = caster(w, level=200)                          # 200 // 20 + 2 = 12 -> 7
    t = foe(w, 2, 22, 20)
    [foe(w, 3 + i, 23, 18 + i) for i in range(10)]
    assert len(start(w, c, t)[0].chain) == 7


def test_the_release_does_not_make_the_bolt():
    w = world()
    c = caster(w, level=40)
    t = foe(w, 2, 22, 20)
    w.tick = 50
    cast, st = start(w, c, t)
    n, bolts = len(w.carriers), list(w.bolts)
    w.tick = 60
    spells.cast_release(w, c, cast, st)
    assert len(w.carriers) == n                                 # FUN_00519d7f skips spell 11
    assert w.bolts == bolts and (bolts[0].pid, bolts[0].caster, bolts[0].targets, bolts[0].born) == (30, c.id, cast.chain, 50)


def test_a_cast_from_an_item_uses_the_item_level_for_the_count():
    w = world()
    c = caster(w, level=0)
    t = foe(w, 2, 22, 20)
    [foe(w, 3 + i, 23, 18 + i) for i in range(8)]
    assert len(start(w, c, t, item_count=60)[0].chain) == 5     # 60 // 20 + 2


def test_lightning_has_no_chain_and_its_bolt_comes_from_the_cast_message():
    w = world()
    c = caster(w)
    t = foe(w, 2, 22, 20)
    w.tick = 4
    cast, st = start(w, c, t, spell=LIGHTNING)
    assert cast.chain is None and w.carriers == []
    (b,) = w.bolts
    assert (b.pid, b.targets, b.born) == (28, (t.id,), 4)
    w.tick = 9
    spells.cast_release(w, c, cast, st)                         # the release makes the damage carrier only
    assert len(w.bolts) == 1 and len(w.carriers) == 1


# --- the client bolt ------------------------------------------------------------------------------------------------------------------

def test_a_bolt_lives_13_ticks_and_walks_the_ping_pong_phases():
    w = world()
    c = caster(w)
    t = foe(w, 2, 24, 20)
    w.tick = 100
    effects.spawn_bolt(w, c, 28, (t.id,))
    seen = []
    for tick in range(100, 114):
        w.tick = tick
        effects.bolt_system(w, [])
        if w.bolts:
            seen.append(lights.bolt_phase(tick - 100 + 1))
    assert seen == [4, 3, 2, 1, 0, 1, 2, 1, 0, 1, 2, 3, 4] and w.bolts == []


def test_the_bolt_light_is_phase_times_10_on_the_2x2_vertices_of_each_point_cell():
    assert lights.bolt_vertices([(5, 6)], 3) == {(5, 6): 30, (6, 6): 30, (5, 7): 30, (6, 7): 30}
    w = world()
    c = caster(w)
    t = foe(w, 2, 26, 20)
    effects.spawn_bolt(w, c, 28, (t.id,))
    m4 = lights.light_map(w, None, w.tick)                      # age 1: phase 4 -> 40
    assert m4 and set(m4.values()) == {40}
    assert lights.light_map(w, None, w.tick + 4) and set(lights.light_map(w, None, w.tick + 4).values()) == {0}      # age 5: phase 0
    assert lights.light_map(w, None, w.tick + 13) == {} and lights.light_map(w, None, w.tick - 1) == {}


def test_the_spray_draws_a_segment_per_list_entry_with_the_variant_row():
    w = world()
    c = caster(w)
    ts = [foe(w, 2 + i, 24, 18 + 2 * i) for i in range(3)]
    effects.spawn_bolt(w, c, 30, tuple(t.id for t in ts))
    segs = lights.bolt_segments(w, w.bolts[0], w.tick)
    assert [v for v, _ in segs] == [0, 1, 2]
    assert all(len(p) > 2 for _, p in segs)
    ts[1].hp = 0
    w.units.pop(ts[1].id)                                      # a target that is gone has no segment (the view lookup fails)
    assert [v for v, _ in lights.bolt_segments(w, w.bolts[0], w.tick)] == [0, 2]


# --- the exact line (FUN_004c8863 / FUN_004c819d / FUN_004c8069) and the spawn --------------------------------------------------------------

def test_the_rand_is_the_msvc_crt_lcg():
    r = boltline.CrtRand(1)                                     # FUN_00583290: holdrand * 214013 + 2531011, bits 16..30
    assert [r() for _ in range(5)] == [41, 18467, 6334, 26500, 19169]


def test_the_spline_is_the_quadratic_through_three_points_stepped_by_6():
    xs, ys = [], []
    boltline.spline(100.0, 10.0, 130.0, 25.0, 160.0, 16.0, xs, ys)
    assert xs == [100.0 + 6 * i for i in range(10)]               # x < 160, step 6.0
    coef = np.polyfit([100.0, 130.0, 160.0], [10.0, 25.0, 16.0], 2)
    assert np.allclose(ys, np.polyval(coef, xs), atol=1e-6) and abs(ys[0] - 10.0) < 1e-6
    xs, ys = [], []
    boltline.spline(5.0, 0.0, 5.0, 0.0, 5.0, 0.0, xs, ys)         # x1 == x3: no sample
    assert xs == []


def test_the_control_line_stays_within_015_length_of_the_axis_and_is_jagged():
    for seed in range(30):
        xs, ys = boltline.control_line(0.0, 0.0, 200.0, 0.0, 200.0, boltline.CrtRand(seed * 7919 + 1))
        assert xs[0] == 0.0 and abs(ys[0]) < 1e-9 and all(0 < b - a <= 6.0 for a, b in zip(xs, xs[1:]))      # each span restarts its 6 px stepping
        assert all(abs(y) <= 0.15 * 200 for y in ys)               # the retry rule
        assert len(xs) >= 30 and max(ys) - min(ys) > 0.5            # 200 px / 6 = 34 samples, with real lateral jumps


def test_the_control_line_draws_in_the_exes_order():
    """One hand-followed draw: the sign by `rand & 1`, then per iteration `rand % 7` and `rand % 50`; the same stream, replayed, gives the same line."""
    r1, r2 = boltline.CrtRand(12345), boltline.CrtRand(12345)
    assert boltline.control_line(0.0, 0.0, 120.0, 0.0, 120.0, r1) == boltline.control_line(0.0, 0.0, 120.0, 0.0, 120.0, r2)
    assert r1.state == r2.state and r1.state != 12345


def test_build_rotates_the_line_onto_the_target_and_truncates():
    pts = boltline.build(10.0, 20.0, 210.0, 20.0, boltline.CrtRand(3))
    assert pts[0] == (10, 20) and all(isinstance(v, int) for p in pts for v in p)
    assert pts[-1][0] > 200 - 6 and max(abs(y - 20) for _, y in pts) <= 0.15 * 200 + 1     # the last sample lies < 6 px short of the end
    d = boltline.build(0.0, 0.0, 0.0, 200.0, boltline.CrtRand(3))                           # vertical: the line is the horizontal one turned 90 degrees
    h = boltline.build(0.0, 0.0, 200.0, 0.0, boltline.CrtRand(3))
    assert len(d) == len(h) and all(abs(a[0] + b[1]) <= 1 and abs(a[1] - b[0]) <= 1 for a, b in zip(d, h))
    assert boltline.build(5.0, 5.0, 5.0, 5.0, boltline.CrtRand(1)) == []                    # zero length: no point


def test_lines_differ_between_ticks_and_are_repeatable():
    w = world()
    c = caster(w)
    t = foe(w, 2, 26, 20)
    effects.spawn_bolt(w, c, 28, (t.id,))
    b = w.bolts[0]
    a1, a2 = lights.bolt_segments(w, b, w.tick)[0][1], lights.bolt_segments(w, b, w.tick + 1)[0][1]
    assert a1 == lights.bolt_segments(w, b, w.tick)[0][1] and a1 != a2


def test_the_target_end_is_the_feet_with_the_flyers_altitude_and_no_chest_height():
    w = world()
    c = caster(w)
    t = foe(w, 2, 26, 20)
    effects.spawn_bolt(w, c, 28, (t.id,))
    b = w.bolts[0]
    pts = lights.bolt_segments(w, b, w.tick)[0][1]
    ex, ey = (26 * 256 + 128) >> 3, (20 * 256 + 128) >> 3                # flat ground: the screen y of the cell centre
    assert abs(pts[-1][0] - ex) <= 6 and abs(pts[-1][1] - ey) < 0.15 * 192
    assert abs(pts[0][0] - (20 * 256 + 128) // 8) <= 1 and pts[0][1] == (20 * 256 + 128) // 8


class FakeSet:
    def __init__(self, delay=8, so=None, z=0, n=12):
        self.t = types.SimpleNamespace(ShootOffset=so or [], CenterX=64, CenterY=78, Z=z, SelectionX1=0, SelectionX2=0, SelectionY1=0, SelectionY2=0)
        self._ev = {"impact": 8, "release": delay} if delay is not None and delay < n else {"impact": 8}

    def attack_events(self, kind):
        return self._ev


class FakeAssets:
    def __init__(self, aset):
        self.aset = aset

    def unit_set(self, tid):
        return self.aset


def test_the_bolt_spawns_on_the_shoot_delay_tick_of_the_cast_action():
    w = world()
    w.assets = FakeAssets(FakeSet(delay=8))
    c = caster(w)
    t = foe(w, 2, 22, 20)
    w.tick = 30
    cast, st = start(w, c, t)
    (b,) = w.bolts
    assert b.born == 38 and c.action_start_tick == 30           # action tick 8 of the cast = world tick 38
    assert lights.bolt_age(b, 37) is None and lights.bolt_age(b, 38) == 1 and lights.bolt_age(b, 50) == 13 and lights.bolt_age(b, 51) is None


def test_a_shoot_delay_past_the_sequence_never_fires():
    w = world()
    w.assets = FakeAssets(FakeSet(delay=12, n=12))              # delay 12 >= length 12
    c = caster(w)
    t = foe(w, 2, 22, 20)
    start(w, c, t)
    assert w.bolts == []


def test_the_bolt_is_dropped_when_its_first_target_is_gone_on_the_spawn_tick():
    w = world()
    w.assets = FakeAssets(FakeSet(delay=3))
    c = caster(w)
    t = foe(w, 2, 22, 20)
    w.tick = 10
    start(w, c, t)
    w.units.pop(t.id)
    for k in (10, 11, 12):
        w.tick = k
        effects.bolt_system(w, [])
        assert len(w.bolts) == 1
    w.tick = 13
    effects.bolt_system(w, [])
    assert w.bolts == []                                        # FUN_0046707e: the +0x8e lookup fails, nothing is made


def test_the_origin_is_the_shoot_offset_point_by_direction():
    w = world()
    so = list(range(40, 56))                                    # 8 (x, y) pairs
    w.assets = FakeAssets(FakeSet(so=so))
    c = caster(w, x=20, y=20)
    c.facing = 0x40                                             # direction 4: k = (4 - 8) & 14 = 12 -> (SO[12], SO[13]) = (52, 53)
    assert effects.shoot_origin(w, c) == (20 * 256 + 128 - (64 - 52) * 8, 20 * 256 + 128 - (78 - 53) * 8)
    c.facing = 0xB0                                             # direction 11: k = 3 & 14 = 2 -> (42, 43)
    assert effects.shoot_origin(w, c) == (20 * 256 + 128 - (64 - 42) * 8, 20 * 256 + 128 - (78 - 43) * 8)
    w.assets = FakeAssets(FakeSet(so=[]))                       # no table: only the unit's own centre (no selection box here)
    assert effects.shoot_origin(w, c) == (20 * 256 + 128 - 64, 20 * 256 + 128 - 78)


def test_a_hidden_caster_makes_the_spray_at_once_on_its_cell_and_no_lightning():
    w = world()
    hidden = types.SimpleNamespace(id=0, type_id=0, x=21, y=22)
    t = foe(w, 2, 24, 20)
    w.tick = 70
    effects.spawn_bolt(w, hidden, 28, (t.id,))
    assert w.bolts == []                                        # the 0x86 handler finds no caster view
    effects.spawn_bolt(w, hidden, 30, (t.id,))
    (b,) = w.bolts
    assert (b.born, b.age0, b.origin, b.life) == (70, -1, (21 * 256 + 128, 22 * 256 + 128), 13)
    assert [lights.bolt_age(b, 70 + k) for k in (0, 1, 12)] == [0, 1, 12] and lights.bolt_age(b, 83) is None
    assert [lights.bolt_phase(a) for a in (0, 1, 2, 12)] == [0, 4, 3, 3]


def test_pick_row_follows_the_relief():
    w = world()
    assert lights.pick_row(w, 5 * 32 + 3, 10 * 32 + 5) == 10     # flat ground: the pixel row is the cell row
    w.heights[10, 5] = w.heights[10, 6] = 32                     # the row-10 vertices are drawn 32 px higher: the pixel row 9.x now shows row 10
    assert lights.pick_row(w, 5 * 32 + 3, 9 * 32 + 5) == 10


def test_bolt_sprites_are_drawn_and_the_carriers_of_10_and_11_have_no_missile():
    a = Assets({})
    a.unit_set = lambda tid: None
    a.p[30] = projectile(30, Width=16, Height=16, Phases=5, RotationPhases=1, sprites={"main": sprite_file(35)})
    a.p[28] = projectile(28, Width=16, Height=16, Phases=5, RotationPhases=1, sprites={"main": sprite_file(5)})
    w = world()
    c = caster(w, level=40)
    ts = [foe(w, 2 + i, 24, 18 + 2 * i) for i in range(2)]
    cast, st = start(w, c, ts[0])
    spells.cast_release(w, c, cast, st)
    pics = [i for i in build_draw_list(w, cam(22, 20), w.tick, a, PLAIN) if i.kind == "sprite" and i.sprite[0] == "projectile"]
    assert pics and {i.sprite[1] for i in pics} == {30}                          # no flying missile of the carriers (id 30 is the bolt)
    assert {i.frame % 5 for i in pics} == {4} and {i.frame // 5 for i in pics} == {0, 1}
