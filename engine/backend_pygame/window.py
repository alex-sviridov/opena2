"""Window and the main loop: the original interface around the map, selection, cursors."""

import dataclasses
import gc

import pygame

from engine.sim import DEFAULT_SPEED, CommandQueue, SetRetreatMode, Simulation, TickClock, tick_period_ms
from engine.sim import ai as ai_mod
from engine.sim import spells as spell_mod
from engine.ui import (CursorInput, CursorState, DebugFlags, Layout, MinimapPanel, OrderInput, ScrollInput,
                       SelectionInput, bar, choose_cursor, choose_minimap_cursor, drain_no_way, level_up_messages, target_cell)
from engine.ui.book import button_text as book_button_text, draw_views
from engine.ui.pack import KIND_SLOT, button_text as pack_button_text, doll_tip
from engine.ui.info import is_hero
from engine.ui.selection import band_lines, clip_to, drag_nonempty
from engine.ui.widgets import info_button_rect
from engine.ui.spellbook import auto_slot_mask, selection_item_mask, selection_slot_mask
from engine.ui.tooltip import TooltipTimer, bar_text
from engine.ui.orders import FORMATION_MS, FORMATION_TEXT, HEALTH_TEXT, castable_spell, minimap_move_cell
from engine.view import DrawOptions, Projection, build_draw_list, build_terrain_items
from engine.view.damage import FloatingDamage, unit_anchor
from engine.world import Damage, Died, LevelUp, Loot, Removed
from engine.view import fog as fog_view
from engine.view.pick import pick_at

from .cursor import CursorSprites, draw_cursor, hide_os_cursor
from .interface import Interface, InterfaceArt, info_picture_fn, make_game_ui, message_line, selection_state
from .render import Caches, player_ramp
from .text import measure as text_measure
from .sprites import SpriteCache
from .surfaces import SurfaceCache

DEBUG_KEYS = {pygame.K_F1: "passability", pygame.K_F2: "markers", pygame.K_F3: "depth"}
DEBUG_SHIFT_KEYS = {pygame.K_F4: "paths", pygame.K_F5: "ai"}       # F4-F12 are the exe's spell shortcuts (research 1.4): the overlays moved to Shift+F4 / Shift+F5
FKEY_NUMBERS = {getattr(pygame, "K_F%d" % n): n for n in range(4, 13)}
SMOOTHING_TEXT = 0x6A                                                # main.txt 0x6a + state: "Smoothing is Off" / "On" (Ctrl+O, DAT_00622768)
OPTION_KEYS = {pygame.K_w: "w", pygame.K_n: "n", pygame.K_c: "c", pygame.K_u: "u"}     # Ctrl+W retreat, N day/night, C colours, U auto-cast (messages.OptionToggles)
FLYING_TEXT = 0x66                                                   # main.txt 0x66 + state: "Flying damage is Off" / "On"
ORDER_KEYS = {pygame.K_m: "m", pygame.K_a: "a", pygame.K_d: "d", pygame.K_s: "s", pygame.K_t: "t", pygame.K_g: "g", pygame.K_r: "r", pygame.K_l: "l", pygame.K_c: "c", pygame.K_p: "p"}
BOOK_KEYS = {pygame.K_b, pygame.K_q, pygame.K_SPACE, pygame.K_i, pygame.K_BACKQUOTE}     # message 0x40f (B, Q) / 0x40e (I, backquote) / both (Space): the spell book and the backpack (`0x40cd29`, `0x40ccb6`, `0x40cd6e`)
CHAT_KEYS = {pygame.K_BACKSPACE: "backspace", pygame.K_UP: "up"}       # the edit line's extra keys (engine.ui.chat)
NAMED_KEYS = {pygame.K_ESCAPE: "escape", pygame.K_PAUSE: "pause", pygame.K_TAB: "tab", pygame.K_RETURN: "return", pygame.K_KP_ENTER: "return"}
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
    """`entity -> bool`: the owner of the unit or structure is at war with the viewer (relation bit 0, INFERRED; `FUN_0041e830` on the object's owner)."""
    def fn(e):
        o = world.units.get(e) or world.objects.get(e)
        p = world.players.get(o.owner) if o else None
        return bool(p and len(p.relations) >= viewer and p.relations[viewer - 1] & 1 and o.owner != viewer)
    return fn


