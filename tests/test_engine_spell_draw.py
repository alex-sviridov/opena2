"""Missiles and their smoke trails in the draw list (I4b).  Synthetic assets, always run.
Spec: docs/formats/animation.md 4.4, docs/engine/rendering.md section 2 (pass 6)."""

import pytest

from engine.view import DrawOptions, build_draw_list
from engine.view import drawlist as dl
from engine.world import Carrier

from helpers import projectile, sprite_file
from test_engine_unit_draw import UnitAssets, uassets, unit, world_with
from test_engine_objects import cam

C = 256
POS = lambda x, y: (x * C + 128, y * C + 128)       # a cell centre in 1/256 cell


class MissileAssets(UnitAssets):
    def __init__(self, base, pset):
        super().__init__(base.units, objects=base.objects, structures=base.structures)
        self.pset = pset

    def projectile_set(self, pid):
        return self.pset if pid == self.pset.pid else None


def assets(**rec):
    pset = projectile(10, sprites={"main": sprite_file(64), "trail": sprite_file(6)}, **rec)
    return MissileAssets(uassets(), pset)


def missile(uid=1, start=(10, 10), aim=(17, 10), born=0, flight=8, target=None):       # target None: the cell form (a unit-target flight is a client Arrow)
    return Carrier(uid, "missile", 0, target, 1, 1, flight, born, True, POS(*start), flight, POS(*aim))


def draw(w, tick, a=None):
    return build_draw_list(w, cam(), tick, a or assets(), DrawOptions(shadows=False))


def projectile_items(items):
    return [i for i in items if i.kind == "sprite" and i.sprite[0] == "projectile"]


def test_position_is_a_straight_line_to_the_target_and_clamps_at_the_end():
    c = missile()
    assert dl.missile_position(c, None, 0) == POS(10, 10)
    assert dl.missile_position(c, None, 4) == (14 * C, 10 * C + 128)                     # halfway between 10.5 and 17.5 cells
    assert dl.missile_position(c, None, 8) == POS(17, 10)
    assert dl.missile_position(c, None, 99) == POS(17, 10)             # past the flight: the target
    assert dl.missile_position(c, POS(17, 14), 8) == POS(17, 14)        # the target moved: the missile steers at its current position


def test_flight_zero_is_at_the_target_at_once():
    c = missile(flight=0)
    assert dl.missile_position(c, None, 0) == POS(17, 10)


def test_facing_16_directions():
    assert dl.missile_facing(0, -5) == 0 and dl.missile_facing(5, 0) == 4 and dl.missile_facing(0, 5) == 8 and dl.missile_facing(-5, 0) == 12
    assert dl.missile_facing(5, -5) == 2


