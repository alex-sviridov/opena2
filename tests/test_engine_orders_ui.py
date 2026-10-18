"""Click-to-move UI (H3 stage B): cursor chooser rows, OrderInput dispatch, pending mode, right button, minimap,
"No way" message, and a headless scripted click sequence.  Research: docs/engine/click-to-move-research.md."""

import os

import numpy as np
import pytest

from engine.sim import MoveUnits, SelectUnits, SetFormation, Simulation, Stop
from engine.ui import (CursorInput, CursorState as S, MainText, MessageLine, MinimapPanel, OrderInput, choose_cursor,
                       choose_minimap_cursor, drain_no_way, target_cell)
from engine.ui.orders import NO_WAY_MS, right_drag_cells
from engine.view import MinimapGeometry
from engine.world import NoWay, World

from helpers import GFS, needs_graphics

W, H = 640, 480
ME = 1


def ci(**kw):
    base = dict(in_viewport=True, selection="own", selected_count=2)
    base.update(kw)
    return CursorInput((100, 100), W, H, **base)


# --- choose_cursor, R 1.3 table -------------------------------------------------------------------------------

@pytest.mark.parametrize("hover,mods,want", [
    # ground
    (dict(), {}, S.MOVE), (dict(), dict(ctrl=True), S.SWARM), (dict(), dict(alt=True), S.MOVE),
    (dict(), dict(ctrl=True, alt=True), S.SWARM), (dict(), dict(shift=True), S.MOVE),
    # own / neutral unit
    (dict(hover_unit=True), {}, S.SELECT), (dict(hover_unit=True), dict(ctrl=True), S.ATTACK),
    (dict(hover_unit=True), dict(alt=True), S.MOVE), (dict(hover_unit=True), dict(ctrl=True, alt=True), S.MOVE),
    # hostile unit
    (dict(hover_unit=True, hover_hostile=True), {}, S.ATTACK),
    (dict(hover_unit=True, hover_hostile=True), dict(ctrl=True), S.SWARM),
    (dict(hover_unit=True, hover_hostile=True), dict(alt=True), S.MOVE),
    (dict(hover_unit=True, hover_hostile=True), dict(ctrl=True, alt=True), S.MOVE),
    # hostile structure
    (dict(hover_structure=True, hover_hostile=True), {}, S.SELECT),
    (dict(hover_structure=True, hover_hostile=True), dict(ctrl=True), S.SELECT),
    (dict(hover_structure=True, hover_hostile=True), dict(alt=True), S.MOVE),
    # own structure
    (dict(hover_structure=True), {}, S.SELECT), (dict(hover_structure=True), dict(ctrl=True), S.ATTACK),
])
def test_cursor_rows_own_selection(hover, mods, want):
    assert choose_cursor(ci(**hover, **mods)) is want


def test_pickup_and_town():
    hero = dict(selected_count=1, single_is_hero=True)
    assert choose_cursor(ci(**hero, hover_item_cell=True)) is S.PICKUP
    assert choose_cursor(ci(**hero, hover_item_cell=True, ctrl=True)) is S.SWARM          # modifiers win
    assert choose_cursor(ci(**hero, hover_item_cell=True, alt=True)) is S.MOVE
    assert choose_cursor(ci(**hero, hover_unit=True, hover_item_cell=True, hover_is_selected=True)) is S.PICKUP
    assert choose_cursor(ci(**hero, hover_unit=True, hover_item_cell=True)) is S.SELECT   # another unit on the pile
    assert choose_cursor(ci(**hero, hover_structure=True, hover_enterable=True)) is S.TOWN
    assert choose_cursor(ci(**hero, hover_structure=True, hover_enterable=True, ctrl=True)) is S.ATTACK
    assert choose_cursor(ci(selected_count=1, hover_structure=True, hover_enterable=True)) is S.SELECT


