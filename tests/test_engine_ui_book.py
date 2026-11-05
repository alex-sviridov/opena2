"""The spell book window (ui-layout 11.12, `FUN_004c61e7`): geometry and hit test per mode, the enable / select / deselect rules, the double-click cast, open / close
rules, the per-slot tables and the tooltip gate.  Synthetic (no install except the drawing test), always run; every rule cites the exe routine."""

import pytest

from engine.sim import CastSpell
from engine.ui import GameUi, Layout, MainText, OrderInput, Rect
from engine.ui import book as bk
from engine.ui import spellbook as sb
from engine.ui.orders import CAST
from helpers import GFS, needs_data
from spell_helpers import full_table
from test_engine_ai_casting import monster, world as cast_world

LAYOUTS = {s: Layout.for_size(*s) for s in ((640, 480), (800, 600), (1024, 768))}
L640 = LAYOUTS[(640, 480)]


def bits(*ns):
    return sum(1 << n for n in ns)


def orders(mask=0, item=0, sel=(0x6001,), state="own"):
    box = {"mask": mask, "item": item}
    o = OrderInput(1, 640, lambda: sel, lambda: state, mask_fn=lambda: box["mask"], item_mask_fn=lambda: box["item"])
    return o, box


def window(size=(640, 480), mask=0, item=0, sel=(0x6001,), state="own"):
    w = bk.SpellBookWindow(LAYOUTS[size])
    o, box = orders(mask, item, sel, state)
    o.book = w
    return w, o, box


def centre(w, slot):
    r = w.tile_rect(slot)
    return r.x + 10, r.y + 10


# --- geometry ---------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("size,left", [((640, 480), 0), ((800, 600), 80), ((1024, 768), 192)])
def test_window_rect_frame_offset_and_caps_per_mode(size, left):
    lay = LAYOUTS[size]
    w, h = size
    assert lay.book_rect() == Rect(0, h - 85, w - 160, 85)             # 0x41af4a: (0, H-0x55, W-160, H)
    assert bk.frame_dx(lay) == left                                       # DAT_00621420 = (W - 640) / 2
    assert bk.caps(lay) == {(640, 480): None, (800, 600): ("spb800l", "spb800r"), (1024, 768): ("spb1024l", "spb1024r")}[size]
    if left:                                                              # left cap 80 / 192 wide, right cap from frame + 464 to the window's end (96 / 208 wide)
        assert left + bk.FRAME_W - bk.CAP_OVERLAP + {80: 96, 192: 208}[left] == w - 160


def test_the_book_stacks_above_an_open_inventory():
    lay = L640
    assert lay.book_rect(False).y == 480 - 85 and lay.book_rect(True).y == 480 - 0xAF       # 0x41af4a: H-0xaf .. H-0x5a (the inventory is 90 high)
    assert lay.book_rect(True).bottom == 480 - 0x5A


def test_tiles_are_36_px_on_a_38_px_pitch_from_6_6():
    w, _, _ = window()
    r = w.rect
    assert w.tile_rect(0) == Rect(r.x + 6, r.y + 6, 36, 36)
    assert w.tile_rect(13) == Rect(r.x + 6 + 38, r.y + 6 + 38, 36, 36)                   # slot 13 = column 1 of row 1
    assert w.tile_rect(11) == Rect(r.x + 6 + 11 * 38, r.y + 6, 36, 36)
    w8, _, _ = window((800, 600))
    assert w8.tile_rect(0).x == 80 + 6                                                       # the frame is centred: 80 px of left cap


def test_hit_test_cells_start_5_px_in_and_span_38_px_x_12_by_75_px():
    w, _, _ = window()
    r = w.rect
    at = lambda x, y: w.slot_at((r.x + x, r.y + y))
    assert at(5, 5) == 0 and at(42, 42) == 0 and at(43, 5) == 1 and at(5, 43) == 12           # FUN_004c6fe0: cell = (y / 38) * 12 + x / 38 after (-5, -5)
    assert at(4, 10) == -1 and at(10, 4) == -1                                                # left of / above the first cell
    assert at(5 + 12 * 38 - 1, 5) == 11 and at(5 + 12 * 38, 5) == -1                          # x < 0x1c8
    assert at(5, 5 + 75 - 1) == 12 and at(5, 5 + 75) == -1                                    # y < 0x4b: only two rows
    assert at(41, 41) == 0 and at(42, 41) == 0                                                # the 2 px gap between the tiles belongs to the left cell


