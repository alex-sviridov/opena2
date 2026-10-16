"""Window and the main loop."""

import pygame

from engine.sim import DEFAULT_SPEED, CommandQueue, Simulation, tick_period_ms
from engine.ui import DebugFlags, ScrollInput
from engine.view import DrawOptions, build_draw_list, build_terrain_items

from .render import Caches, draw_frame
from .sprites import SpriteCache
from .surfaces import SurfaceCache

MAX_FRAME_MS = 250
DEBUG_KEYS = {pygame.K_F1: "passability", pygame.K_F2: "markers", pygame.K_F3: "depth"}
KEYS = {pygame.K_LEFT: "left", pygame.K_RIGHT: "right", pygame.K_UP: "up", pygame.K_DOWN: "down"}


def ensure_display(w, h):
    """pygame display of size (w, h); created once (needed for convert_alpha)."""
    if not pygame.get_init():
        pygame.init()
    s = pygame.display.get_surface()
    if s is None or s.get_size() != (w, h):
        s = pygame.display.set_mode((w, h))
    return s


def run(world, terrain_view, camera, speed=DEFAULT_SPEED, title="Allods 2", max_frames=None,
        assets=None, options=None, debug=None):
    """Accumulator main loop: fixed-step sim, variable-rate drawing.  Returns when
    the window closes (or after `max_frames`, for tests).  `assets` (an AssetCache)
    turns on objects and structures; F1/F2/F3 toggle the debug overlays."""
    options, debug = options or DrawOptions(), debug or DebugFlags()
    screen = ensure_display(camera.view_w, camera.view_h)
    pygame.display.set_caption(title)
    sim, queue, scroll = Simulation(world), CommandQueue(), ScrollInput()
    caches = Caches(SurfaceCache(terrain_view), SpriteCache(assets) if assets is not None else None)
    period = tick_period_ms(speed)
    clock = pygame.time.Clock()
    held, acc, frames = set(), 0, 0
    running = True
    while running:
        dt = clock.tick(60)
        acc += min(dt, MAX_FRAME_MS)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key in DEBUG_KEYS:
                debug.toggle(DEBUG_KEYS[ev.key])
            elif ev.type in (pygame.KEYDOWN, pygame.KEYUP) and ev.key in KEYS:
                (held.add if ev.type == pygame.KEYDOWN else held.discard)(KEYS[ev.key])
        mouse = pygame.mouse.get_pos() if pygame.mouse.get_focused() else None
        scroll.update(camera, dt, held, mouse)
        while acc >= period:
            sim.step(queue.drain())
            acc -= period
        items = build_draw_list(world, camera, world.tick, assets, options, debug) if assets is not None else ()
        draw_frame(screen, caches, build_terrain_items(terrain_view, camera, world.tick), items, camera)
        pygame.display.flip()
        frames += 1
        if max_frames is not None and frames >= max_frames:
            break
    pygame.quit()
