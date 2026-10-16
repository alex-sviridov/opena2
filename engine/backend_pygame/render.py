"""Draw a draw list onto a surface; screenshots."""

import os

import numpy as np
import pygame

from allods2.graphics import write_png

from engine.view import build_draw_list


def draw_frame(surface, cache, items, camera):
    """Black background, then every terrain item blitted in list order."""
    surface.fill((0, 0, 0))
    cy = camera.iy
    blit = surface.blit
    for item in items:
        val = cache.get(item)
        if val is not None:
            blit(val[0], (item.sx, val[1] - cy))


def surface_rgb(surface):
    """(h, w, 3) uint8 copy of a surface."""
    return np.ascontiguousarray(pygame.surfarray.array3d(surface).transpose(1, 0, 2))


def screenshot(terrain_view, camera, tick, dest, cache=None):
    """Render one frame off-screen (works with SDL_VIDEODRIVER=dummy), save a PNG,
    return the (h, w, 3) pixels."""
    from .window import ensure_display
    ensure_display(camera.view_w, camera.view_h)
    from .surfaces import SurfaceCache
    cache = cache or SurfaceCache(terrain_view)
    surf = pygame.Surface((camera.view_w, camera.view_h))
    draw_frame(surf, cache, build_draw_list(terrain_view, camera, tick), camera)
    rgb = surface_rgb(surf)
    if dest:
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        write_png(dest, rgb)
    return rgb