@pytest.mark.parametrize("size", [(800, 600), (1024, 768)])
def test_hit_test_follows_the_centred_frame(size):
    w, _, _ = window(size)
    r = w.rect
    dx = bk.frame_dx(w.layout)
    assert w.slot_at((r.x + dx + 5, r.y + 5)) == 0 and w.slot_at((r.x + dx + 4, r.y + 5)) == -1 and w.slot_at((r.x + 4, r.y + 5)) == -1


# --- enable, select, deselect ------------------------------------------------------------------------------------------------

def test_a_click_selects_only_an_enabled_slot_and_the_scroll_mask_counts():
    w, o, box = window(mask=bits(0, 12), item=bits(5))
    assert w.left_down(centre(w, 3), o) is True and o.slot == -1                              # disabled: consumed, nothing selected (0x4c7580)
    w.left_down(centre(w, 12), o)
    assert o.slot == 12
    w.left_down(centre(w, 3), o)
    assert o.slot == 12                                                                       # a refused click keeps the old selection
    w.left_down(centre(w, 5), o)
    assert o.slot == 5                                                                        # `view+0x150` (scroll slots) enables it as well
    w.left_down((w.rect.x + 1, w.rect.y + 1), o)
    assert o.slot == 5                                                                        # outside the grid: nothing


def test_right_press_deselects_and_is_consumed_the_release_changes_nothing_else():
    w, o, _ = window(mask=bits(0))
    w.left_down(centre(w, 0), o)
    assert o.slot == 0 and w.right_down(centre(w, 7), o) is True and o.slot == -1             # 0x4c75e8 / 0x4c7786: +0x60 := -1
    w.right_up()
    assert not w.right_held


def test_moving_with_a_button_held_slides_the_selection():
    w, o, _ = window(mask=bits(0, 1))
    w.open_book()
    w.left_down(centre(w, 0), o)
    w.mouse_move(centre(w, 1), True, False, o)
    assert o.slot == 1                                                                        # 0x4c77a2: flag 1 selects the slot under the pointer
    w.mouse_move(centre(w, 0), False, False, o)
    assert o.slot == 1                                                                        # no button: nothing
    w.right_down(centre(w, 3), o)
    w.left_up()
    o.slot = 1
    w.mouse_move(centre(w, 0), True, True, o)
    assert o.slot == -1                                                                       # right held (flag 2) deselects; the left press had ended


def test_a_move_without_a_press_in_the_window_does_nothing():
    w, o, _ = window(mask=bits(0))
    w.open_book()
    w.mouse_move(centre(w, 0), True, False, o)
    assert o.slot == -1


# --- the per-slot tables (CONFIRMED bytes) ---------------------------------------------------------------------------------------

def test_tables_have_24_entries_and_the_confirmed_slots():
    for t in (sb.UNIT_ONLY, sb.AUTO_CAST, sb.INSTANT):
        assert len(t) == 24 and set(t) <= {0, 1}
    spell = lambda tbl, v: sorted(sb.SLOT_SPELLS[s] for s in range(24) if tbl[s] == v)
    # 0x5f1930: the instant (self) casts: protections 4, 8, 13, 19, Heal 24, Bless 20, Haste 21, Invisibility 12, Summon 25, Shield 27
    assert spell(sb.INSTANT, 1) == [4, 8, 12, 13, 19, 20, 21, 24, 25, 27]
    # 0x5f1810: the spells that also have a cell form (0): Fire Ball, Wall of Fire, Poison Cloud, Blizzard, Wall of Earth, Control Spirit, Teleport
    assert spell(sb.UNIT_ONLY, 0) == [2, 3, 6, 7, 17, 22, 23]
    assert sb.AUTO_CAST[sb.slot_of_spell(24)] == 1 and sb.AUTO_CAST[sb.slot_of_spell(4)] == 0         # Heal can be the auto-cast spell, a protection cannot