def modifiers():
    """(ctrl, alt, shift) from the keyboard state (globals 0x6227d8 / 0x6227e0 / 0x6227dc)."""
    m = pygame.key.get_mods()
    return bool(m & pygame.KMOD_CTRL), bool(m & pygame.KMOD_ALT), bool(m & pygame.KMOD_SHIFT)


def hover_flags(world, entity, assets=None):
    """(is_structure, usable) of a hovered entity: units and flyers are 1 / 2 in `FUN_004180c6`; a structure is 0x20, plus 0x800 when its
    structures.reg record has `Usable` (`+0x8c`; needs `assets`, else not usable).  Unit ids win a collision (none on the shipped maps)."""
    if entity is None or entity in world.units:
        return False, False
    ent = world.objects.get(entity)
    if ent is None or ent.kind == "object":
        return False, False
    aset = assets.structure_set(ent.type_id) if assets is not None and ent.kind == "structure" else None
    return True, bool(aset is not None and aset.rec.get("Usable"))


def cursor_input(world, camera, layout, picks, mouse, player_id=PLAYER_ID, projection=None, pending=0,
                 mods=(False, False, False), drag_from=None, assets=None):
    """The `CursorInput` of this frame (docs/engine/ui-layout.md section 6).  `picks`: `DrawList.hover_picks` (units and structures); the item
    flag 0x40 and the fogged flag 0x400 come from the four tiles of the cell under the pointer (`FUN_004180c6`)."""
    in_view = mouse is not None and layout.viewport.contains(*mouse)
    hover = pick_at(picks, *mouse) if in_view else None
    sel = world.players[player_id].selection
    item_cell = fogged = False
    if in_view:
        cell = (projection or Projection(world.heights)).hover_cell(camera.ix + mouse[0], camera.iy + mouse[1])
        if cell is not None:
            seen = fog_view.cell_visible(world, *cell)
            item_cell = seen and bool(world.items_at(*cell))
            fogged = not seen
    structure, usable = hover_flags(world, hover, assets)
    return CursorInput(mouse, layout.screen.w, layout.screen.h, in_view, hover is not None and not structure,
                       hover is not None and hostile_to(world, player_id)(hover), item_cell,
                       selection_state(world, player_id), len(sel),
                       len(sel) == 1 and world.units[sel[0]].human,
                       hover_structure=structure, hover_enterable=usable, hover_fogged=fogged,
                       hover_is_selected=hover is not None and len(sel) == 1 and hover == sel[0],
                       ctrl=mods[0], alt=mods[1], shift=mods[2], pending=pending,
                       dragging=drag_nonempty(drag_from, mouse))


def click_target(world, camera, layout, picks, pos, projection):
    """(cell, hover) for a click at `pos` (R 1.7): column `(mx >> 5) + camera cell`, relief-aware row of
    `Projection.hover_cell`; None when the pointer is outside the view or no row matches.  No fog or
    passability test.  `hover` is the entity id under the pointer or None (an attack order needs the id)."""
    if not layout.viewport.contains(*pos):
        return None, None
    cell = projection.hover_cell(camera.ix + pos[0], camera.iy + pos[1])
    cell = None if cell is None else (target_cell(pos[0], camera.ix >> 5, cell[1]))
    return cell, pick_at(picks, *pos)


