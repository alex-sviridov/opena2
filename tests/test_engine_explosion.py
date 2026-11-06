"""Fire explosion (projectile 13, `FUN_0046c1d0` case 0xd / `FUN_0046d0ef` / `FUN_005045a5`): spawn from the Fire Ball area carrier, the age-4
burning-list queue, the age-8 burnt ground, phase lights, draw.  Synthetic worlds, always run.  Docs: lighting.md 3, animation.md 4.4."""

from allods2.anim import ObjectSet

from engine.sim import effects, spells
from engine.view import build_draw_list, lights
from helpers import projectile, sprite_file
from test_engine_burning_sprites import Assets
from test_engine_effects import monster, sp, world
from test_engine_objects import PLAIN, cam, obj, orec


def fireball(w):
    m = monster(w, 1, 10, 20)
    t = monster(w, 2, 20, 20)
    effects.release(w, m, sp(w, 2), 40, t=t)
    return t


def run_ticks(w, n):
    for _ in range(n):
        spells.carrier_system(w, [])
        effects.explosion_system(w, [])
        w.tick += 1


def test_fire_ball_spawns_one_explosion_at_the_cell_when_the_area_carrier_runs():
    w = world()
    fireball(w)
    assert w.explosions == []                                     # the missile is still in flight
    seen = []
    for _ in range(60):
        run_ticks(w, 1)
        seen += [(e.x, e.y, e.life) for e in w.explosions]
    assert set(seen) == {(20, 20, 22)}


def test_age_4_queues_object_and_water_cells_and_age_8_burns_all_but_bare_water():
    w = world()
    w.add_object(obj(1, 19, 20))                                  # a map object (DeadObject is checked at draw time)
    w.cells[20, 21] |= 8 << 6                                     # water, no object
    w.add_object(obj(2, 21, 21))
    w.cells[21, 21] |= 8 << 6                                     # water with an object
    effects.spawn_explosion(w, (20, 20))
    w.tick = 3
    effects.explosion_system(w, [])
    assert w.burn_fx == {}
    w.tick = 4
    effects.explosion_system(w, [])
    assert {c: v[1] for c, v in w.burn_fx.items()} == {(19, 20): False, (21, 20): True, (21, 21): True}
    assert not w.cells[20, 19] & 0x2000
    w.tick = 8
    effects.explosion_system(w, [])
    assert w.cells[20, 19] & 0x2000 and w.cells[19, 20] & 0x2000     # plain ground and the object cell burn
    assert w.cells[20, 21] & 0x2000 == 0                             # bare water stays
    assert w.cells[21, 21] & 0x2000                                  # water holding an object burns
    assert w.burn_start == {}                                        # the explosion never touches the Wall of Fire list
    w.tick = 23
    effects.explosion_system(w, [])
    assert w.explosions == []


def test_a_burnt_cell_is_not_queued_again():
    w = world()
    w.add_object(obj(1, 19, 20))
    w.scorch(19, 20, burn=False)
    effects.spawn_explosion(w, (20, 20))
    w.tick = 4
    effects.explosion_system(w, [])
    assert w.burn_fx == {}


def test_phase_lights_follow_the_table_and_end_at_age_22():
    w = world()
    effects.spawn_explosion(w, (20, 20))
    a = None
    m0 = lights.light_map(w, a, 0)
    assert set(m0.values()) == {16} and len(m0) == 5                 # phase 0: radius 1 (a plus), value 16
    m2 = lights.light_map(w, a, 2)                                   # phase 1: radius 2 value 8
    assert m2[(20, 20)] == 8 and (22, 20) in m2 and (22, 22) not in m2
    m4 = lights.light_map(w, a, 4)                                   # phase 2: radius 3 value 0
    assert m4[(20, 20)] == 0 and (23, 20) in m4
    assert lights.light_map(w, a, 16)[(20, 20)] == 40                # phase 8
    assert lights.light_map(w, a, 21)[(20, 20)] == 46                # phase 10
    assert lights.light_map(w, a, 22) == {} and lights.light_map(w, a, -1) == {}


def test_explosion_sprite_and_steam_are_drawn():
    dead = orec(ID=7, Index=0)
    s = ObjectSet(orec(Index=2, DeadObject=7), dead,
                  sprites={"main": sprite_file(4), "main_b": sprite_file(4), "dead": sprite_file(2), "dead_b": sprite_file(2)})
    a = Assets({5: s})
    a.p[13] = projectile(13, Width=64, Height=64, Phases=11, RotationPhases=1, sprites={"main": sprite_file(11)})
    w = world()
    w.cells[20, 21] |= 8 << 6
    effects.spawn_explosion(w, (20, 20))
    w.tick = 4
    effects.explosion_system(w, [])
    w.tick = 6                                                       # age 6: frame 3; steam counter 2: frame 1

    def pics(tick):
        return sorted((i.sprite[1], i.frame) for i in build_draw_list(w, cam(20, 20), tick, a, PLAIN)
                      if i.kind == "sprite" and i.sprite[0] == "projectile")
    assert pics(6) == [(8, 1), (13, 3)]                              # bare water: steam only, the fire needs a map object (`0x408981` gate)
    assert [p for p in pics(22) if p[0] == 13] == [] and pics(26) == []         # the explosion ends at age 22, the list entry at 4 + 22
