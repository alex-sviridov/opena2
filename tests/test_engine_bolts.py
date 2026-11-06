"""Prismatic Spray chain (`FUN_00519c04` -> `FUN_00579ddf`) and the client bolts of Lightning / Prismatic Spray (projectiles 28 / 30, `FUN_0046707e`,
`FUN_0046d46a`, `FUN_0046d0ef`): target list, chain release, bolt lifetime, phases, lights, draw.  Synthetic worlds, always run.
Docs: docs/engine/effects.md 11, docs/mechanics/lighting.md 3."""

from engine.sim import ai, effects, spells
from engine.view import build_draw_list, lights
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
    assert not w.unbuilt_casts and w.bolts == []              # the bolt starts at the cast action, not at the start


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


def test_the_release_does_nothing_but_start_the_bolt():
    w = world()
    c = caster(w, level=40)
    t = foe(w, 2, 22, 20)
    cast, st = start(w, c, t)
    n = len(w.carriers)
    w.tick = 50
    spells.cast_release(w, c, cast, st)
    assert len(w.carriers) == n                                 # FUN_00519d7f skips spell 11
    (b,) = w.bolts
    assert (b.pid, b.caster, b.targets, b.born) == (30, c.id, cast.chain, 50)


def test_a_cast_from_an_item_uses_the_item_level_for_the_count():
    w = world()
    c = caster(w, level=0)
    t = foe(w, 2, 22, 20)
    [foe(w, 3 + i, 23, 18 + i) for i in range(8)]
    assert len(start(w, c, t, item_count=60)[0].chain) == 5     # 60 // 20 + 2


def test_lightning_has_no_chain_and_starts_a_bolt_at_the_release():
    w = world()
    c = caster(w)
    t = foe(w, 2, 22, 20)
    cast, st = start(w, c, t, spell=LIGHTNING)
    assert cast.chain is None and w.carriers == [] and w.bolts == []
    w.tick = 9
    spells.cast_release(w, c, cast, st)
    (b,) = w.bolts
    assert (b.pid, b.targets, b.born) == (28, (t.id,), 9) and len(w.carriers) == 1


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


def test_the_polyline_runs_from_origin_to_target():
    import random
    pts = lights.bolt_polyline((0, 0), (200, 0), random.Random(3))
    assert pts[0] == (0, 0) and abs(pts[-1][0] - 200) < 1e-6 and abs(pts[-1][1]) < 1e-6
    assert max(abs(y) for _, y in pts) <= 0.09 * 200 + 1e-6    # offset <= 3 * 0.03 * length


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