def test_ctrl_a_only_takes_slots_the_table_allows():
    o, _ = orders(mask=bits(*range(24)))
    knows = lambda uid, n: True
    assert o.auto_cast(knows, hover_slot=sb.slot_of_spell(24)) != ()
    assert o.auto_cast(knows, hover_slot=sb.slot_of_spell(4)) == ()                                 # 0x4c74b1 reads 0x5f18d0[slot]


# --- double click: the instant cast -----------------------------------------------------------------------------------------------

def test_double_click_on_an_instant_slot_casts_at_once_on_every_unit_that_has_it_and_selects():
    slot = sb.slot_of_spell(24)                                                                      # Heal
    sel = (0x6001, 0x6002, 0x6003)
    w, o, _ = window(mask=bits(slot), sel=sel)
    knows = lambda uid, n: uid != 0x6002
    cmds = w.double_click(centre(w, slot), o, knows)
    assert cmds == (CastSpell(1, (0x6001,), 24, 0x6001), CastSpell(1, (0x6003,), 24, 0x6003))        # 0x419a54: one message per unit, itself as the target
    assert o.slot == slot


def test_double_click_on_a_targeted_or_disabled_slot_only_selects():
    fire = sb.slot_of_spell(1)
    w, o, _ = window(mask=bits(fire, 3))
    assert w.double_click(centre(w, fire), o, lambda u, n: True) == () and o.slot == fire            # Fire Arrow needs a target: INSTANT is 0
    assert w.double_click(centre(w, 4), o, lambda u, n: True) == () and o.slot == fire               # disabled slot: nothing, selection kept


def test_the_instant_cast_needs_the_unit_mask_and_an_own_selection():
    slot = sb.slot_of_spell(24)
    w, o, _ = window(mask=0, item=bits(slot))                                                          # a scroll-only slot: the scroll branch (backpack) is not built
    assert w.double_click(centre(w, slot), o, lambda u, n: True) == ()
    w, o, _ = window(mask=bits(slot), state="foreign")
    assert w.double_click(centre(w, slot), o, lambda u, n: True) == ()


# --- open and close ---------------------------------------------------------------------------------------------------------------

def test_toggle_message_0x40f():
    w, _, _ = window()
    assert not w.open and not w.contains(centre(w, 0))
    w.toggle()
    assert w.open and w.contains(centre(w, 0))
    w.toggle()
    assert not w.open


def test_c_opens_the_book_with_the_cast_mode_and_leaving_the_mode_closes_it():
    w, o, _ = window(mask=bits(sb.slot_of_spell(1)))
    o.spell_fn = lambda: 1
    o.key("c")
    assert o.pending == CAST and w.open                                       # FUN_00418a02 case 5
    o.key("m")
    assert o.pending != CAST and not w.open                                   # any other mode closes it (0x418a2e)
    o.key("c")
    assert w.open
    o.release(None, None, False)                                              # the left release resets the mode and closes it (0x41791a)
    assert o.pending == 0 and not w.open
    o.key("c")
    assert o.right_release() is None and not w.open and o.pending == 0       # right click: 0x416388 closes it too


def test_a_failed_c_does_not_open_and_f_keys_arm_without_opening():
    w, o, _ = window(mask=0)
    o.key("c")
    assert not w.open and o.pending == 0                                      # no enabled slot: the button is disabled
    slot = sb.slot_of_spell(1)
    o2, _ = orders(mask=bits(slot))
    w2 = bk.SpellBookWindow(L640)
    o2.book = w2
    o2.hotkeys[0] = slot
    o2.fkey(4)
    assert o2.pending == CAST and not w2.open                                 # F-key = FUN_00418a02(9): the switch has no case 9, the book stays closed


