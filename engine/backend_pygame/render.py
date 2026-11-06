"""Draw a draw list onto a surface; screenshots."""

import os
from dataclasses import dataclass

import numpy as np
import pygame

from allods2.graphics import write_png

from allods2.graphics import lighting as lt
from allods2.graphics.palette import pack16, unpack16
from engine.view import build_draw_list, build_terrain_items
from engine.view import fog as fog_view

from .sprites import Frame, blend_half, blend_shadow, frame_alpha, frame_half, frame_shadow  # noqa: F401 (the surface variants are the tests' API)
from .scene import SceneMemo, full_scene
from .text import draw_text, render_text

PASSABILITY_TINT = (255, 40, 40, 90)
MARKER_COLOR = (255, 255, 0)
HOTSPOT_COLOR = (0, 255, 255)
DEPTH_COLOR = (255, 255, 255)


@dataclass
class Caches:
    terrain: object             # SurfaceCache
    sprites: object = None      # SpriteCache (None = terrain only)
    ball: object = None         # Ball.bmp 4x4 bar cap (surface) or None
    scene: object = None        # SceneMemo (scene.py): the last composite, made on first use; False = always redraw in full


# FUN_00460db1 (ui-layout.md section 9): empty track rows, then fill rows (dark, bright, mid, dark)
BAR_EMPTY = ((0x40,) * 3, (0x80,) * 3, (0x60,) * 3, (0x40,) * 3)
BAR_TIERS = (((0, 128, 0), (0, 255, 0), (0, 192, 0)),         # hp >= max/2: dark, bright, mid
             ((128, 128, 0), (255, 255, 0), (192, 192, 0)),   # hp < max/2
             ((128, 0, 0), (255, 0, 0), (192, 0, 0)),         # hp < max/4
             ((0, 0, 128), (0, 0, 255), (0, 0, 192)))         # tier 3: the mana bar


def draw_bar(surface, it, ball=None):
    """HP bar of a "bar" item: item (sx, sy) = (x1, y-2), width x2-x1, `bar` = (fill, track, tier);
    track x1+4 .. x2-4, 4 rows; Ball.bmp caps at x1 and x2-4."""
    fill, track, tier = it.bar
    dark, bright, mid = BAR_TIERS[tier]
    full = (dark, bright, mid, dark)
    x = it.sx + 4
    for row in range(4):
        y = it.sy + row
        pygame.draw.line(surface, BAR_EMPTY[row], (x, y), (x + track - 1, y))
        if fill > 0:
            pygame.draw.line(surface, full[row], (x, y), (x + fill - 1, y))
    if ball is not None:
        surface.blit(ball, (it.sx, it.sy))
        surface.blit(ball, (it.sx + it.w - 4, it.sy))


PATH_TINTS = {"searched": (80, 120, 255, 60), "path": (255, 220, 0, 110), "hop": (0, 255, 90, 150),
              "ai_sight": (255, 60, 60, 45), "ai_radius": (255, 160, 0, 130), "ai_post": (0, 200, 255, 170), "ai_target": (255, 0, 0, 170)}


def _overlay(surface, caches, it):
    r = pygame.Rect(it.sx, it.sy, it.w, it.h)
    if it.kind == "passability":
        tint = pygame.Surface((it.w, it.h), pygame.SRCALPHA)
        tint.fill(PASSABILITY_TINT)
        surface.blit(tint, r.topleft)
    elif it.kind in PATH_TINTS:
        tint = pygame.Surface((it.w, it.h), pygame.SRCALPHA)
        tint.fill(PATH_TINTS[it.kind])
        surface.blit(tint, r.topleft)
    elif it.kind == "marker" and it.text == "hotspot":
        x, y = it.sx, it.sy
        pygame.draw.line(surface, HOTSPOT_COLOR, (x - 4, y), (x + 4, y))
        pygame.draw.line(surface, HOTSPOT_COLOR, (x, y - 4), (x, y + 4))
    elif it.kind == "marker":
        pygame.draw.rect(surface, MARKER_COLOR, r, 1)
    elif it.kind == "ai_text":
        surface.blit(render_text(it.text, DEPTH_COLOR, font=3, shadow=False, background=(0, 0, 0)), r.topleft)
    elif it.kind == "depth":
        surface.blit(render_text(it.text, DEPTH_COLOR, font=3, shadow=False, background=(0, 0, 0)), r.topleft)


def draw_frame(surface, caches, terrain_items, items, camera, world=None):
    """Black background, the terrain items in list order, then the draw list's items in list order: sprites blit,
    smoothing and shadows blend per pixel (numpy); with `world` whose `fog` is set, the fog pass darkens the result last (vision.md).  Everything is drawn into a `Frame` (a lock-free numpy-writable
    surface) that is copied to `surface` at the end."""
    frame = Frame.get(*surface.get_size())
    target = surface
    surface = frame.surf
    if caches.scene is None:
        caches.scene = SceneMemo()
    memo = caches.scene
    if memo is False:                                # the reference path: everything drawn, every frame
        full_scene(frame, caches, terrain_items, items, camera.iy)
        clean = False
    else:
        clean = memo.compose(frame, caches, terrain_items, items, camera)
    fog = None
    if world is not None and world.fog is not None:
        fog = fog_view.overlay(world, camera, caches.terrain.tv.proj.vy)
    fkey = fog_key(frame, fog) if fog is not None else None
    if clean and memo.final is not None and memo.final_key == fkey:     # the very same frame again: its fogged output is still in hand
        target.blit(memo.final.surf, (0, 0))
        return
    if clean:
        memo.restore(frame)
    if fog is not None:
        draw_fog_pass(frame, fog, fkey, camera.iy & 31)
    if memo is not False:
        memo.keep_final(frame, fkey, camera)
    target.blit(surface, (0, 0))