@pytest.mark.parametrize("sel", ["none", "foreign"])
def test_no_orders_from_foreign_or_empty_selection(sel):
    kw = dict(selection=sel, selected_count=0 if sel == "none" else 1)
    assert choose_cursor(ci(**kw)) is S.DEFAULT
    assert choose_cursor(ci(**kw, ctrl=True)) is S.DEFAULT
    assert choose_cursor(ci(**kw, hover_unit=True, hover_hostile=True)) is S.SELECT
    assert choose_cursor(ci(**kw, hover_structure=True)) is S.SELECT


@pytest.mark.parametrize("mode,want", [(1, S.ATTACK), (2, S.MOVE), (4, S.DEFEND), (5, S.CAST), (6, S.SWARM),
                                      (8, S.PATROL)])
def test_pending_cursors_ignore_hover_and_modifiers(mode, want):
    for kw in (dict(), dict(hover_unit=True, hover_hostile=True, ctrl=True), dict(alt=True),
               dict(selection="none", selected_count=0)):
        assert choose_cursor(ci(pending=mode, **kw)) is want
    assert choose_cursor(ci(pending=5, hover_fogged=True)) is S.MOVE


def test_border_beats_pending_and_panels_are_default():
    assert choose_cursor(CursorInput((0, 100), W, H, in_viewport=True, pending=2)) is S.ARROW_W
    assert choose_cursor(CursorInput((100, 100), W, H, in_viewport=False, pending=2)) is S.DEFAULT


def test_minimap_cursors():
    assert choose_minimap_cursor(False, "own", 0) is S.SDEFAULT
    assert choose_minimap_cursor(True, "none", 0) is S.SDEFAULT
    assert choose_minimap_cursor(True, "foreign", 2) is S.SDEFAULT
    assert choose_minimap_cursor(True, "own", 0) is S.SMOVE
    assert [choose_minimap_cursor(True, "own", m) for m in (1, 2, 4, 5, 6, 8)] == [
        S.SATTACK, S.SMOVE, S.SDEFEND, S.SCAST, S.SATTACK, S.SPATROL]


# --- OrderInput -----------------------------------------------------------------------------------------------

def make(sel=(10, 11), state="own", formation=1):
    box = {"sel": sel, "state": state}
    oi = OrderInput(ME, W, lambda: box["sel"], lambda: box["state"], formation)
    return oi, box


@pytest.mark.parametrize("cursor,hover_unit,cmd", [
    (S.MOVE, False, True), (S.MOVE, True, True),                     # alt over an enemy unit walks
    (S.ATTACK, False, True), (S.ATTACK, True, False),                # attack over ground / structure = move
    (S.SWARM, False, False), (S.PATROL, False, False), (S.DEFEND, True, False), (S.PICKUP, False, False),
    (S.TOWN, False, False), (S.CAST, False, False), (S.DEFAULT, False, False), (S.ARROW_N, False, False),
])
def test_release_dispatch(cursor, hover_unit, cmd):
    oi, _ = make()
    oi.pending = 2
    what, got = oi.release(cursor, (20, 30), hover_unit)
    assert what == "order"
    assert got == (MoveUnits(ME, (10, 11), (20, 30)) if cmd else None)
    assert oi.pending == 0                                           # reset after every dispatch


def test_release_select_cursor_defers_to_selection():
    oi, _ = make()
    oi.pending = 4
    assert oi.release(S.SELECT, (1, 1), True) == ("select", None)
    assert oi.pending == 0


def test_no_order_without_own_selection_or_cell():
    oi, box = make(state="foreign")
    assert oi.release(S.MOVE, (1, 1), False) == ("order", None)
    oi, box = make()
    assert oi.release(S.MOVE, None, False) == ("order", None)


def test_click_vs_drag_and_empty_selection():
    oi, box = make()
    assert oi.is_order_click((50, 50), (60, 50)) and not oi.is_order_click((50, 50), (61, 50))
    assert not oi.is_order_click(None, (60, 50))
    box["sel"] = ()
    assert not oi.is_order_click((50, 50), (50, 50))                  # nothing selected: select path


def test_target_cell_formula():
    assert target_cell(0, 10, 7) == (10, 7) and target_cell(63, 10, 7) == (11, 7) and target_cell(64, 10, 7) == (12, 7)