def test_opening_by_hand_with_the_cast_mode_armed_by_an_f_key_still_closes_on_release():
    slot = sb.slot_of_spell(1)
    o, _ = orders(mask=bits(slot))
    w = bk.SpellBookWindow(L640)
    o.book = w
    o.hotkeys[0] = slot
    o.fkey(4)
    w.toggle()
    assert w.open and o.pending == CAST
    o.release(None, None, False)
    assert not w.open


def test_the_book_stays_open_when_the_mode_was_never_cast_and_ignores_the_selection():
    w, o, box = window(mask=bits(0))
    w.toggle()
    o.pending = 1                                                              # attack mode armed, then cleared: not the cast mode
    o.pending = 0
    box["mask"] = 0
    assert w.open                                                               # nothing in the exe closes it on a selection change; every slot is just disabled


# --- views --------------------------------------------------------------------------------------------------------------------------

def test_views_enabled_selected_fkey_and_auto():
    w, o, _ = window(mask=bits(0, 2))
    hot = [None] * 9
    hot[0], hot[3], hot[5] = 0, 0, 7                                           # F4 and F7 both on slot 0 (the last wins), F9 on a disabled slot
    v = w.views(bits(0, 2), 0, hot, bits(1, 2))
    assert [x.enabled for x in v][:4] == [True, False, True, False]
    assert v[0].selected and not v[2].selected
    assert v[0].fkey == 7 and v[7].fkey == 0 and v[2].fkey == 0               # F9 -> slot 7 is disabled: no label; slot 0 shows F7 (the last entry)
    assert v[1].auto and v[2].auto and not v[0].auto                          # the "A" label does not need the slot enabled (view+0x14c)
    v = w.views(bits(0), 5, hot, 0)
    assert not any(x.selected for x in v)                                      # a disabled slot is never highlighted


def test_hotkey_of_a_hovered_slot_binds_when_nothing_is_selected():
    slot = sb.slot_of_spell(1)
    o, _ = orders(mask=bits(slot))
    o.fkey(5, ctrl=True, hover_slot=slot)                                      # 0x4c72f5: with Ctrl and +0x60 == -1 the slot under the pointer
    assert o.hotkeys[1] == slot
    o.fkey(6, ctrl=True)                                                       # no selection, no hover: nothing
    assert o.hotkeys[2] is None


# --- GameUi routing --------------------------------------------------------------------------------------------------------------------

def make_ui():
    from test_engine_death import world
    w = world()
    ui = GameUi(L640, w, 1, MainText(["m%02x" % i for i in range(0x100)]), MainText(), MainText())
    return ui, w


def test_the_info_panel_button_and_keys_toggle_the_book():
    ui, _ = make_ui()
    r = ui.layout.info_panel.rect
    assert ui.mouse_down((r.x + 5, r.y + 5)) == (False, None) and not ui.book.open   # the press only returns 1 (`FUN_004aea97`)
    assert ui.info_release((r.x + 5, r.y + 5)) and ui.book.open        # the book button (0,0,28,36) posts 0x40f on the release (`FUN_004aebc8`)
    ui.info_release((r.x + 5, r.y + 5))
    assert not ui.book.open
    assert ui.key("b") and ui.book.open and ui.key("q") and not ui.book.open and ui.key(" ") and ui.book.open


def test_a_press_in_the_open_book_is_consumed_and_a_modal_blocks_it():
    ui, _ = make_ui()
    o, _ = orders(mask=bits(0))
    o.book = ui.book
    assert ui.mouse_down(centre(ui.book, 0), o) == (False, None)              # closed: the press reaches the world
    ui.book.open_book()
    assert ui.mouse_down(centre(ui.book, 0), o) == (True, None) and o.slot == 0
    ui.open_menu()
    o.slot = -1
    assert ui.mouse_down(centre(ui.book, 0), o) == (True, None) and o.slot == -1      # a modal takes every click


def test_the_double_click_message_replaces_the_second_press():
    ui, w = make_ui()
    slot = sb.slot_of_spell(24)
    u = monster(cast_world(), 1, 5, 5, owner=1)
    o, _ = orders(mask=bits(slot), sel=(u.id,))
    o.book = ui.book
    ui.book.open_book()
    ui.knows = lambda uid, n: True
    taken, cmds = ui.mouse_down(centre(ui.book, slot), o, clicks=2)
    assert taken and cmds == (CastSpell(1, (u.id,), 24, u.id),) and o.slot == slot