def feed_fight_log(world, floats, assets, player_id, options, debug, now_ms):
    """Drain `world.fight_log`: floating numbers for blows that took HP (message 0x73 with the option on), console lines for
    `--debug combat`."""
    log, world.fight_log[:] = list(world.fight_log), []
    for e in log:
        if isinstance(e, Damage):
            if debug.combat:
                print("tick %d: %#x -> %#x %s roll %+d damage %d hp %d" % (e.tick, e.attacker, e.target, "hit " if e.hit else "miss",
                                                                          e.roll, e.amount, e.hp))
            v = world.find_unit(e.target)
            if e.amount > 0 and options.flying_damage and v is not None:
                aset = assets.unit_set(v.type_id)
                p = world.players.get(v.owner)
                floats.add(v.id, e.amount, p.colour if p else 0, v.owner != player_id, aset.t.TileSize if aset else 1, now_ms, e.tick)
        elif isinstance(e, Died) and debug.combat:
            print("tick %d: %#x died (killed by %#x)" % (e.tick, e.unit, e.by))
        elif debug.combat and isinstance(e, Removed):
            print("tick %d: %#x removed" % (e.tick, e.unit))
        elif debug.combat and isinstance(e, LevelUp):
            print("tick %d: %#x skill %d -> %d" % (e.tick, e.unit, e.school, e.skill))
        elif debug.combat and isinstance(e, Loot):
            print("tick %d: %#x dropped gold %d, %d items at (%d, %d)" % (e.tick, e.unit, e.gold, len(e.codes), e.x, e.y))


def floating_entries(world, floats, camera, assets, fs, now_ms):
    """[(text, ramp, x, y)] of the live numbers, in view pixels."""
    out = []
    for n in floats.visible(now_ms):
        u = world.find_unit(n.unit)
        if u is not None and not fog_view.unit_visible(world, u):       # `FUN_0045c6cd`: the number is kept (until 1000 ms) but not drawn while unit `+0x7c` != 0
            continue
        anchor = unit_anchor(world, camera, assets, u) if u is not None else None
        if anchor is not None:
            out.append((str(n.value), player_ramp(n.colour, fs), anchor[0] + n.x, anchor[1] + n.y))
    return out


