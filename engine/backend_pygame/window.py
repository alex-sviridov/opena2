"""Window and the main loop."""

import pygame

from engine.sim import DEFAULT_SPEED, CommandQueue, Simulation, tick_period_ms
from engine.ui import ScrollInput
from engine.view import build_draw_list

from .render import draw_frame
from .surfaces import SurfaceCache

MAX_FRAME_MS = 250
KEYS = {pygame.K_LEFT: "left", pygame.K_RIGHT: "right", pygame.K_UP: "up", pygame.K_DOWN: "down"}


def ensure_display(w, h):
    """pygame display of size (w, h); created once (needed for convert_alpha)."""
    if not pygame.get_init():
        pygame.init()
    s = pygame.display.get_surface()
    if s is None or s.get_size() != (w, h):
        s = pygame.display.set_mode((w, h))
    return s


def run(world, terrain_view, camera, speed=DEFAULT_SPEED, title="Allods 2", max_frames=None):
    """Accumulator main loop: fixed-step sim, variable-rate drawing.  Returns when
    the window closes (or after `max_frames`, for tests)."""
    screen = ensure_display(camera.view_w, camera.view_h)
    pygame.display.set_caption(title)
    sim, queue, scroll = Simulation(world), CommandQueue(), ScrollInput()
    cache = SurfaceCache(terrain_view)
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
            elif ev.type in (pygame.KEYDOWN, pygame.KEYUP) and ev.key in KEYS:
                (held.add if ev.type == pygame.KEYDOWN else held.discard)(KEYS[ev.key])
        mouse = pygame.mouse.get_pos() if pygame.mouse.get_focused() else None
        scroll.update(camera, dt, held, mouse)
        while acc >= period:
            sim.step(queue.drain())
            acc -= period
        draw_frame(screen, cache, build_draw_list(terrain_view, camera, world.tick), camera)
        pygame.display.flip()
        frames += 1
        if max_frames is not None and frames >= max_frames:
            break
    pygame.quit()