def test_info_button_tooltip_lines_8_and_9():
    main = MainText(["l%d" % i for i in range(16)])
    assert bk.button_text(False, main) == "l8" and bk.button_text(True, main) == "l9"        # `FUN_004ae232`: Open / Close Spellbook <Q>,<B>


# --- tooltip gate -------------------------------------------------------------------------------------------------------------------

def tip_world():
    w = cast_world()
    w.spell_table = full_table()
    u = monster(w, 1, 6, 5, owner=1, power=40, mind=20)
    u.spellbook = bits(1, 5)
    return w, u


def test_tooltip_only_for_a_unit_slot_never_for_a_scroll_only_or_disabled_slot_or_a_dialog():
    w, u = tip_world()
    win = bk.SpellBookWindow(L640)
    labels = ["L%d" % i for i in range(0x100)]
    mask = sb.selection_slot_mask(w, (u.id,))
    s0, s12, s5 = sb.slot_of_spell(1), sb.slot_of_spell(5), 5
    win.open_book()
    t = lambda slot, m=mask, fz=False: win.tooltip_text(centre(win, slot), w, (u.id,), m, None, labels, fz)
    assert t(s0).startswith("Fire") or "#" in t(s0)
    assert t(s12) != "" and t(s0) != t(s12)
    assert t(s5) == "" and t(s5, mask | (1 << s5)) == ""                       # a slot outside the unit mask has no tooltip (0x4c6290: `+0x148` bit)
    assert t(s0, 0) == ""                                                      # the mask is the unit mask
    assert t(s0, fz=True) == ""                                                # modal windows: no tooltip
    win.close()
    assert t(s0) == ""                                                         # a closed window is not under the pointer


# --- drawing (needs the install) ------------------------------------------------------------------------------------------------------------

@needs_data
def test_draw_book_covers_disabled_tiles_veils_the_selection_and_labels():
    import numpy as np
    import pygame
    from engine.backend_pygame.panels import Panels
    pygame.init()
    lay = LAYOUTS[(800, 600)]
    win = bk.SpellBookWindow(lay)
    win.open_book()
    panels = Panels(GFS, lay)

    def render(views):
        s = pygame.Surface(lay.size)
        panels.draw_book(s, win, views)
        return pygame.surfarray.array3d(s)

    plain = render(win.views(bits(0, 1), -1, (), 0))
    none = render(win.views(0, -1, (), 0))
    tile = lambda a, slot: a[win.tile_rect(slot).x:win.tile_rect(slot).right, win.tile_rect(slot).y:win.tile_rect(slot).bottom]
    assert np.array_equal(tile(plain, 5), tile(none, 5))                                          # slot 5 is disabled in both
    assert not np.array_equal(tile(plain, 0), tile(none, 0))                                       # slot 0 enabled vs covered with SpellBack
    assert np.array_equal(tile(none, 0), tile(none, 20))                                           # every covered tile is the same 36x36 art
    sel = render(win.views(bits(0, 1), 0, (), 0))
    assert not np.array_equal(tile(plain, 0), tile(sel, 0)) and np.array_equal(tile(plain, 1), tile(sel, 1))
    assert (tile(sel, 0).astype(int) >= tile(plain, 0).astype(int) * 3 // 4 - 8).all()               # the veil keeps ~12/16 of the tile and adds a floor
    hot = [0] + [None] * 8
    lab = render(win.views(bits(0, 1), -1, hot, bits(1)))
    assert not np.array_equal(tile(plain, 0), tile(lab, 0)) and not np.array_equal(tile(plain, 1), tile(lab, 1))     # "F4" on slot 0, "A" on slot 1
    r = win.rect
    left_cap = plain[r.x:r.x + 80, r.y:r.bottom]
    assert left_cap.any() and plain[:, :r.y].sum() == 0                                             # caps drawn, nothing above the window