def minimap_order_target(projection, camera, layout, panel, pos):
    """Cell of a minimap move order (R 1.6, CONFIRMED `FUN_00418bc3`): the minimap column, but the row is the main
    view's relief row finder applied to the mouse position over the right panel, plus the camera's top cell."""
    cell_x = panel.order_cell(*pos)[0]
    vp = layout.viewport
    row = projection.exe_row(camera.ix >> 5, camera.iy >> 5, vp.w >> 5, vp.h >> 5, *pos)
    return minimap_move_cell(cell_x, vp.h // 32 + 4 if row is None else row, camera.iy >> 5)


def ai_overlay(world, debug, selection):
    """{unit id: `ai.overlay`} for the selected monsters while the `ai` debug flag is on (Shift+F5), else None."""
    if not debug.ai or not world.ai_on:
        return None
    return {uid: ai_mod.overlay(world, world.units[uid]) for uid in selection if uid in world.units}


def spells_txt_lines(fs):
    """The lines of main/text/spells.txt (`FUN_00474733`: `Name (Type)#Description` per slot), None without the file."""
    from allods2.common import as_fs

    from engine.ui import MainText
    try:
        return MainText.load(as_fs(fs), "main/text/spells.txt").lines
    except (OSError, KeyError, FileNotFoundError):
        return None


def hover_text(ui, ordering, world, selection, sel_state, cast_enabled, pos, spell_lines):
    """The tooltip text under `pos`: the open spell book's slot, the info panel's book button, else the command bar's cell."""
    if ui.frozen:
        return ""
    if ui.pack.carried is not None:
        return ""                                       # `FUN_004ae232`, `FUN_004a3f0b`, `FUN_004ad61c`: no tooltip while an item is carried
    if ui.pack.contains(pos):
        return ui.pack.tooltip_text(pos, world, ui.main)
    if ui.book.contains(pos):
        return ui.book.tooltip_text(pos, world, selection, ordering.mask_fn() if sel_state == "own" else 0, spell_lines, ui.main.lines)
    if info_button_rect(ui.layout, "book").contains(*pos):
        return book_button_text(ui.book.open, ui.main)
    if info_button_rect(ui.layout, "pack").contains(*pos):
        return pack_button_text(ui.pack.open, ui.main)
    if info_button_rect(ui.layout, "mode").contains(*pos) and not ui.layout.text_in_extra:
        return ui.main.line(0xC if ui.shown_mode == "text" else 0xD)       # `FUN_004ae232`: main 0xc "Switch to Picture" in the text mode, 0xd "Switch to Stats"
    if info_button_rect(ui.layout, "menu").contains(*pos):
        return ui.main.line(0xE)
    slot = ui.doll_slot_at(pos)
    if slot >= 0:
        return doll_tip(world, ui, slot)
    return bar_text(ui.layout, pos, sel_state, cast_enabled, ui.main)


def key_name(ev):
    """The `engine.ui` key name of a KEYDOWN event: 'escape', 'pause', 'tab', 'return', or the lower-case letter."""
    return NAMED_KEYS.get(ev.key) or KEYS.get(ev.key) in ("up", "down") and KEYS[ev.key] or (chr(ev.key) if 32 <= ev.key < 127 else "")


def run(world, terrain_view, camera, layout=None, speed=DEFAULT_SPEED, title="Allods 2", max_frames=None,
        assets=None, options=None, debug=None, minimap=None, player_id=PLAYER_ID, commands=(), ai=True,
        trace=False, hero_name="Hero", mission_id=None, frame_hook=None, sim_hook=None):
    """Accumulator main loop: fixed-step sim, variable-rate drawing.  Returns the `Simulation` when the window
    closes (or after `max_frames`, for tests).  `layout`: `Layout` of the window size (the camera is built from
    `layout.viewport`).  `ai`: the monsters think (docs/engine/ai.md; `--no-ai` of the CLI).  F1-F3 and Shift+F4/F5 toggle the debug overlays, F4-F12 are the spell shortcuts, Ctrl+H the health bars, Ctrl+F cycles the formation.
    Left mouse: click / drag selects, a click with a selection orders by the cursor (move, attack over ground),
    Shift toggles; M / A / D / S arm a pending mode, T stands ground, R retreats; right click cancels the mode or deselects,
    right drag scrolls; the minimap orders a walk (own units selected) or moves the camera; "No way" shows (with --trace) in
    the message line.  Commands go through the queue and apply on the next tick.  `commands` are queued before
    the first tick (the debug-move order).

    The interface is `engine.ui.GameUi` (docs/engine/ui-layout.md 11): ESC opens the menu (End Quest -> Exit leaves), the Pause key a notice
    window, TAB toggles the info panel's picture / text mode; while any dialog is open the loop skips `sim.step`, closes the tick block at resume (`TickClock.resume`: one tick, no burst), freezes the edge scroll and the world input, and keeps drawing.  Closing the window quits at once.  `trace`: the "No way" line (the
    exe's `-trace`), `hero_name`: the name of the player's heroes, `mission_id`: the `mission<id>.txt` of the story windows.
    `frame_hook(frame, ui, world)` runs at the start of every frame (a test hook); `sim_hook(sim)` gets the `Simulation` once built
    (the session recorder of `play`)."""
    options, debug = options or DrawOptions(), debug or DebugFlags()
    layout = layout or Layout.for_size(camera.view_w + 160, camera.view_h)
    screen = ensure_display(*layout.size)
    pygame.display.set_caption(title)
    hide_os_cursor()
    fs = assets.fs
    art = InterfaceArt(fs)
    iface = Interface(layout, art)
    cursors = CursorSprites(fs)
    info_picture = info_picture_fn(assets)
    ui = make_game_ui(assets, layout, world, player_id, mission_id, trace, hero_name)
    ui.doll_mask = lambda u: iface.panels.doll_mask(world, u)
    texts, messages = ui.main, ui.messages
    panel = MinimapPanel.from_layout(minimap.geometry, layout) if minimap else None
    sim, queue, scroll = Simulation(world, ai=ai, triggers=world.script is not None, vision=world.fog is not None), CommandQueue(), ScrollInput()
    sim.ui = ui
    if sim_hook is not None:
        sim_hook(sim)
    for cmd in commands:
        queue.put(cmd)
    player = world.players[player_id]
    items = build_draw_list(world, camera, world.tick, assets, options, debug, player.selection, ai_info=ai_overlay(world, debug, player.selection))
    selecting = SelectionInput(player_id, layout.screen.w, lambda: items.hover_picks,
                               lambda e: world.units[e].owner if e in world.units else None,
                               lambda: player.selection, hostile_to(world, player_id))
    ordering = OrderInput(player_id, layout.screen.w, lambda: player.selection,
                          lambda: selection_state(world, player_id), player.formation, lambda: castable_spell(world, player_id),
                          lambda: selection_slot_mask(world, player.selection) if selection_state(world, player_id) == "own" else 0,
                          lambda: selection_item_mask(world, player.selection) if selection_state(world, player_id) == "own" else 0,
                          lambda uid: uid in world.units and is_hero(world.units[uid]))
    ordering.book = ui.book
    caches = Caches(SurfaceCache(terrain_view), SpriteCache(assets))
    ticks = TickClock(tick_period_ms(speed), pygame.time.get_ticks())
    was_frozen = False
    clock = pygame.time.Clock()
    projection = Projection(world.heights)
    held, frames = set(), 0
    right_in_view = False
    floats = FloatingDamage()
    tips = TooltipTimer()
    text_measure_font2 = lambda t: text_measure(t, 2)       # tooltips use font2 (`FUN_00427999`)
    spell_lines = spells_txt_lines(assets.fs)

    def minimap_left(pos):
        """Left press or drag over the minimap (R 1.6): an order inside the image with own units selected."""
        if panel.contains(*pos):
            what, cmd = ordering.minimap_left(minimap_order_target(projection, camera, layout, panel, pos))
            if what == "order":
                if cmd is not None:
                    queue.put(cmd)
                return
        panel.center_camera(camera, *pos)

    gc.collect()
    gc.freeze()                         # the loaded world and art stay out of the collector's scans: a gen-2 pass over them paused a frame ~30 ms
    running = True
    state = CursorState.DEFAULT                 # the cursor of the previous frame (a pending mode without a cursor keeps it)
    while running:
        if frame_hook is not None:
            frame_hook(frames, ui, world)
        dt = clock.tick(60)
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYUP and ev.key in KEYS:
                held.discard(KEYS[ev.key])                      # always: a key released inside a dialog must not stay down
            elif ev.type == pygame.KEYDOWN and ui.chat.open and not ui.frozen:
                ui.chat_key(CHAT_KEYS.get(ev.key) or NAMED_KEYS.get(ev.key) or "", ev.unicode, pygame.time.get_ticks())     # every key goes to the line (ui-layout 11.5)
            elif ev.type == pygame.KEYDOWN and (ui.frozen or ev.key in NAMED_KEYS) and ui.key(key_name(ev)):
                pass                                            # ESC / Pause / TAB / a dialog's keys (ui-layout 11.4)
            elif ui.frozen:
                if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                    selecting.corner = None
                    ui.mouse_down(ev.pos)
                elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                    selecting.corner = None
                    ui.mouse_up(ev.pos)                         # every other event is dropped: mode != 1 (no cursor, hotkeys, right drag)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_h and ev.mod & pygame.KMOD_CTRL:
                options = dataclasses.replace(options, health_bars=not options.health_bars)     # FUN_0041f0e0 + text 0x64/0x65
                messages.show(texts.line(HEALTH_TEXT + int(options.health_bars)), pygame.time.get_ticks(), FORMATION_MS)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_l and ev.mod & pygame.KMOD_CTRL:
                options = dataclasses.replace(options, flying_damage=not options.flying_damage)     # FUN_0041f120 + text 0x66/0x67
                messages.show(texts.line(FLYING_TEXT + int(options.flying_damage)), pygame.time.get_ticks(), FORMATION_MS)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_o and ev.mod & pygame.KMOD_CTRL:
                options = dataclasses.replace(options, smoothing=not options.smoothing)         # DAT_00622768 + text 0x6a/0x6b
                messages.show(texts.line(SMOOTHING_TEXT + int(options.smoothing)), pygame.time.get_ticks(), FORMATION_MS)
            elif ev.type == pygame.KEYDOWN and ev.key in OPTION_KEYS and ev.mod & pygame.KMOD_CTRL:
                if ui.option_key(OPTION_KEYS[ev.key], pygame.time.get_ticks()) and ev.key == pygame.K_w:
                    queue.put(SetRetreatMode(player_id, ui.toggles.retreat))       # FUN_0041a4ef: message 0x46 sub 1
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_f and ev.mod & pygame.KMOD_CTRL:
                cmd, mode = ordering.key("f", ctrl=True)
                queue.put(cmd)
                messages.show(texts.line(FORMATION_TEXT + mode), pygame.time.get_ticks(), FORMATION_MS)
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_a and ev.mod & pygame.KMOD_CTRL:
                mp = pygame.mouse.get_pos() if pygame.mouse.get_focused() else None
                for cmd in ordering.auto_cast(lambda uid, n: uid in world.units and (spell_mod.known_mask(world.units[uid]) >> n) & 1,
                                              ui.book.slot_at(mp) if mp is not None else -1):      # Ctrl+A: FUN_004c74b1 -> message 0x46 sub 4
                    queue.put(cmd)
            elif ev.type == pygame.KEYDOWN and ev.key in DEBUG_SHIFT_KEYS and ev.mod & pygame.KMOD_SHIFT:
                debug.toggle(DEBUG_SHIFT_KEYS[ev.key])
            elif ev.type == pygame.KEYDOWN and ev.key in FKEY_NUMBERS:
                mp = pygame.mouse.get_pos() if pygame.mouse.get_focused() else None
                n, ctrl, shift = FKEY_NUMBERS[ev.key], bool(ev.mod & pygame.KMOD_CTRL), bool(ev.mod & pygame.KMOD_SHIFT)
                ui.sync_pack()
                if ctrl and not shift and mp is not None and ui.pack.bind_key(n, mp, world):
                    ordering.hotkeys[n - 4] = None                  # Ctrl+F<n> over a pack cell: the item takes the key (table entry type 2, `FUN_004a3cef`)
                elif not ctrl and ui.pack.item_keys[n - 4] is not None:
                    for c in ui.pack.use_key(n, world, player_id, ordering):
                        queue.put(c)                                # F<n> with an item bound: one piece is put to the hero
                else:
                    ordering.fkey(n, ctrl=ctrl, shift=shift, hover_slot=ui.book.slot_at(mp) if mp is not None else -1)
                    if ordering.hotkeys[n - 4] is not None:
                        ui.pack.item_keys[n - 4] = None
            elif ev.type == pygame.KEYDOWN and ev.key in DEBUG_KEYS:
                debug.toggle(DEBUG_KEYS[ev.key])
            elif ev.type in (pygame.KEYDOWN, pygame.KEYUP) and ev.key in KEYS:
                (held.add if ev.type == pygame.KEYDOWN else held.discard)(KEYS[ev.key])
            elif ev.type == pygame.KEYDOWN and ev.key in BOOK_KEYS and not ev.mod & pygame.KMOD_CTRL:
                ui.key(key_name(ev))
            elif ev.type == pygame.KEYDOWN and ev.key in ORDER_KEYS and not ev.mod & pygame.KMOD_CTRL:
                cmd, _ = ordering.key(ORDER_KEYS[ev.key])
                if cmd is not None:
                    queue.put(cmd)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                if panel and panel.contains(*ev.pos):
                    panel.dragging = True
                    minimap_left(ev.pos)
                else:
                    taken, cmd = ui.mouse_down(ev.pos, ordering, bool(ordering.slot_mask()), getattr(ev, "clicks", 1))
                    for c in (cmd if isinstance(cmd, tuple) else (cmd,)):
                        if c is not None:
                            queue.put(c)
                    if not taken and layout.viewport.contains(*ev.pos):
                        tips.hide()                             # `FUN_0042748f`: a left press in the world hides the tooltip
                        selecting.press(*ev.pos)
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 3:
                if panel and panel.contains(*ev.pos):
                    panel.right_dragging = True                 # minimap right press: always a camera jump
                    panel.center_camera(camera, *ev.pos)
                elif ui.book_right_down(ev.pos, ordering):
                    right_in_view = False                       # the spell book took it: the slot is deselected, the view never sees the release
                else:
                    right_in_view = layout.viewport.contains(*ev.pos)
                    ordering.right_press()
            elif ev.type == pygame.MOUSEMOTION and ev.buttons[0] and not ui.frozen and layout.bar_panel.rect.contains(*ev.pos):
                cmd = ui.bar_press(ev.pos, ordering, bool(ordering.slot_mask()))        # `FUN_004adb35`: a move with the left button held is a press
                if cmd is not None:
                    queue.put(cmd)
            elif ev.type == pygame.MOUSEMOTION and ev.buttons[0] and selecting.corner is None and ui.pack.carried is None and ui.pack_mouse_move(ev.pos, True, bool(pygame.key.get_mods() & pygame.KMOD_SHIFT)):
                pass                                            # a cell / a doll layer picked up (`0x4a3a1d`, `0x4af120`)
            elif ev.type == pygame.MOUSEMOTION and (ev.buttons[0] or ev.buttons[2]) and ui.book.contains(ev.pos):
                ui.book_mouse_move(ev.pos, ev.buttons[0], ev.buttons[2], ordering)         # `0x4c77a2`
            elif ev.type == pygame.MOUSEMOTION and panel and ev.buttons[0] and panel.dragging:
                minimap_left(ev.pos)
            elif ev.type == pygame.MOUSEMOTION and panel and ev.buttons[2] and panel.right_dragging:
                panel.center_camera(camera, *ev.pos)
            elif ev.type == pygame.MOUSEMOTION and ev.buttons[2] and right_in_view:
                cx, cy = ordering.right_move(*ev.rel)
                if cx or cy:
                    camera.move_by(cx * 32, cy * 32)
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 3:
                ui.book.right_up()
                if panel and panel.right_dragging:
                    panel.right_dragging = False
                elif right_in_view or layout.bar_panel.rect.contains(*ev.pos) or layout.info_panel.rect.contains(*ev.pos):
                    cmd = ordering.right_release()               # 0x40c53a, also posted by the bar and info panels
                    if cmd is not None:
                        queue.put(cmd)
                right_in_view = False
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                ui.book.left_up()
                handled, cmds = ui.item_release(ev.pos, ordering) if panel is None or not panel.dragging else (False, ())
                for c in cmds:
                    queue.put(c)
                if not handled and selecting.corner is None and not (panel and panel.dragging) and ui.info_release(ev.pos):
                    pass                                        # an info panel button acts on the release (`FUN_004aebc8`)
                elif handled and selecting.corner is None:
                    pass                                        # an item was put down: no press began in the map, so no selection / order dispatch (`FUN_0040c5d1`)
                elif panel and panel.dragging:
                    panel.release()
                else:
                    mods = modifiers()
                    cmd = None
                    if selecting.corner is not None:
                        ev = pygame.event.Event(ev.type, pos=clip_to(layout.viewport, ev.pos), button=ev.button)   # the pointer was clipped to the view (`FUN_0048acbc`)
                    if ordering.is_order_click(selecting.corner, ev.pos):
                        picks = items.hover_picks
                        ci = cursor_input(world, camera, layout, picks, ev.pos, player_id, projection,
                                          ordering.pending, mods, assets=assets)
                        cell, hover_unit = click_target(world, camera, layout, picks, ev.pos, projection)
                        what, cmd = ordering.release(choose_cursor(ci, state), cell, hover_unit)
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
        if ui.quit:
            running = False
        mouse = pygame.mouse.get_pos() if pygame.mouse.get_focused() else None
        steps = 0
        if ui.frozen:
            selecting.corner = None                 # a dialog closes the capture without a release (`FUN_0048b33b`, `FUN_0048b1f9`: `FUN_00427501`)
            was_frozen = True                       # a dialog is open: no server step, no scroll
        else:
            scroll.update(camera, dt, held, mouse, layout.size, captured=selecting.corner is not None)     # no edge scroll while the capture `mgr+0x9c` is open
            if was_frozen:
                ticks.resume()                      # `FUN_004891d8` zeroes the block counter, not the base (ui-layout 11.4)
                was_frozen = False
            for _ in range(ticks.advance(pygame.time.get_ticks())):
                sim.step(queue.drain())
                terrain_view.set_clock(world.tick)      # FUN_0041d3b9 cadence: every 320 ticks, option on only
                steps += 1
        now = pygame.time.get_ticks()
        ui.knowledge.feed(world, player_id)            # before feed_fight_log drains the Killed entries
        level_up_messages(world, player_id, messages, now, texts, lambda h: h.name or hero_name)
        feed_fight_log(world, floats, assets, player_id, options, debug, now)
        floats.advance(steps)
        floats.prune(now)
        drain_no_way(world, player_id, messages, now, texts, trace)
        ui.poll(now)
        ui.after_step()
        ui.sync_pack()
        ordering.update()
        hover = (pick_at(items.hover_picks, *mouse) if mouse is not None and not ui.frozen and layout.viewport.contains(*mouse) and not ui.book.contains(mouse)
                 else None)
        items = build_draw_list(world, camera, world.tick, assets, options, debug, player.selection, hover,
                                ai_info=ai_overlay(world, debug, player.selection),
                                hidden={ui.pack.carried.unit: ui.pack.carried.index + 1} if ui.pack.carried is not None and ui.pack.carried.kind == KIND_SLOT else None)
        lines = [(t, player_ramp(c[1], fs) if isinstance(c, tuple) else c) for t, c in messages.entries(now)]      # ("player", colour row) = `0x61fac8 + 32 * row`
        numbers = floating_entries(world, floats, camera, assets, fs, now) if options.flying_damage else ()
        sel_state = selection_state(world, player_id)
        cast_enabled = bool(ordering.slot_mask()) if sel_state == "own" else False
        book_views = draw_views(ui.book, ordering, world, player.selection, sel_state == "own") if ui.book.open else None
        pack_view = ui.pack.views(world, mouse) if ui.pack.open else None
        tip = tips.update(dt, mouse, lambda p: hover_text(ui, ordering, world, player.selection, sel_state, cast_enabled, p, spell_lines), text_measure_font2, layout.size, ui.frozen)
        iface.draw(screen, caches, build_terrain_items(terrain_view, camera, world.tick, items.lights), items, camera,
                   world, player_id, minimap, panel, None, lines or None, numbers, hover, ui,
                   bar.cells(sel_state, cast_enabled, ordering.pending, ui.bar.highlight(ordering.pending)), mouse, info_picture, tip, book_views, pack_view)
        if ui.frozen:
            state = CursorState.DEFAULT
        elif ui.book.contains(mouse) or ui.pack.contains(mouse):
            state = CursorState.DEFAULT                 # an open dialog window (ids 2 / 3) under the pointer: the default cursor (ui-layout 6)
        elif panel and mouse is not None and panel.contains(*mouse):
            state = choose_minimap_cursor(True, selection_state(world, player_id), ordering.pending)
        else:
            state = choose_cursor(cursor_input(world, camera, layout, items.hover_picks, mouse, player_id, projection,
                                               ordering.pending, modifiers(), selecting.corner, assets=assets), state)
        if selecting.corner is not None and mouse is not None:
            for x, y, w, h in band_lines(selecting.corner, clip_to(layout.viewport, mouse)):
                screen.fill((255, 255, 255), (x, y, w, h))      # the white rubber band of the capture (`FUN_0042754f`)
        if ui.pack.carried is not None and not ui.frozen:
            iface.panels.draw_carried(screen, ui.pack.carried.item, mouse)       # the carried item replaces the pointer (`FUN_0048ad7b`)
        else:
            draw_cursor(screen, cursors, state, mouse, now)
        pygame.display.flip()
        caches.terrain.prewarm(camera, world.tick)         # the cells just outside the view, so a scroll does not build a row at once
        frames += 1
        if max_frames is not None and frames >= max_frames:
            break
    gc.unfreeze()
    pygame.quit()
    return sim
