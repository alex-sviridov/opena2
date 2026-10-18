"""Window and the main loop: the original interface around the map, selection, cursors."""

import dataclasses

import pygame

from engine.sim import DEFAULT_SPEED, CommandQueue, Simulation, tick_period_ms
from allods2.common import as_fs
from engine.ui import (CursorInput, DebugFlags, Layout, MainText, MessageLine, MinimapPanel, OrderInput, ScrollInput,
                       SelectionInput, choose_cursor, choose_minimap_cursor, drain_no_way, target_cell)
from engine.ui.orders import FORMATION_MS, FORMATION_TEXT, minimap_move_cell
from engine.view import DrawOptions, Projection, build_draw_list, build_terrain_items
from engine.view.pick import pick_at

from .cursor import CursorSprites, draw_cursor, hide_os_cursor
from .interface import Interface, InterfaceArt, selection_state, unit_title_fn
from .render import Caches
from .sprites import SpriteCache
from .surfaces import SurfaceCache

MAX_FRAME_MS = 250
DEBUG_KEYS = {pygame.K_F1: "passability", pygame.K_F2: "markers", pygame.K_F3: "depth", pygame.K_F4: "paths"}
ORDER_KEYS = {pygame.K_m: "m", pygame.K_a: "a", pygame.K_d: "d", pygame.K_s: "s", pygame.K_t: "t"}
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


def modifiers():
    """(ctrl, alt, shift) from the keyboard state (globals 0x6227d8 / 0x6227e0 / 0x6227dc)."""
    m = pygame.key.get_mods()
    return bool(m & pygame.KMOD_CTRL), bool(m & pygame.KMOD_ALT), bool(m & pygame.KMOD_SHIFT)


def cursor_input(world, camera, layout, picks, mouse, player_id=PLAYER_ID, projection=None, pending=0,
                 mods=(False, False, False)):
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
                       len(sel) == 1 and world.units[sel[0]].human,
                       hover_is_selected=hover is not None and len(sel) == 1 and hover == sel[0],
                       ctrl=mods[0], alt=mods[1], shift=mods[2], pending=pending)


def click_target(world, camera, layout, picks, pos, projection):
    """(cell, hover_unit) for a click at `pos` (R 1.7): column `(mx >> 5) + camera cell`, relief-aware row of
    `Projection.hover_cell`; None when the pointer is outside the view or no row matches.  No fog or
    passability test."""
    if not layout.viewport.contains(*pos):
        return None, False
    cell = projection.hover_cell(camera.ix + pos[0], camera.iy + pos[1])
    cell = None if cell is None else (target_cell(pos[0], camera.ix >> 5, cell[1]))
    return cell, pick_at(picks, *pos) is not None