def test_age_three_draws_three_trail_points_and_the_missile():
    w = world_with(unit(1, 10, 10))
    w.carriers.append(missile())
    items = projectile_items(draw(w, tick=3))
    assert [i.sprite[2] for i in sorted(items, key=lambda i: i.depth)] == ["main", "trail", "trail", "trail"]     # the trail follows the body
    main = [i for i in items if i.sprite[2] == "main"][0]
    assert main.blend == "alpha" and main.light_row is None and main.sprite[:2] == ("projectile", 10)
    assert main.frame == (3 // 2) % 4 + 4 * ((4 - 8) & 15)             # east: direction 4 -> row 12; phase (age / 2) mod Phases
    trail = sorted((i for i in items if i.sprite[2] == "trail"), key=lambda i: i.depth)
    assert [i.frame for i in trail] == [0, 1, 2]                        # frame i at point i, oldest first


def test_the_trail_keeps_the_last_six_points():
    w = world_with(unit(1, 10, 10))
    w.carriers.append(missile())
    assert len([i for i in projectile_items(draw(w, tick=7)) if i.sprite[2] == "trail"]) == 6
    assert len([i for i in projectile_items(draw(w, tick=0)) if i.sprite[2] == "trail"]) == 0


def test_the_missile_is_drawn_after_units_of_its_cell():
    u = unit(1, 10, 10)
    w = world_with(u)
    w.carriers.append(missile(start=(10, 10), aim=(10, 10)))
    items = [i for i in draw(w, tick=2) if i.kind == "sprite" and i.blend != "half"]
    order = [i.entity for i in items]
    assert order.index(u.id) < order.index(projectile_items(items)[-1].entity)


def test_outside_the_window_is_culled_and_a_vanished_target_keeps_its_line():
    w = world_with(unit(1, 10, 10))
    w.carriers.append(missile(start=(100, 100), aim=(101, 100)))
    out = draw(w, tick=2)
    assert not projectile_items(out) and out.culled >= 1
    w2 = world_with(unit(1, 10, 10))
    w2.carriers.append(missile())                                       # the aim position of the release
    assert projectile_items(draw(w2, tick=4))


def test_point_carriers_and_unknown_projectile_ids_draw_nothing():
    w = world_with(unit(1, 10, 10))
    c = missile()
    c.kind = "point"
    w.carriers.append(c)
    assert not projectile_items(draw(w, tick=2))
    w.carriers[:] = [missile()]
    w.carriers[0].spell = 9                                              # projectile 26: absent from the fake assets
    out = draw(w, tick=2)
    assert not projectile_items(out) and out.missing >= 1


# --- the real firebolt on a real map (needs the install) ---------------------------------------------------------------

from helpers import GFS, needs_graphics


@needs_graphics
def test_a_missile_in_flight_changes_the_frame_and_stays_inside_the_view(tmp_path):
    import numpy as np
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.backend_pygame import render
    from engine.backend_pygame.sprites import SpriteCache
    from engine.backend_pygame.surfaces import SurfaceCache
    from engine.view import Camera, TerrainView
    from engine.world import World

    a = AssetCache(GFS)
    w = World.from_map(open_map("10"), a, seed=1)
    tv = TerrainView(w, a.tileset())
    u = next(iter(w.units.values()))
    cam_ = Camera(640, 480, w.width, w.height, max(u.x * 32 - 320, 0), max(u.y * 32 - 240, 0))
    tc, sc = SurfaceCache(tv), SpriteCache(a)
    base = render.screenshot(tv, cam_, 0, None, tc, a, DrawOptions(), None, sc)
    sx, sy = (u.x << 8) | u.sub_x, (u.y << 8) | u.sub_y
    w.carriers.append(Carrier(1, "missile", u.id, None, 1, 1, 8, 0, True, (sx, sy), 8, (sx + 4 * 256, sy)))
    shot = render.screenshot(tv, cam_, 4, str(tmp_path / "missile.png"), tc, a, DrawOptions(), None, sc)
    diff = np.argwhere((base != shot).any(axis=2))
    assert len(diff) > 20                                               # the firebolt and its smoke were blended in
    assert diff[:, 0].min() >= 0 and diff[:, 1].max() < 640


# --- cost (I4c: "a 15-unit fight with projectiles keeps a steady frame rate") -----------------------------------------------------------------

def test_fifteen_missiles_cost_next_to_nothing_in_the_draw_list_and_the_carrier_pass():
    import time
    from engine.sim import Simulation
    from engine.sim.spells import carrier_system
    w = world_with(*[unit(i, 8 + i % 8, 8 + i // 8) for i in range(1, 16)])
    a = assets()

    def mean_ms(fn, n=30):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        return (time.perf_counter() - t0) * 1000 / n

    base = mean_ms(lambda: draw(w, 4, a))
    for k in range(15):
        w.carriers.append(missile(uid=k + 1, start=(8 + k % 8, 8), aim=(12, 12 + k % 3), born=0, flight=64))
    loaded = mean_ms(lambda: draw(w, 4, a))
    assert len(projectile_items(draw(w, 4, a))) == 15 * 5               # a missile and 4 trail points each at age 4
    assert loaded - base < 15.0, (base, loaded)                         # generous: 75 sprite items; the budget at 60 fps is 16.7 ms for everything
    sim_ms = mean_ms(lambda: carrier_system(w, ()), 200)
    assert sim_ms < 1.0, sim_ms


# --- K9 follow-up: the unit-target flights are client Arrows made by the cast action (FUN_0046707e) --------------------------------------------

from engine.world import Arrow


def live_flight(**kw):
    a = dict(x=10 * C + 128, y=10 * C + 128, tx=17 * C + 128, ty=10 * C + 128, steps=6, age=2, facing=4, spell=True,
             trail=[(10 * C + 128 + 40 * k, 10 * C + 128) for k in range(3)])
    a.update(kw)
    return Arrow(10, 1, 2, 0, live=True, **a)


def test_a_unit_target_carrier_is_not_drawn_its_client_flight_is():
    w = world_with(unit(1, 10, 10), unit(2, 17, 10, owner=2))
    w.carriers.append(missile(target=2))                                 # the server carrier of a unit-target cast: no sprite of its own
    assert not projectile_items(draw(w, tick=3))
    w.arrows.append(live_flight())
    items = projectile_items(draw(w, tick=3))
    assert [i.sprite[2] for i in sorted(items, key=lambda i: i.depth)] == ["main", "trail", "trail", "trail"]


def test_the_client_flight_frame_uses_age_one_first_and_the_facing_row():
    w = world_with(unit(1, 10, 10), unit(2, 17, 10, owner=2))
    for age in (1, 2, 3, 4):
        w.arrows[:] = [live_flight(age=age, trail=[])]
        main = projectile_items(draw(w, tick=0))[0]
        assert main.frame == (age // 2) % 4 + 4 * ((4 - 8) & 15)         # unit-fired: age 0 at creation, the first drawn age is 1 (carriers started at -1)


def test_the_client_flight_has_no_height_and_the_light_follows_it():
    from engine.view import lights
    w = world_with(unit(1, 10, 10), unit(2, 17, 10, owner=2))
    w.arrows.append(live_flight(x=12 * C, y=11 * C, trail=[]))
    out = lights.light_map(w, assets(), 0)
    assert out and any(v == (12, 11) or (v[0] in (12, 13) and v[1] in (11, 12)) for v in out)
