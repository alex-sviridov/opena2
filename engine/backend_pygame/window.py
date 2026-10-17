"""Window and the main loop: the original interface around the map, selection, cursors."""

import dataclasses

import pygame

from engine.sim import DEFAULT_SPEED, CommandQueue, Simulation, tick_period_ms
from engine.ui import CursorInput, DebugFlags, Layout, MinimapPanel, ScrollInput, SelectionInput, choose_cursor
from engine.view import DrawOptions, Projection, build_draw_list, build_terrain_items
from engine.view.pick import pick_at

from .cursor import CursorSprites, draw_cursor, hide_os_cursor
from .interface import Interface, InterfaceArt, selection_state, unit_title_fn
from .render import Caches
from .sprites import SpriteCache
from .surfaces import SurfaceCache

MAX_FRAME_MS = 250
DEBUG_KEYS = {pygame.K_F1: "passability", pygame.K_F2: "markers", pygame.K_F3: "depth"}
KEYS = {pygame.K_LEFT: "left", pygame.K_RIGHT: "right", pygame.K_UP: "up", pygame.K_DOWN: "down"}
PLAYER_ID = 1       # single player: the human is record 1 (map.md part 5)


def ensure_display(w, h):
    """pygame display of size (w, h); created once (needed for convert_alpha)."""
    if not pygame.get_init():
        pygame.init()
    s = pygame.display.get_surface()
    if s is None or s.get_size() != (w, h):
        s = pygame.display.set_mode((w, h))
    return s


def hostile_to(world, viewer):
    """`entity -> bool`: the unit's owner is at war with the viewer (relation bit 0, INFERRED)."""
    def fn(e):
        u = world.units.get(e)
        p = world.players.get(u.owner) if u else None
        return bool(p and len(p.relations) >= viewer and p.relations[viewer - 1] & 1 and u.owner != viewer)
    return fn


def cursor_input(world, camera, layout, picks, mouse, player_id=PLAYER_ID, projection=None):
    """The `CursorInput` of this frame (docs/engine/ui-layout.md section 6)."""
    in_view = mouse is not None and layout.viewport.contains(*mouse)
    hover = pick_at(picks, *mouse) if in_view else None
    sel = world.players[player_id].selection
    item_cell = False
    if in_view:
        cell = (projection or Projection(world.heights)).hover_cell(camera.ix + mouse[0], camera.iy + mouse[1])
        item_cell = cell is not None and bool(world.items_at(*cell))
    return CursorInput(mouse, layout.screen.w, layout.screen.h, in_view, hover is not None,
                       hover is not None and hostile_to(world, player_id)(hover), item_cell,
                       selection_state(world, player_id), len(sel),
                       len(sel) == 1 and world.units[sel[0]].human)


def run(world, terrain_view, camera, layout=None, speed=DEFAULT_SPEED, title="Allods 2", max_frames=None,
        assets=None, options=None, debug=None, minimap=None, player_id=PLAYER_ID, commands=()):
    """Accumulator main loop: fixed-step sim, variable-rate drawing.  Returns when the window
    closes (or after `max_frames`, for tests).  `layout`: `Layout` of the window size (the camera
    is built from `layout.viewport`).  F1/F2/F3 toggle the debug overlays, Ctrl+H the health bars,
    left mouse selects (click / drag, Shift toggles), right mouse clears, the minimap moves the
    camera.  `commands` are queued before the first tick (the debug-move order)."""
    options, debug = options or DrawOptions(), debug or DebugFlags()
    layout = layout or Layout.for_size(camera.view_w + 160, camera.view_h)
    screen = ensure_display(*layout.size)
    pygame.display.set_caption(title)
    hide_os_cursor()
    fs = assets.fs
    art = InterfaceArt(fs)
    ui = Interface(layout, art)
    cursors = CursorSprites(fs)
    title_of = unit_title_fn(assets)
    panel = MinimapPanel.from_layout(minimap.geometry, layout) if minimap else None
    sim, queue, scroll = Simulation(world), CommandQueue(), ScrollInput()
    for cmd in commands:
        queue.put(cmd)
    player = world.players[player_id]
    items = build_draw_list(world, camera, world.tick, assets, options, debug, player.selection)
    selecting = SelectionInput(player_id, layout.screen.w, lambda: items.picks,
                               lambda e: world.units[e].owner if e in world.units else None,
                               lambda: player.selection, hostile_to(world, player_id))
    caches = Caches(SurfaceCache(terrain_view), SpriteCache(assets))
    period = tick_period_ms(speed)
    clock = pygame.time.Clock()
    projection = Projection(world.heights)
    held, acc, frames = set(), 0, 0
    running = True
    while running:
        dt = clock.tick(60)
        acc += min(dt, MAX_FRAME_MS)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_h and ev.mod & pygame.KMOD_CTRL:
                options = dataclasses.replace(options, health_bars=not options.health_bars)
            elif ev.type == pygame.KEYDOWN and ev.key in DEBUG_KEYS:
                debug.toggle(DEBUG_KEYS[ev.key])
            elif ev.type in (pygame.KEYDOWN, pygame.KEYUP) and ev.key in KEYS:
                (held.add if ev.type == pygame.KEYDOWN else held.discard)(KEYS[ev.key])
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if not (panel and panel.press(camera, *ev.pos)) and layout.viewport.contains(*ev.pos):
                    selecting.press(*ev.pos)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3 and layout.viewport.contains(*ev.pos):
                queue.put(selecting.right_click())
            elif panel and ev.type == pygame.MOUSEMOTION and ev.buttons[0]:
                panel.drag(camera, *ev.pos)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if panel and panel.dragging:
                    panel.release()
                else:
                    cmd = selecting.release(*ev.pos, shift=bool(pygame.key.get_mods() & pygame.KMOD_SHIFT))
                    if cmd is not None:
                        queue.put(cmd)
        mouse = pygame.mouse.get_pos() if pygame.mouse.get_focused() else None
        scroll.update(camera, dt, held, mouse, layout.size)
        while acc >= period:
            sim.step(queue.drain())
            acc -= period
        items = build_draw_list(world, camera, world.tick, assets, options, debug, player.selection)
        ui.draw(screen, caches, build_terrain_items(terrain_view, camera, world.tick), items, camera,
                world, player_id, minimap, panel, title_of)
        state = choose_cursor(cursor_input(world, camera, layout, items.picks, mouse, player_id, projection))
        draw_cursor(screen, cursors, state, mouse, pygame.time.get_ticks())
        pygame.display.flip()
        frames += 1
        if max_frames is not None and frames >= max_frames:
            break
    pygame.quit()
