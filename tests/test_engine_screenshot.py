"""Engine screenshot vs render_3d, pixel for pixel.

Synthetic terrain (random strips/palette, a map with cliffs, water, dirt) always
runs; the real-map case needs the install.  Documented differences, by design:
the viewport is clamped to the flat grid (camera y in [0, 32*h - vh]), so the
margin render_3d keeps above row 0 is never shown; outside the map the engine
draws black, as render_3d's zero fill.  Inside those limits there is no difference.
"""

import functools

import numpy as np
import pytest

pygame = pytest.importorskip("pygame")

from allods2.graphics import lighting as lt
from allods2.graphics import terrain as tr
from engine.backend_pygame import render
from engine.backend_pygame.surfaces import SurfaceCache
from engine.view import Camera, TerrainView
from engine.world import World

from helpers import GFS, needs_graphics


@functools.lru_cache(maxsize=4)
def _reference(world, terrain, tick):
    day = lt.daylight(0, False)
    light = lt.terrain_light(world.heights, day.angle, day.ambient, day.diffuse)
    img, top = tr.render_3d(world.cells, world.heights, terrain, light, anim=tick, tint=day.tint)
    return img, top


def reference(world, terrain, tick):
    return _reference(world, terrain, tick)


def shot(tv, w, h, x, y, tick, cache=None):
    cam = Camera(w, h, tv.world.width, tv.world.height, x, y)
    rgb = render.screenshot(tv, cam, tick, None, cache)
    return rgb, cam


@functools.lru_cache(maxsize=1)
def synthetic():
    rng = np.random.default_rng(7)
    strips = {(s, j): rng.integers(0, 256, ((8 if 8 <= s <= 11 else 14) * 32, 32)).astype(np.uint8)
              for s in range(13) for j in range(4)}
    terrain = tr.TerrainSet(strips, rng.integers(0, 256, (128, 32)).astype(np.uint8),
                            rng.integers(0, 256, (256, 3)).astype(np.uint8))
    w, h = 30, 22
    sets = rng.integers(0, 13, (h, w))
    cells = np.array([[tr.cell_value(int(s), int(rng.integers(0, 4)), int(rng.integers(0, 8)),
                                     bool(rng.integers(0, 2))) for s in row] for row in sets], np.uint16)
    heights = rng.integers(0, 24, (h, w)).astype(np.int8)
    heights[6:9, 10:14] += 90                            # a plateau with cliffs
    heights[15, :] = 120
    return World(cells, heights), terrain


@pytest.mark.parametrize("x,y,tick", [(0, 0, 0), (100, 77, 0), (5000, 5000, 0), (0, 5000, 13), (333, 50, 8)])
def test_synthetic_screenshot_equals_render_3d(x, y, tick):
    world, terrain = synthetic()
    tv = TerrainView(world, terrain)
    ref, top = reference(world, terrain, tick)
    rgb, cam = shot(tv, 400, 300, x, y, tick)
    assert (cam.ix, cam.iy) == (min(x, cam.max_x), min(y, cam.max_y))
    crop = ref[top + cam.iy:top + cam.iy + 300, cam.ix:cam.ix + 400]
    assert rgb.shape == crop.shape
    assert np.array_equal(rgb, crop)


def test_cache_does_not_change_pixels_and_hits_on_second_frame():
    world, terrain = synthetic()
    tv = TerrainView(world, terrain)
    cache = SurfaceCache(tv)
    a, _ = shot(tv, 320, 240, 64, 40, 4, cache)
    misses = cache.misses
    b, _ = shot(tv, 320, 240, 64, 40, 4, cache)
    assert np.array_equal(a, b) and cache.misses == misses and cache.layer_hits > 0     # the second frame is one cached layer, no cell lookups
    cache.layer_hits = 0
    d, _ = shot(tv, 320, 240, 64, 41, 4, cache)         # another camera row: the layer misses, the cells hit
    assert cache.layer_misses == 2 and cache.hits > 0
    c, _ = shot(tv, 320, 240, 64, 40, 4, SurfaceCache(tv, capacity=0))
    assert np.array_equal(a, c)


def test_water_animates_with_tick():
    world, terrain = synthetic()
    tv = TerrainView(world, terrain)
    a, _ = shot(tv, 400, 300, 0, 0, 0)
    b, _ = shot(tv, 400, 300, 0, 0, 4)
    c, _ = shot(tv, 400, 300, 0, 0, 3)
    assert not np.array_equal(a, b) and np.array_equal(a, c)


def test_larger_viewport_than_map_is_black_outside():
    world, terrain = synthetic()
    tv = TerrainView(world, terrain)
    ref, top = reference(world, terrain, 0)
    rgb, cam = shot(tv, world.width * 32 + 50, world.height * 32 + 40, 0, 0, 0)
    assert np.array_equal(rgb[:world.height * 32, :world.width * 32],
                          ref[top:top + world.height * 32])
    assert not rgb[:, world.width * 32:].any() and not rgb[world.height * 32:].any()


@needs_graphics
def test_real_map_screenshots_equal_render_3d():
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    world = World.from_map(open_map("10"), AssetCache(GFS))
    terrain = AssetCache(GFS).tileset()
    tv = TerrainView(world, terrain)
    cache = SurfaceCache(tv)
    for tick, spots in ((0, ((256, 256), (0, 0), (100000, 100000), (0, 100000), (777, 301))), (20, ((256, 256),))):
        ref, top = reference(world, terrain, tick)
        for x, y in spots:
            rgb, cam = shot(tv, 1024, 768, x, y, tick, cache)
            crop = ref[top + cam.iy:top + cam.iy + 768, cam.ix:cam.ix + 1024]
            assert np.array_equal(rgb, crop), (tick, x, y)


@needs_graphics
def test_cli_screenshot_writes_png(tmp_path, monkeypatch):
    from PIL import Image
    from engine.__main__ import main
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    dest = tmp_path / "s.png"
    assert main(["screenshot", "10", "256", "256", str(dest), "--size", "320x200", "--tick", "4"]) == 0
    assert Image.open(dest).size == (320, 200)