def fog_key(frame, ov):
    levels, vy, cols, rows = ov
    return (np.asarray(levels).tobytes(), np.asarray(vy).tobytes(), cols, rows, frame.arr.shape)


def draw_fog_pass(frame, ov, key=None, phase=None):
    """The exe's fog pass (`0x40a06a`-`0x40a5bc`, lighting.md 3) on the 16-bit (565) image of the frame.

    With `phase` (the camera's vertical pixel offset inside its cell, `iy & 31`) the plan is built once per fog state and shared by every
    vertical offset: the quads' screen y are `world y - iy`, the same for all offsets of one origin cell up to a shift by `phase`, and a
    pixel's blend rows depend only on the quads that cover it and their order, so the plan is made for the canonical frame (`vy + phase`,
    32 rows taller: real row r is canonical row r + phase) and the frame is applied inside a padded copy.  Pixel-identical to the plan of
    the real offset (`tests/test_engine_scene.py`)."""
    levels, vy, cols, rows = ov
    if not (levels != lt.FOG_SEEN).any():
        return
    shape = frame.arr.shape
    if phase is None:
        key = key or fog_key(frame, ov)
        if _fog_cache[0] != key:
            _fog_cache[:] = [key, lt.fog_plan(levels, vy, cols, rows, shape)]
        lt.apply_fog_plan_rgb(frame.flat, _fog_cache[1], shape)
        return
    H, W = shape
    pshape = (H + 32, W)
    pkey = ("pad", np.asarray(levels).tobytes(), (np.asarray(vy) + phase).tobytes(), cols, rows, shape)
    if _fog_cache[0] != pkey:                       # the pass only changes with the fog bits or the camera cell
        _fog_cache[:] = [pkey, lt.fog_plan(levels, np.asarray(vy) + phase, cols, rows, pshape)]
    pad = _fog_pad.get(pshape)
    if pad is None:
        _fog_pad.clear()
        pad = _fog_pad[pshape] = np.zeros(pshape, np.uint32)
    inner = pad[phase:phase + H]
    np.copyto(inner, frame.arr)
    lt.apply_fog_plan_rgb(pad.reshape(-1), _fog_cache[1], pshape)
    np.copyto(frame.arr, inner)


_fog_cache = [None, None]
_fog_pad = {}


def surface_rgb(surface):
    """(h, w, 3) uint8 copy of a surface."""
    return np.ascontiguousarray(pygame.surfarray.array3d(surface).transpose(1, 0, 2))


def screenshot(terrain_view, camera, tick, dest, cache=None, assets=None, options=None,
               debug=None, sprite_cache=None):
    """Render one frame off-screen (works with SDL_VIDEODRIVER=dummy), save a PNG,
    return the (h, w, 3) pixels.  With `assets` (an `AssetCache`) the world's objects
    and structures are drawn too (`options`: DrawOptions, `debug`: DebugFlags)."""
    from .window import ensure_display
    ensure_display(camera.view_w, camera.view_h)
    from .sprites import SpriteCache
    from .surfaces import SurfaceCache
    cache = cache or SurfaceCache(terrain_view)
    items = []
    if assets is not None:
        sprite_cache = sprite_cache or SpriteCache(assets)
        items = build_draw_list(terrain_view.world, camera, tick, assets, options, debug)
    surf = pygame.Surface((camera.view_w, camera.view_h))
    draw_frame(surf, Caches(cache, sprite_cache), build_terrain_items(terrain_view, camera, tick, getattr(items, "lights", None)),
               items, camera, terrain_view.world)
    rgb = surface_rgb(surf)
    if dest:
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        write_png(dest, rgb)
    return rgb


_player_ramps = {}


def player_ramp(colour, fs):
    """The 16-entry text ramp of player colour row `colour` (`FUN_0047e345`: `0x61fac8 + 32 * colour`), hashable for the text cache."""
    if colour not in _player_ramps:
        from allods2.graphics import load_human_palettes, player_text_ramp
        from allods2.units import HUMAN_PAL
        rows = load_human_palettes(HUMAN_PAL, fs)
        table = player_text_ramp(rows[colour % len(rows)])
        _player_ramps[colour] = tuple(tuple(int(c) for c in row) for row in table)
    return _player_ramps[colour]


def draw_numbers(surface, entries):
    """Floating damage numbers: `entries` = [(text, colour, x, y)], x / y relative to the surface (the view).  Font 2 with the
    1 px shadow, as `FUN_0045d536` is called with the small font."""
    for text, colour, x, y in entries:
        draw_text(surface, text, x, y, colour)