def minimap_order_target(projection, camera, layout, panel, pos):
    """Cell of a minimap move order (R 1.6, CONFIRMED `FUN_00418bc3`): the minimap column, but the row is the main
    view's relief row finder applied to the mouse position over the right panel, plus the camera's top cell."""
    cell_x = panel.order_cell(*pos)[0]
    vp = layout.viewport
    row = projection.exe_row(camera.ix >> 5, camera.iy >> 5, vp.w >> 5, vp.h >> 5, *pos)
    return minimap_move_cell(cell_x, vp.h // 32 + 4 if row is None else row, camera.iy >> 5)


def run(world, terrain_view, camera, layout=None, speed=DEFAULT_SPEED, title="Allods 2", max_frames=None,
        assets=None, options=None, debug=None, minimap=None, player_id=PLAYER_ID, commands=()):
    """Accumulator main loop: fixed-step sim, variable-rate drawing.  Returns the `Simulation` when the window
    closes (or after `max_frames`, for tests).  `layout`: `Layout` of the window size (the camera is built from
    `layout.viewport`).  F1-F4 toggle the debug overlays, Ctrl+H the health bars, Ctrl+F cycles the formation.
    Left mouse: click / drag selects, a click with a selection orders by the cursor (move, attack over ground),
    Shift toggles; M / A / D / S arm a pending mode, T stands ground; right click cancels the mode or deselects,
    right drag scrolls; the minimap orders a walk (own units selected) or moves the camera; "No way" shows in
    the message line.  Commands go through the queue and apply on the next tick.  `commands` are queued before
    the first tick (the debug-move order)."""
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
    texts = MainText.load(as_fs(fs))
    messages = MessageLine()
    panel = MinimapPanel.from_layout(minimap.geometry, layout) if minimap else None
    sim, queue, scroll = Simulation(world), CommandQueue(), ScrollInput()
    for cmd in commands:
        queue.put(cmd)
    player = world.players[player_id]
    items = build_draw_list(world, camera, world.tick, assets, options, debug, player.selection)
    selecting = SelectionInput(player_id, layout.screen.w, lambda: items.picks,
                               lambda e: world.units[e].owner if e in world.units else None,
                               lambda: player.selection, hostile_to(world, player_id))
    ordering = OrderInput(player_id, layout.screen.w, lambda: player.selection,
                          lambda: selection_state(world, player_id), player.formation)
    caches = Caches(SurfaceCache(terrain_view), SpriteCache(assets))
    period = tick_period_ms(speed)
    clock = pygame.time.Clock()
    projection = Projection(world.heights)
    held, acc, frames = set(), 0, 0
    right_in_view = False

    def minimap_left(pos):
        """Left press or drag over the minimap (R 1.6): an order inside the image with own units selected."""
        if panel.contains(*pos):
            what, cmd = ordering.minimap_left(minimap_order_target(projection, camera, layout, panel, pos))
            if what == "order":
                if cmd is not None:
                    queue.put(cmd)
                return
        panel.center_camera(camera, *pos)

    running = True
    while running:
        dt = clock.tick(60)
        acc += min(dt, MAX_FRAME_MS)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_h and ev.mod & pygame.KMOD_CTRL:
                options = dataclasses.replace(options, health_bars=not options.health_bars)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_f and ev.mod & pygame.KMOD_CTRL:
                cmd, mode = ordering.key("f", ctrl=True)
                queue.put(cmd)
                messages.show(texts.line(FORMATION_TEXT + mode), pygame.time.get_ticks(), FORMATION_MS)
            elif ev.type == pygame.KEYDOWN and ev.key in DEBUG_KEYS:
                debug.toggle(DEBUG_KEYS[ev.key])
            elif ev.type in (pygame.KEYDOWN, pygame.KEYUP) and ev.key in KEYS:
                (held.add if ev.type == pygame.KEYDOWN else held.discard)(KEYS[ev.key])
            elif ev.type == pygame.KEYDOWN and ev.key in ORDER_KEYS and not ev.mod & pygame.KMOD_CTRL:
                cmd, _ = ordering.key(ORDER_KEYS[ev.key])
                if cmd is not None:
                    queue.put(cmd)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if panel and panel.contains(*ev.pos):
                    panel.dragging = True
                    minimap_left(ev.pos)
                elif layout.viewport.contains(*ev.pos):
                    selecting.press(*ev.pos)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
                if panel and panel.contains(*ev.pos):
                    panel.right_dragging = True                 # minimap right press: always a camera jump
                    panel.center_camera(camera, *ev.pos)
                else:
                    right_in_view = layout.viewport.contains(*ev.pos)
                    ordering.right_press()
            elif ev.type == pygame.MOUSEMOTION and panel and ev.buttons[0] and panel.dragging:
                minimap_left(ev.pos)
            elif ev.type == pygame.MOUSEMOTION and panel and ev.buttons[2] and panel.right_dragging:
                panel.center_camera(camera, *ev.pos)
            elif ev.type == pygame.MOUSEMOTION and ev.buttons[2] and right_in_view:
                cx, cy = ordering.right_move(*ev.rel)
                if cx or cy:
                    camera.move_by(cx * 32, cy * 32)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 3:
                if panel and panel.right_dragging:
                    panel.right_dragging = False
                elif right_in_view or layout.bar_panel.rect.contains(*ev.pos) or layout.info_panel.rect.contains(*ev.pos):
                    cmd = ordering.right_release()               # 0x40c53a, also posted by the bar and info panels
                    if cmd is not None:
                        queue.put(cmd)
                right_in_view = False
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                if panel and panel.dragging:
                    panel.release()
                else:
                    mods = modifiers()
                    cmd = None
                    if ordering.is_order_click(selecting.corner, ev.pos):
                        picks = items.picks
                        ci = cursor_input(world, camera, layout, picks, ev.pos, player_id, projection,
                                          ordering.pending, mods)
                        cell, hover_unit = click_target(world, camera, layout, picks, ev.pos, projection)
                        what, cmd = ordering.release(choose_cursor(ci), cell, hover_unit)
                        if what == "select":
                            cmd = selecting.release(*ev.pos, shift=mods[2])
                            if cmd is not None:
                                ordering.clear_pending()
                        selecting.corner = None
                    else:
                        cmd = selecting.release(*ev.pos, shift=mods[2])
                        if cmd is not None:
                            ordering.clear_pending()           # FUN_00417986 resets the mode (0x417e86)
                    if cmd is not None:
                        queue.put(cmd)
        mouse = pygame.mouse.get_pos() if pygame.mouse.get_focused() else None
        scroll.update(camera, dt, held, mouse, layout.size)
        while acc >= period:
            sim.step(queue.drain())
            acc -= period
        now = pygame.time.get_ticks()
        drain_no_way(world, player_id, messages, now, texts)
        ordering.update()
        items = build_draw_list(world, camera, world.tick, assets, options, debug, player.selection)
        text = messages.current(now)
        ui.draw(screen, caches, build_terrain_items(terrain_view, camera, world.tick), items, camera,
                world, player_id, minimap, panel, title_of, (text,) if text else None)
        if panel and mouse is not None and panel.contains(*mouse):
            state = choose_minimap_cursor(True, selection_state(world, player_id), ordering.pending)
        else:
            state = choose_cursor(cursor_input(world, camera, layout, items.picks, mouse, player_id, projection,
                                               ordering.pending, modifiers()))
        draw_cursor(screen, cursors, state, mouse, now)
        pygame.display.flip()
        frames += 1
        if max_frames is not None and frames >= max_frames:
            break
    pygame.quit()
    return sim