def test_hotkeys_arm_modes_and_t_stops():
    oi, box = make()
    for k, mode in (("m", 2), ("a", 1), ("d", 4), ("s", 6)):
        assert oi.key(k) == (None, None) and oi.pending == mode
    assert oi.key("t") == (Stop(ME, (10, 11)), None) and oi.pending == 0
    assert oi.key("x") == (None, None)
    box["state"] = "foreign"
    assert oi.key("m") == (None, None) and oi.pending == 0            # gated by an own selection
    box["state"], box["sel"] = "none", ()
    assert oi.key("a") == (None, None) and oi.pending == 0


def test_ctrl_f_cycles_formation_without_selection():
    oi, box = make(sel=(), state="none", formation=1)
    assert [oi.key("f", ctrl=True) for _ in range(3)] == [
        (SetFormation(ME, 2), 2), (SetFormation(ME, 0), 0), (SetFormation(ME, 1), 1)]
    assert oi.key("m", ctrl=True) == (None, None)


def test_pending_clears_when_selection_dies():
    oi, box = make()
    oi.update()
    oi.pending = 2
    box["sel"] = ()
    oi.update()
    assert oi.pending == 0


def test_right_button():
    oi, _ = make()
    assert oi.right_release() == SelectUnits(ME, ())                  # plain right click deselects
    oi.pending = 1
    assert oi.right_release() is None and oi.pending == 0             # cancels the mode, keeps the selection
    assert oi.right_release() == SelectUnits(ME, ())                  # click again clears
    oi.pending = 1
    assert oi.right_move(16, -8) == (2, -1)
    assert oi.right_release() is None and oi.pending == 1             # a drag neither cancels nor deselects
    assert oi.right_release() is None                                 # (pending kept: cancel needs a clean click)
    assert oi.pending == 0


@pytest.mark.parametrize("d,cells", [(0, 0), (7, 0), (8, 1), (15, 1), (16, 2), (-7, 0), (-8, -1), (-15, -1), (-16, -2)])
def test_right_drag_truncates_toward_zero(d, cells):
    assert right_drag_cells(d) == cells


def test_minimap_left():
    oi, box = make()
    assert oi.minimap_left((40, 50)) == ("order", MoveUnits(ME, (10, 11), (40, 50)))
    oi.pending = 1                                                   # attack/swarm: nothing issued yet, mode reset
    assert oi.minimap_left((40, 50)) == ("order", None) and oi.pending == 0
    oi.pending = 2
    assert oi.minimap_left((41, 50))[1] == MoveUnits(ME, (10, 11), (41, 50)) and oi.pending == 0
    box["state"] = "foreign"
    assert oi.minimap_left((40, 50)) == ("camera", None)
    box["state"], box["sel"] = "none", ()
    assert oi.minimap_left((40, 50)) == ("camera", None)


def test_minimap_order_cell_is_the_image_cell():
    g = MinimapGeometry(144, 144)                                    # k = 0: one pixel per cell
    p = MinimapPanel(g, 500, 10)
    assert p.order_cell(500, 10) == (8, 8) and p.order_cell(510, 25) == (18, 23)
    g2 = MinimapGeometry(256, 256)                                   # k = -1: two cells per pixel
    p2 = MinimapPanel(g2, 0, 0)
    assert p2.order_cell(10, 20) == (28, 48)
    g3 = MinimapGeometry(48, 48)                                     # k = 2
    assert MinimapPanel(g3, 0, 0).order_cell(9, 4) == (10, 9)


# --- "No way" message -----------------------------------------------------------------------------------------

def text():
    return MainText(["x"] * 0x81 + ["No way"])


def test_message_lifetime():
    m = MessageLine()
    m.show("No way", 1000, NO_WAY_MS)
    assert m.current(1000) == "No way" and m.current(3999) == "No way" and m.current(4000) is None
    m.show("", 5000, 100)                                             # empty text (missing main.txt) shows nothing
    assert m.current(5000) is None


