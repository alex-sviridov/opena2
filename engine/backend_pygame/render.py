"""Draw a draw list onto a surface; screenshots."""

import os
from dataclasses import dataclass

import numpy as np
import pygame

from allods2.graphics import write_png

from engine.view import build_draw_list, build_terrain_items

from .sprites import blend_half, blend_shadow

PASSABILITY_TINT = (255, 40, 40, 90)
MARKER_COLOR = (255, 255, 0)
HOTSPOT_COLOR = (0, 255, 255)
DEPTH_COLOR = (255, 255, 255)


@dataclass
class Caches:
    terrain: object             # SurfaceCache
    sprites: object = None      # SpriteCache (None = terrain only)
    font: object = None

    def get_font(self):
        if self.font is None:
            if not pygame.font.get_init():
                pygame.font.init()
            self.font = pygame.font.Font(None, 14)
        return self.font


def _overlay(surface, caches, it):
    r = pygame.Rect(it.sx, it.sy, it.w, it.h)
    if it.kind == "passability":
        tint = pygame.Surface((it.w, it.h), pygame.SRCALPHA)
        tint.fill(PASSABILITY_TINT)
        surface.blit(tint, r.topleft)
    elif it.kind == "marker" and it.text == "hotspot":
        x, y = it.sx, it.sy
        pygame.draw.line(surface, HOTSPOT_COLOR, (x - 4, y), (x + 4, y))
        pygame.draw.line(surface, HOTSPOT_COLOR, (x, y - 4), (x, y + 4))
    elif it.kind == "marker":
        pygame.draw.rect(surface, MARKER_COLOR, r, 1)
    elif it.kind == "depth":
        surface.blit(caches.get_font().render(it.text, False, DEPTH_COLOR, (0, 0, 0)), r.topleft)


def draw_frame(surface, caches, terrain_items, items, camera):
    """Black background, the terrain items in list order, then the draw list's items
    in list order: sprites blit, smoothing and shadows blend per pixel (numpy)."""
    surface.fill((0, 0, 0))
    cy = camera.iy
    blit = surface.blit
    terrain = caches.terrain
    for item in terrain_items:
        val = terrain.get(item)
        if val is not None:
            blit(val[0], (item.sx, val[1] - cy))
    sprites = caches.sprites
    for it in items:
        kind = it.kind
        if kind == "sprite" or kind == "shadow":
            val = sprites.get(it)
            if val is None:
                continue
            if kind == "shadow":
                blend_shadow(surface, it.sx, it.sy, val, it.shadow_level)
            elif it.blend == "half":
                blend_half(surface, it.sx, it.sy, val)
            else:
                blit(val, (it.sx, it.sy))
        else:
            _overlay(surface, caches, it)


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
    draw_frame(surf, Caches(cache, sprite_cache), build_terrain_items(terrain_view, camera, tick),
               items, camera)
    rgb = surface_rgb(surf)
    if dest:
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        write_png(dest, rgb)
    return rgb
