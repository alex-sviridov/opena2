"""The spell flights and their smoke trails in the draw list: client `Arrow`s made by the cast action (`FUN_0046707e`, K9 follow-up; before that the
server carriers were drawn).  Synthetic assets, always run.  Spec: docs/formats/animation.md 4.4, docs/engine/rendering.md "Arrows and shots"."""

import pytest

from allods2.anim.projectiles import direction16
from engine.view import DrawOptions, build_draw_list, lights
from engine.world import Arrow, Carrier

from helpers import projectile, sprite_file
from test_engine_unit_draw import UnitAssets, uassets, unit, world_with
from test_engine_objects import cam

C = 256


class MissileAssets(UnitAssets):
    def __init__(self, base, pset):
        super().__init__(base.units, objects=base.objects, structures=base.structures)
        self.pset = pset

    def projectile_set(self, pid):
        return self.pset if pid == self.pset.pid else None


def assets(**rec):
    pset = projectile(10, sprites={"main": sprite_file(64), "trail": sprite_file(6)}, **rec)
    return MissileAssets(uassets(), pset)


def draw(w, tick=0, a=None):
    return build_draw_list(w, cam(), tick, a or assets(), DrawOptions(shadows=False))


def projectile_items(items):
    return [i for i in items if i.kind == "sprite" and i.sprite[0] == "projectile"]


def flight(**kw):
    """A live Fire Arrow flight at cell (10, 10) heading east, age 2, with a 3-point trail."""
    a = dict(x=10 * C + 128, y=10 * C + 128, tx=17 * C + 128, ty=10 * C + 128, steps=6, age=2, facing=4, spell=True,
             trail=[(10 * C + 128 + 40 * k, 10 * C + 128) for k in range(3)])
    a.update(kw)
    return Arrow(10, 1, 2, 0, live=True, **a)


def test_facing_16_directions():
    assert direction16(0, -5) == 0 and direction16(5, 0) == 4 and direction16(0, 5) == 8 and direction16(-5, 0) == 12
    assert direction16(5, -5) == 2


def test_a_flight_draws_the_body_then_its_trail_oldest_first():
    w = world_with(unit(1, 10, 10), unit(2, 17, 10, owner=2))
    w.arrows.append(flight())
    items = projectile_items(draw(w))
    assert [i.sprite[2] for i in sorted(items, key=lambda i: i.depth)] == ["main", "trail", "trail", "trail"]     # the trail follows the body
    main = [i for i in items if i.sprite[2] == "main"][0]
    assert main.blend == "alpha" and main.light_row is None and main.sprite[:2] == ("projectile", 10)
    assert main.frame == (2 // 2) % 4 + 4 * ((4 - 8) & 15)             # east: direction 4 -> row 12; phase (age / 2) mod Phases
    trail = sorted((i for i in items if i.sprite[2] == "trail"), key=lambda i: i.depth)
    assert [i.frame for i in trail] == [0, 1, 2]                        # frame i at point i, oldest first


def test_the_trail_holds_up_to_six_points():
    w = world_with(unit(1, 10, 10))
    w.arrows.append(flight(trail=[(10 * C + 40 * k, 10 * C) for k in range(6)]))
    assert len([i for i in projectile_items(draw(w)) if i.sprite[2] == "trail"]) == 6
    w.arrows[:] = [flight(trail=[])]
    assert len([i for i in projectile_items(draw(w)) if i.sprite[2] == "trail"]) == 0


@pytest.mark.parametrize("age", [1, 2, 3, 4])
def test_the_first_drawn_age_is_one_for_unit_fired_flights(age):
    w = world_with(unit(1, 10, 10))
    w.arrows[:] = [flight(age=age, trail=[])]
    main = projectile_items(draw(w))[0]
    assert main.frame == (age // 2) % 4 + 4 * ((4 - 8) & 15)


def test_the_flight_is_drawn_after_the_units_of_its_cell():
    u = unit(1, 10, 10)
    w = world_with(u)
    w.arrows.append(flight(x=10 * C + 128, y=10 * C + 128, trail=[]))
    items = [i for i in draw(w) if i.kind == "sprite" and i.blend != "half"]
    order = [i.entity for i in items]
    assert order.index(u.id) < order.index(projectile_items(items)[-1].entity)


def test_outside_the_window_is_culled_and_a_missing_set_is_counted():
    w = world_with(unit(1, 10, 10))
    w.arrows.append(flight(x=100 * C, y=100 * C, trail=[]))
    out = draw(w)
    assert not projectile_items(out) and out.culled >= 1
    w2 = world_with(unit(1, 10, 10))
    w2.arrows.append(Arrow(26, 1, 2, 0, live=True, x=10 * C, y=10 * C, tx=12 * C, ty=10 * C, steps=3, age=1, spell=True))   # projectile 26: absent from the fake assets
    out = draw(w2)
    assert not projectile_items(out) and out.missing >= 1


def test_server_carriers_draw_nothing_the_client_flight_is_the_picture():
    w = world_with(unit(1, 10, 10))
    w.carriers.append(Carrier(1, "missile", 0, None, 1, 1, 8, 0, True, (10 * C + 128, 10 * C + 128), 8, (17 * C + 128, 10 * C + 128)))
    assert not projectile_items(draw(w, tick=3))


def test_the_client_flight_has_no_height_and_the_light_follows_it():
    w = world_with(unit(1, 10, 10), unit(2, 17, 10, owner=2))
    w.arrows.append(flight(x=12 * C, y=11 * C, trail=[]))
    out = lights.light_map(w, assets(), 0)
    assert out and any(v == (12, 11) or (v[0] in (12, 13) and v[1] in (11, 12)) for v in out)


# --- the real firebolt on a real map (needs the install) ---------------------------------------------------------------

from helpers import GFS, needs_graphics


@needs_graphics
def test_a_flight_changes_the_frame_and_stays_inside_the_view(tmp_path):
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
    w.arrows.append(Arrow(10, u.id, u.id, 0, live=True, x=sx + 2 * 256, y=sy, tx=sx + 4 * 256, ty=sy, steps=3, age=3, facing=4, spell=True,
                          trail=[(sx + k * 100, sy) for k in range(5)]))
    shot = render.screenshot(tv, cam_, 4, str(tmp_path / "missile.png"), tc, a, DrawOptions(), None, sc)
    diff = np.argwhere((base != shot).any(axis=2))
    assert len(diff) > 20                                               # the firebolt and its smoke were blended in
    assert diff[:, 0].min() >= 0 and diff[:, 1].max() < 640


# --- cost -------------------------------------------------------------------------------------------------------------------------------

def test_fifteen_flights_cost_next_to_nothing_in_the_draw_list():
    import time
    w = world_with(*[unit(i, 8 + i % 8, 8 + i // 8) for i in range(1, 16)])
    a = assets()

    def mean_ms(fn, n=30):
        t0 = time.perf_counter()
        for _ in range(n):
            fn()
        return (time.perf_counter() - t0) * 1000 / n

    base = mean_ms(lambda: draw(w, 4, a))
    for k in range(15):
        w.arrows.append(flight(x=(8 + k % 8) * C, y=8 * C, tx=12 * C, ty=(12 + k % 3) * C, trail=[((8 + k % 8) * C + 30 * j, 8 * C) for j in range(4)]))
    loaded = mean_ms(lambda: draw(w, 4, a))
    assert len(projectile_items(draw(w, 4, a))) == 15 * 5               # a missile and 4 trail points each
    assert loaded - base < 15.0, (base, loaded)                         # generous: 75 sprite items; the budget at 60 fps is 16.7 ms for everything