def test_no_way_drain():
    w = World(np.zeros((16, 16), np.uint16), np.zeros((16, 16), np.int8), "syn")
    w.events.extend([NoWay(2, 5), NoWay(ME, 6), "other"])
    m = MessageLine()
    assert drain_no_way(w, ME, m, 100, text())
    assert m.current(100) == "No way" and m.current(3099) == "No way" and m.current(3100) is None
    assert w.events == ["other"]                                      # NoWay consumed, other events kept
    m2 = MessageLine()
    w.events.append(NoWay(2, 9))
    assert not drain_no_way(w, ME, m2, 0, text()) and m2.current(0) is None and w.events == ["other"]


def test_sim_no_way_reaches_the_ui():
    from engine.sim import MoveUnits as MU
    w = World(np.zeros((32, 32), np.uint16), np.zeros((32, 32), np.int8), "syn")
    w.events.append(NoWay(ME, 0))
    m = MessageLine()
    drain_no_way(w, ME, m, 0, text())
    assert m.current(10) == "No way"


# --- headless scripted sequence on a real map -----------------------------------------------------------------

@needs_graphics
def test_scripted_click_orders_a_walk():
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    pygame = pytest.importorskip("pygame")
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.backend_pygame import window
    from engine.view import Camera, DrawOptions, Projection, TerrainView, build_draw_list
    assets = AssetCache(GFS)
    w = World.from_map(open_map("53", GFS), assets)   # the one map with a unit of the human
    u = next(u for u in w.units.values() if u.owner == 1)
    lay = window.Layout.for_size(640, 480)
    v = lay.viewport
    cam = Camera(v.w, v.h, w.width, w.height, u.x * 32 - v.w // 2, u.y * 32 - v.h // 2, border=256)
    pick = next(r for r in build_draw_list(w, cam, 0, assets, DrawOptions()).picks if r.entity == u.id)
    x, y = (pick.x1 + pick.x2) // 2, (pick.y1 + pick.y2) // 2
    tv = TerrainView(w, assets.tileset())
    ev = pygame.event.Event
    window.ensure_display(*lay.size)
    pygame.event.post(ev(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=1))
    pygame.event.post(ev(pygame.MOUSEBUTTONUP, pos=(x, y), button=1))
    window.run(w, tv, cam, lay, assets=assets, max_frames=8)
    assert w.players[1].selection == (u.id,)
    # second session: click on the ground 96 px right, 64 px down of the unit.  The dummy pointer sits at (0, 0)
    # and edge-scrolls the camera after the first frame, so put it back (events run before the scroll).
    cam.move_to(u.x * 32 - v.w // 2, u.y * 32 - v.h // 2)
    cell, hover = window.click_target(w, cam, lay, build_draw_list(w, cam, 0, assets, DrawOptions()).picks,
                                      (x + 96, y + 64), Projection(w.heights))
    assert not hover and cell is not None
    tx, ty = x + 96, y + 64
    window.ensure_display(*lay.size)
    pygame.event.post(ev(pygame.MOUSEBUTTONDOWN, pos=(tx, ty), button=1))
    pygame.event.post(ev(pygame.MOUSEBUTTONUP, pos=(tx, ty), button=1))
    start = (u.x, u.y, u.sub_x, u.sub_y)
    sim = window.run(w, tv, cam, lay, assets=assets, max_frames=45)
    moves = [c for _, c in sim.log if isinstance(c, MoveUnits)]
    assert moves == [MoveUnits(1, (u.id,), cell)]
    assert (u.x, u.y, u.sub_x, u.sub_y) != start and u.order == 1    # walking
    # right click clears the selection (release, no drag)
    window.ensure_display(*lay.size)
    pygame.event.post(ev(pygame.MOUSEBUTTONDOWN, pos=(tx, ty), button=3))
    pygame.event.post(ev(pygame.MOUSEBUTTONUP, pos=(tx, ty), button=3))
    window.run(w, tv, cam, lay, assets=assets, max_frames=8)
    assert w.players[1].selection == ()
