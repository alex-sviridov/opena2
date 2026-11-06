"""The incremental scene composite (engine/backend_pygame/scene.py): every frame equals the full redraw (`Caches(scene=False)`), pixel for pixel,
whatever moved: the camera, objects (added, removed, moved: overlapping sprites, shadows, smoothing overlays), units, selection bars, fog."""

import random

import numpy as np
import pygame
import pytest

from allods2.anim import ObjectSet
from allods2.graphics.terrain import TerrainSet
from engine.backend_pygame.render import Caches, draw_frame
from engine.backend_pygame.scene import _merge
from engine.backend_pygame.sprites import SpriteCache
from engine.backend_pygame.surfaces import SurfaceCache
from engine.backend_pygame.window import ensure_display
from engine.view import Camera, DrawOptions, TerrainView, build_draw_list, build_terrain_items

from helpers import needs_data, sprite_file
from test_engine_objects import H, W, assets, flat_world, obj, struct

SIZE = 160


def render(w, tv, caches, a, x, y, tick, opts, selection=()):
    c = Camera(SIZE, SIZE, W, H, x, y)
    items = build_draw_list(w, c, tick, a, opts, selection=selection)
    surf = pygame.Surface((SIZE, SIZE))
    draw_frame(surf, caches, build_terrain_items(tv, c, tick, items.lights), items, c, w)
    return pygame.image.tobytes(surf, "RGB")


def test_merge_keeps_cover_and_drops_contained():
    rects = [(0, 0, 10, 10), (2, 2, 4, 4), (8, 0, 18, 10), (100, 100, 110, 110)]
    out = _merge(rects)
    assert (2, 2, 4, 4) not in out and (100, 100, 110, 110) in out
    for r in rects:
        assert any(o[0] <= r[0] and o[1] <= r[1] and o[2] >= r[2] and o[3] >= r[3] for o in out)


def test_incremental_equals_full_redraw_synthetic():
    ensure_display(SIZE, SIZE)
    objs = [obj(n, 2 + n % 9, 2 + n % 7) for n in range(40)] + [struct(1, 6, 6), struct(2, 9, 3)]
    w = flat_world(objs)
    tv = TerrainView(w, TerrainSet({}, np.zeros((128, 32), np.uint8), np.zeros((256, 3), np.uint8)))
    a = assets()
    inc = Caches(SurfaceCache(tv), SpriteCache(a))
    ref = Caches(SurfaceCache(tv), SpriteCache(a), scene=False)
    rng = random.Random(5)
    x = y = 0
    nid = 100
    for opts in (DrawOptions(), DrawOptions(shadows=False), DrawOptions(smoothing=False, shadows=False, lit=False)):
        for step in range(60):
            kind = rng.random()
            if kind < 0.45:                                   # the camera: still, a pixel or two, a jump
                dx, dy = rng.choice(((0, 0), (0, 0), (1, 0), (3, -2), (0, 5), (-7, 3), (40, 0), (0, 33), (150, 90)))
                x, y = max(0, x + dx), max(0, y + dy)
            elif kind < 0.7 and len(w.objects) > 5:           # an object goes
                w.remove_object(rng.choice(list(w.objects)))
            elif kind < 0.9:                                  # an object appears, over / under the others
                nid += 1
                w.add_object(obj(nid, rng.randint(0, W - 1), rng.randint(0, H - 1)))
            else:                                             # an object moves
                o = w.objects[rng.choice(list(w.objects))]
                w.move_object(o.id, min(W - 1, max(0, o.x + rng.choice((-1, 1)))), min(H - 1, max(0, o.y + rng.choice((-1, 1)))))
            tick = step // 7
            want = render(w, tv, ref, a, x, y, tick, opts)
            assert render(w, tv, inc, a, x, y, tick, opts) == want, (opts, step, x, y)
            assert render(w, tv, inc, a, x, y, tick, opts) == want             # the same frame again
    sc = inc.scene
    assert sc.incremental > 20 and sc.reused > 0 and sc.full > 0


@needs_data
def test_incremental_equals_full_redraw_on_the_install():
    """Map 32 with fog, the hero walking, the world running (units, animated objects), selection bars, several option sets and camera steps."""
    from engine.session import build_game
    from engine.sim import MoveUnits, Simulation
    w, a = build_game("32", seed=1, vision=True)
    sim = Simulation(w, ai=True, vision=True)
    hero = w.units[w.players[1].main_hero]
    ensure_display(320, 240)
    tv = TerrainView(w, a.tileset())
    fog = w.fog
    rng = random.Random(1)
    inc = Caches(SurfaceCache(tv), SpriteCache(a))
    ref = Caches(SurfaceCache(tv), SpriteCache(a), scene=False)

    def shot(caches, cam, opts, sel):
        items = build_draw_list(w, cam, w.tick, a, opts, selection=sel)
        surf = pygame.Surface((320, 240))
        draw_frame(surf, caches, build_terrain_items(tv, cam, w.tick, items.lights), items, cam, w)
        return pygame.image.tobytes(surf, "RGB")

    for opts in (DrawOptions(), DrawOptions(shadows=False, animate=False), DrawOptions(health_bars=True, smoothing=False)):
        for use_fog in (True, False):
            w.fog = fog if use_fog else None
            cam = Camera(320, 240, w.width, w.height, hero.x * 32 - 160, hero.y * 32 - 120)
            for step in range(24):
                cam.move_by(*rng.choice(((0, 0), (0, 0), (3, -2), (1, 0), (0, 5), (-7, 3), (35, 0), (0, 40))))
                if step % 3 == 0:
                    sim.step([MoveUnits(1, (hero.id,), (max(1, hero.x + rng.randint(-6, 6)), max(1, hero.y + rng.randint(-6, 6))))] if step % 6 == 0 else [])
                sel = tuple(w.units)[:4]
                want = shot(ref, cam, opts, sel)
                assert shot(inc, cam, opts, sel) == want, (opts, use_fog, step)
    assert inc.scene.incremental > 30 and inc.scene.full > 0


@needs_data
def test_item_boxes_cover_what_is_drawn():
    """The dirty-rectangle analysis trusts `_bbox`: a sprite's surface, a half overlay's mask and a shadow's mask are never larger than it."""
    from engine.backend_pygame.scene import _bbox
    from engine.session import build_game
    w, a = build_game("32", seed=1, vision=True)
    sprites = SpriteCache(a)
    hero = w.units[w.players[1].main_hero]
    cam = Camera(1024, 768, w.width, w.height, hero.x * 32 - 512, hero.y * 32 - 384)
    n = 0
    for it in build_draw_list(w, cam, 0, a, DrawOptions()):
        val = sprites.get(it)
        if val is None:
            continue
        b = _bbox(it, None)
        n += 1
        if it.kind == "shadow":
            assert (b[0], b[2] - b[0]) == (it.sx + val.dx, val.w) and b[3] - b[1] == val.h, it
        elif it.blend == "half":
            assert (b[2] - b[0], b[3] - b[1]) == (val.w, val.h), it
        elif it.blend == "alpha":
            assert (b[2] - b[0], b[3] - b[1]) == val[0].shape, it
        else:
            assert (b[2] - b[0], b[3] - b[1]) == val.get_size(), it
    assert n > 100
