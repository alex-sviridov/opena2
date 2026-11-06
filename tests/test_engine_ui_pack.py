"""The backpack window (ui-layout 11.13, `FUN_004a2bba`): geometry per mode, the hit tests, the scroll arrows, the pick-up / drop / equip / use rules, the scroll
cast, the F keys, the tooltip texts and the open / close rules.  Synthetic (tests/gear_helpers.py), always run; the drawing test needs the install.  Every rule
cites the exe routine."""

import dataclasses
import os
import sys

import pytest

from allods2.formats import itemdefs as idefs
from allods2.formats import saves as S
from engine.sim import CastScroll, MoveItem, gear
from engine.sim import movement as mv
from engine.sim import spells
from engine.ui import GameUi, Layout, MainText, OrderInput, Rect
from engine.ui import info, pack as pk
from engine.ui.cursor import CursorState
from engine.ui.orders import CAST
from gear_helpers import code_of, item, world_with_hero
from helpers import GFS, needs_data

L = {s: Layout.for_size(*s) for s in ((640, 480), (800, 600), (1024, 768))}
MAIN = MainText(["m%02x" % i for i in range(0x100)])


def hero_world(mage=False, n_items=8):
    w, u = world_with_hero(mage=mage)
    u.stats = dataclasses.replace(u.stats, name="Fighter_Hero")           # `is_hero`: a hero template name
    w.players[1].selection = (u.id,)
    pack = [item("Sword"), item("Buckler"), item("Helm"), item("Potion Healing", count=5), item("Scroll Fire", mods=((41, 1, 50),)), item("Boots"),
            item("Great Sword"), item("Hat")]
    u.pack = tuple(pack[:n_items])
    return w, u


def ui_for(w, size=(640, 480)):
    ui = GameUi(L[size], w, 1, MAIN, MainText(), MainText())
    ui.pack.open_pack()
    ui.sync_pack()
    return ui


def cell_pos(ui, k):
    r = ui.pack.cell_rect(k)
    return r.x + 20, r.y + 20


# --- geometry ----------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("size,cols,pad,tiles", [((640, 480), 5, 0, 0), ((800, 600), 7, 0, 2), ((1024, 768), 9, 32, 4)])
def test_columns_margin_and_frame_slices_per_mode(size, cols, pad, tiles):
    lay = L[size]                                                       # `0x4a2bba`: (W - 160) / 0x50 - 1 columns; `0x4a2cf8`: pad = ((W - 0xf0) % 0x50) / 2
    assert (pk.cols(lay), pk.pad(lay), pk.tiles(lay)) == (cols, pad, tiles)
    p = pk.PackWindow(lay)
    w, h = size
    assert p.rect == Rect(0, h - 90, w - 160, 90)                      # created at (0, view bottom - 0x5a, W - 160, view bottom)
    assert p.cell_rect(0) == Rect(pad + 32, h - 90 + 6, 80, 80) and p.cell_rect(1).x == pad + 32 + 80
    assert p.left_arrow_rect() == Rect(0, h - 90, pad + 32, 90)         # the arrow rects of `0x4a2f10` / `0x4a2f56`
    assert p.right_arrow_rect().x == pad + 32 + cols * 80 and p.right_arrow_rect().w == pad + 32
    assert (pk.caps(lay) is not None) == (size == (1024, 768))          # caps only with a margin and H > 600


def test_frame_blits_left_piece_slices_caps_and_right_end():
    p = pk.PackWindow(L[(640, 480)])
    assert p.frame_blits() == [("InvFrame", 0, 0x110, 0), ("InvFrame", 0x110, None, 272)]       # the right end lands at W - 160 - 480 + 0x110
    p = pk.PackWindow(L[(800, 600)])
    assert [b[1:] for b in p.frame_blits()[:3]] == [(0, 0x110, 0), (0xC0, 0x110, 0x110), (0xC0, 0x110, 0x110 + 0x50)] and p.frame_blits()[-1][3] == 640 - 480 + 0x110
    blits = pk.PackWindow(L[(1024, 768)]).frame_blits()
    assert blits[-3][0] == "inv1024l" and blits[-3][3] == 0 and blits[-2][0] == "inv1024r" and blits[-2][3] == 864 - 32 - 16     # caps before the right end


def test_the_window_exists_only_while_open_and_the_book_stacks_above_it():
    w, _ = hero_world()
    ui = GameUi(L[(640, 480)], w, 1, MAIN, MainText(), MainText())
    assert not ui.pack.contains((100, 440))
    ui.key("i")                                                         # `0x40ccb6`: I toggles message 0x40e
    assert ui.pack.open and ui.pack.contains((100, 440)) and not ui.pack.contains((100, 380))
    ui.book.open_book()
    assert ui.book.rect.y == 480 - 0xAF                                 # `FUN_0041adc2`: the book moves to (H - 0xaf .. H - 0x5a)
    ui.key("`")
    assert not ui.pack.open and ui.book.rect.y == 480 - 85              # `FUN_0041ae4f`: back to the bottom


def test_space_opens_both_bars_when_none_is_open_else_closes_the_open_ones():
    w, _ = hero_world()
    ui = GameUi(L[(640, 480)], w, 1, MAIN, MainText(), MainText())
    ui.key(" ")
    assert ui.pack.open and ui.book.open and ui.book.inventory_open        # `0x40cd6e`
    ui.key(" ")
    assert not ui.pack.open and not ui.book.open
    ui.book.open_book()
    ui.key(" ")
    assert not ui.book.open and not ui.pack.open                         # only the open one closes


def test_the_info_panel_pack_button_toggles_the_window():
    w, _ = hero_world()
    ui = GameUi(L[(640, 480)], w, 1, MAIN, MainText(), MainText())
    r = ui.layout.info_panel.rect
    assert ui.info_release((r.x + 5, r.y + 220)) and ui.pack.open        # the hit rect (0, 202)-(28, 242): message 0x40e, on the release
    ui.info_release((r.x + 5, r.y + 220))
    assert not ui.pack.open


# --- the shown unit and the scroll -------------------------------------------------------------------------------------------------

def test_the_window_shows_the_single_selected_hero_only():
    w, u = hero_world()
    ui = ui_for(w)
    assert ui.pack.unit == u.id                                         # `FUN_004167c2`: count 1 and the hero bit (`+0x144 & 8`) -> list of `view+0x138`
    plain = dataclasses.replace(u.stats, name="Soldier")
    u.stats = plain
    ui.sync_pack()
    assert ui.pack.unit is None
    u.stats = dataclasses.replace(u.stats, name="Fighter_Hero")
    w.players[1].selection = (u.id, 0x9999)
    ui.sync_pack()
    assert ui.pack.unit is None                                         # two selected: `0x94(0)` = no list


def test_without_a_hero_the_window_draws_no_cells_and_says_so():
    w, _ = hero_world()
    w.players[1].selection = ()
    ui = ui_for(w)
    v = ui.pack.views(w)
    assert v.cells == () and v.left is None and v.right is None
    assert ui.pack.tooltip_text(cell_pos(ui, 1), w, MAIN) == "m3a"        # main.txt 0x3a over the cells; 0x33 is the drawn "No hero selected"
    assert pk.T_NO_HERO == 0x33 and pk.T_LEFT == 0x36 and pk.T_RIGHT == 0x37


def test_arrows_scroll_one_item_and_show_only_when_there_is_more():
    w, u = hero_world()                                                 # 8 items, 5 cells
    ui = ui_for(w)
    v = ui.pack.views(w)
    assert [c.pack_index for c in v.cells] == [0, 1, 2, 3, 4] and v.left is None and v.right is not None     # left only with offset != 0, right while the pack goes on
    ui.mouse_down((ui.pack.right_arrow_rect().x + 5, 440))               # `0x4a3706` -> `FUN_004a1a78`: one item
    ui.mouse_down((ui.pack.right_arrow_rect().x + 5, 440))
    ui.mouse_down((ui.pack.right_arrow_rect().x + 5, 440))
    ui.mouse_down((ui.pack.right_arrow_rect().x + 5, 440))               # 8 - 5 = 3 steps at most
    v = ui.pack.views(w)
    assert ui.pack.offset() == 3 and [c.pack_index for c in v.cells] == [3, 4, 5, 6, 7] and v.right is None and v.left is not None
    ui.mouse_down((3, 440))                                              # the left arrow strip: `FUN_004a1bff`
    assert ui.pack.offset() == 2
    ui.pack.offsets[u.id] = 99
    ui.pack.views(w)
    assert ui.pack.offset() == 3                                         # `FUN_004a16d8`: clamped to count - cols


def test_each_hero_keeps_its_own_offset():
    w, u = hero_world()
    ui = ui_for(w)
    ui.pack.offsets[u.id] = 2
    ui.pack.unit = None
    assert ui.pack.offset() == 0
    ui.sync_pack()
    assert ui.pack.offset() == 2                                         # the exe keeps it in the unit (`+0xe4`)


def test_cell_hit_strict_and_lenient():
    w, _ = hero_world()
    ui = ui_for(w)
    p, n = ui.pack, 8
    assert p.index_at((cell_pos(ui, 2)), True, n) == 2 and p.index_at((10, 440), True, n) == -1       # `0x4a35c0` with y < 0: only the cells
    assert p.index_at((10, 440), False, n) == 0                          # a drop left of the first cell = the first shown index
    assert p.index_at((p.right_arrow_rect().x + 3, 440), False, n) == 4  # right of the last cell: the last shown while the pack goes on
    p.offsets[p.unit] = 3
    assert p.index_at((p.right_arrow_rect().x + 3, 440), False, n) == 7 and p.index_at(cell_pos(ui, 4), True, n) == 7
    assert p.index_at(cell_pos(ui, 4), True, 7) == -1                    # an index past the pack is -1


# --- pick up, drop -----------------------------------------------------------------------------------------------------------------

def test_a_left_held_move_over_a_cell_picks_up_one_piece_and_the_pack_shows_it_gone():
    w, u = hero_world()
    ui = ui_for(w)
    assert ui.pack_mouse_move(cell_pos(ui, 3), True)                    # `0x4a3a1d`: MK_LBUTTON, nothing carried
    c = ui.pack.carried
    assert (c.kind, c.index, c.count, c.item.code) == (2, 3, 1, code_of("Potion Healing"))
    assert [c.item.count for c in ui.pack.views(w).cells if c.pack_index == 3] == [4]       # `FUN_004a218b`: the stack loses the piece
    ui.pack.carried = None
    assert ui.pack_mouse_move(cell_pos(ui, 3), True, shift=True) and ui.pack.carried.count == 5      # Shift (`DAT_006227dc`): the whole stack
    assert 3 not in [c.pack_index for c in ui.pack.views(w).cells] or ui.pack.views(w).cells[3].item.code != code_of("Potion Healing")


def test_a_foreign_hero_pack_cannot_be_picked():
    w, u = hero_world()
    u.owner = 2
    ui = ui_for(w)
    assert not ui.pack_mouse_move(cell_pos(ui, 0), True) and ui.pack.carried is None     # `FUN_004a235d`: the hero's owner must be the player


def test_a_release_in_the_window_files_the_item_at_the_index_under_the_pointer():
    w, u = hero_world()
    ui = ui_for(w)
    ui.pack_mouse_move(cell_pos(ui, 0), True)                           # the dagger-like first item
    handled, cmds = ui.item_release(cell_pos(ui, 3))
    assert handled and cmds == (MoveItem(1, u.id, 2, 2, 0, 3, 1),)      # `FUN_004a24e8`: message 0x22 pack -> pack, count = the carried count
    assert ui.pack.carried is None
    ui.pack_mouse_move(cell_pos(ui, 2), True)
    assert ui.item_release(cell_pos(ui, 2)) == (True, ())               # put back where it came from: nothing to send
    assert gear.move_item(w, u, 2, 2, 0, 3, 1) and [i.code for i in u.pack][3] == code_of("Sword")


def test_a_release_left_of_the_cells_files_at_the_first_shown_index():
    w, u = hero_world()
    ui = ui_for(w)
    ui.pack.offsets[u.id] = 2
    ui.pack_mouse_move(cell_pos(ui, 1), True)
    handled, cmds = ui.item_release((5, 440))
    assert cmds == (MoveItem(1, u.id, 2, 2, 3, 2, 1),)


def test_a_release_in_the_map_drops_at_the_heros_feet():
    w, u = hero_world()
    ui = ui_for(w)
    ui.pack_mouse_move(cell_pos(ui, 1), True)
    handled, cmds = ui.item_release((100, 100))                         # `FUN_0040c5d1`: message 0x22 to kind 3 at the hero's cell (x | y << 8)
    assert handled and cmds == (MoveItem(1, u.id, 2, 3, 1, u.x | u.y << 8, 1),)
    gear.move_item(w, u, 2, 3, 1, u.x | u.y << 8, 1)
    assert w.items_at(u.x, u.y) and len(u.pack) == 7


def test_a_release_on_the_command_bar_forgets_the_carried_item_and_on_the_book_puts_it_back():
    w, u = hero_world()
    ui = ui_for(w)
    ui.pack_mouse_move(cell_pos(ui, 1), True)
    bar_pos = (ui.layout.bar_panel.rect.x + 5, ui.layout.bar_panel.rect.y + 5)
    assert ui.item_release(bar_pos) == (True, ()) and ui.pack.carried is None          # `FUN_004adace`: the cursor is dropped, nothing sent
    ui.pack_mouse_move(cell_pos(ui, 1), True)
    ui.book.open_book()
    ui.book.inventory_open = True
    pos = (200, ui.book.rect.y + 20)
    assert ui.item_release(pos) == (True, ()) and ui.pack.carried is None              # `FUN_004c76bc`: back to its place (a pack source: no message needed)


def test_nothing_is_picked_or_released_under_a_modal():
    w, u = hero_world()
    ui = ui_for(w)
    ui.open_menu()
    assert not ui.pack_mouse_move(cell_pos(ui, 0), True)


# --- equip, use, scrolls -----------------------------------------------------------------------------------------------------------

def test_a_double_click_wears_a_weapon_by_the_class_slot():
    w, u = hero_world()
    ui = ui_for(w)
    taken, cmds = ui.mouse_down(cell_pos(ui, 0), clicks=2)               # `0x4a37f3`: one piece picked, then `FUN_004b028d(class - 1)`
    assert taken and cmds == (MoveItem(1, u.id, 2, 1, 0, 1, 1),)         # dst kind 1 (slot), dst index = class (param + 1), count 1
    assert ui.pack.carried is None
    assert gear.move_item(w, u, 2, 1, 0, 1, 1) and gear.slots_of(u)[1].code == code_of("Sword")


def test_a_release_on_the_info_panel_equips_or_uses_the_carried_item():
    w, u = hero_world()
    ui = ui_for(w)
    ui.pack_mouse_move(cell_pos(ui, 1), True)                            # the buckler: class 2
    r = ui.layout.info_panel.rect
    handled, cmds = ui.item_release((r.x + 40, r.y + 100))               # `FUN_004aebc8` -> `FUN_004b028d(2 - 1)`
    assert handled and cmds == (MoveItem(1, u.id, 2, 1, 1, 2, 1),)
    ui.pack_mouse_move(cell_pos(ui, 3), True, shift=True)                # a stack of 5 potions: one piece is used, the rest goes back
    handled, cmds = ui.item_release((r.x + 40, r.y + 100))
    assert cmds == (MoveItem(1, u.id, 2, 1, 3, 14, 1),) and ui.pack.carried is None


def test_an_unusable_item_goes_back_to_the_pack():
    w, u = hero_world(mage=True)                                          # a mage: the sword is fighter-only (`FUN_0046a9c2`)
    ui = ui_for(w)
    r = ui.layout.info_panel.rect
    ui.pack_mouse_move(cell_pos(ui, 0), True)
    assert ui.item_release((r.x + 40, r.y + 100)) == (True, ()) and ui.pack.carried is None
    u.pack = (item("Quest Key"),)                                         # a quest item (flag 1 only) is refused for everybody
    ui.pack.pick(cell_pos(ui, 0), w, 1)
    assert ui.pack.equip_carried(w, 1) == () and ui.pack.carried is None


def test_flags_of_items_follow_the_wire_flag_byte():
    t = world_with_hero()[0].item_table
    assert pk.item_flags(t, item("Sword")) == 2 and pk.item_flags(t, item("Staff")) == 4 and pk.item_flags(t, item("Buckler")) == 6
    assert pk.item_flags(t, item("Potion Healing")) == 7 and pk.item_flags(t, item("Scroll Fire")) == 0x17 and pk.item_flags(t, item("Quest Key")) == 1
    assert pk.usable_by(2, False) and not pk.usable_by(2, True) and pk.usable_by(4, True) and not pk.usable_by(1, False)


def test_a_book_the_mage_knows_or_a_fighter_cannot_read_is_refused():
    w, u = hero_world(mage=True)
    book = S.Item(0xE01, 1, 0, ((42, 3, 0),))
    assert pk.teach_spell(book) == 3 and pk.teach_spell(item("Sword")) == 0
    assert pk.scroll_spell(item("Scroll Fire", mods=((41, 1, 50),))) == 1 and pk.scroll_spell(item("Sword")) == 0


def test_a_scroll_released_on_the_info_panel_selects_the_cast_item_and_the_cast_sends_cast_scroll():
    w, u = hero_world(mage=True)
    ui = ui_for(w)
    o = OrderInput(1, 640, lambda: (u.id,), lambda: "own")
    r = ui.layout.info_panel.rect
    ui.pack_mouse_move(cell_pos(ui, 4), True)
    handled, cmds = ui.item_release((r.x + 40, r.y + 100), o)           # `FUN_004b028d` scroll branch: back into the pack, `FUN_004c7143`, `FUN_00418a02(10)`
    assert handled and cmds == () and ui.pack.carried is None
    assert o.pending == CAST and o.scroll == 4 and o.spell == 1 and o.scroll_unit == u.id
    cmd = o.release(CursorState.CAST, (5, 5), 0x6002)[1]
    assert cmd == CastScroll(1, u.id, 4, target_id=0x6002) and o.pending == 0 and o.scroll == -1     # the mode ends: `FUN_004c7287` clears both


def test_a_scroll_double_click_arms_the_scroll_cast():
    w, u = hero_world(mage=True)
    ui = ui_for(w)
    o = OrderInput(1, 640, lambda: (u.id,), lambda: "own")
    assert ui.mouse_down(cell_pos(ui, 4), o, False, 2) == (True, ())
    assert o.scroll == 4 and o.pending == CAST
    o.pending = 0
    assert o.scroll == -1                                                 # leaving the cast mode forgets the scroll


def test_a_foreign_selection_cannot_arm_a_scroll():
    w, u = hero_world(mage=True)
    o = OrderInput(1, 640, lambda: (u.id,), lambda: "foreign")
    assert not o.select_scroll(0, 1, u.id) and o.pending == 0


# --- the paper doll slots ----------------------------------------------------------------------------------------------------------

def test_a_picked_up_equipment_slot_is_released_into_the_pack_by_a_double_click():
    w, u = hero_world()
    u.equipment = tuple(S.Item(code_of("Sword"), 1) if i == 0 else gear.EMPTY for i in range(12))
    ui = ui_for(w)
    assert ui.pack.pick_equipped(w, 1, 0) and ui.pack.carried.kind == 1 and ui.pack.carried.item.code == code_of("Sword")
    handled, cmds = ui.item_release(cell_pos(ui, 2))
    assert cmds == (MoveItem(1, u.id, 1, 2, 0, 2, 1),)                    # slot 1 -> the pack at the index under the pointer
    assert ui.pack.unequip(w, 1, 0) == (MoveItem(1, u.id, 1, 2, 0, gear.APPEND, 1),)
    assert gear.move_item(w, u, 1, 2, 0, gear.APPEND, 1) and not gear.slots_of(u)


def test_the_doll_hit_mask_layers_and_ids():
    w, u = hero_world()
    u.equipment = tuple(S.Item(code_of(n), 1) if n else gear.EMPTY for n in ("Sword", "Buckler", "", "Helm", "", "", "", "", "Boots", "", "", ""))
    layers = info.doll_mask_layers(w, u)
    # paperdoll.md 4: a fighter's mask list has no body: P3 P8 P0 S3 S8 P1 of the items present, each writing slot + 1
    assert [i for _, i in layers] == [4, 9, 1, 4, 9, 2]
    assert layers[0][0].startswith("graphics/equipment/mfighter/primary/") and layers[3][0].startswith("graphics/equipment/mfighter/secondary/")
    w2, m = hero_world(mage=True)
    m.equipment = tuple(S.Item(code_of(n), 1) if n else gear.EMPTY for n in ("Staff", "", "", "Helm", "", "", "", "", "", "", "", ""))
    ids = [i for _, i in info.doll_mask_layers(w2, m)]
    assert ids[:3] == [0, 4, 4] or 0 in ids                                  # the mage list has the body (id 0, `<face>.256`): it clears what lies under it


def test_the_doll_slot_comes_from_the_mask_in_picture_mode_only():
    import numpy as np
    w, u = hero_world()
    ui = ui_for(w)
    mask = np.zeros((240, 160), np.uint8)
    mask[100:110, 20:30] = 4
    ui.doll_mask = lambda unit: mask
    r = ui.layout.info_panel.rect
    assert ui.doll_slot_at((r.x + 25, r.y + 2 + 105)) == 3                # `FUN_004aeabb`: the byte at ((y - top - 2) * 160 + x - left), id - 1
    assert ui.doll_slot_at((r.x + 5, r.y + 2 + 5)) == -1
    ui.toggle_mode()
    assert ui.doll_slot_at((r.x + 25, r.y + 2 + 105)) == -1


# --- the F keys, the tooltip -------------------------------------------------------------------------------------------------------

def test_ctrl_f_over_a_cell_binds_the_item_and_f_uses_it():
    w, u = hero_world()
    ui = ui_for(w)
    assert ui.pack.bind_key(5, cell_pos(ui, 3), w) and ui.pack.item_keys[1] == (code_of("Potion Healing"), ())
    assert [c.key for c in ui.pack.views(w).cells] == [0, 0, 0, 5, 0]    # the "F5" label of the cell
    assert ui.pack.bind_key(6, cell_pos(ui, 3), w) and ui.pack.item_keys[1] is None and ui.pack.item_keys[2] is not None      # the key is cleared where the same item sits
    assert ui.pack.use_key(6, w, 1) == (MoveItem(1, u.id, 2, 1, 3, 14, 1),)
    assert not ui.pack.bind_key(4, (5, 5), w)


def test_tooltip_texts_follow_the_pointer():
    w, u = hero_world(n_items=3)
    w.item_table.names[code_of("Sword")] = "Sword"                      # the synthetic table has no itemname.txt
    ui = ui_for(w)
    t = lambda pos: ui.pack.tooltip_text(pos, w, MAIN)
    assert t((5, 440)) == "m36" and t((ui.pack.right_arrow_rect().x + 5, 440)) == "m37"      # `FUN_004a3f0b`: 0x36 / 0x37 over the arrow strips
    assert t(cell_pos(ui, 4)) == "m3a" and t(cell_pos(ui, 0)) == "Sword"                       # 0x3a over an empty cell, else the item
    assert ui.pack.tooltip_text(cell_pos(ui, 0), w, MAIN, frozen=True) == ""
    ui.pack_mouse_move(cell_pos(ui, 0), True)
    assert t(cell_pos(ui, 1)) == ""                                      # nothing while an item is carried
    assert pk.button_text(False, MAIN) == "m0a" and pk.button_text(True, MAIN) == "m0b"       # the info panel's pack button: main.txt 0xa / 0xb


# --- the item tooltip rows (`FUN_0043901f`), the weapon-swap lock (`+0x78` in {3, 7, 8}), the "new" twinkle (`FUN_004a285a`) ----------------------------------

STATS = {13: "Damage", 15: "Defense", 38: "Range", 8: "Health Regeneration", 12: "Attack", 44: "Fire Damage"}


def tip_world(payload, n, code=0x1102, name="Dagger", special=False):
    """A synthetic world whose table holds one `itemname.pkt` descriptor (header `1, 0, flags, n`) and the stat names."""
    w, u = hero_world(n_items=1)
    t = w.item_table
    t.packets = {code: idefs.Packet(code, bytes((1, 0, 2, n)), 0, (), bytes(payload))}
    t.names[code] = name
    t.stat_texts = [STATS.get(i, "") for i in range(60)]
    return w, S.Item(code, 1)


def test_tooltip_rows_follow_the_payload_tags():
    price = bytes((1, 0x19, 0, 0, 0))
    # damage pair (13, 3) (14, 1) = `#Damage 3-4` (two entries), a stat `%+d`, a range `%d`
    w, it = tip_world(price + bytes((13, 3, 14, 1, 12, 10, 38, 2)), 5)
    assert pk.item_name(w, it, MAIN) == "Dagger#Damage 3-4#Attack +10#Range 2"
    w, it = tip_world(price + bytes((15, 5, 8, 100)), 3)
    assert pk.item_name(w, it, MAIN) == "Dagger#Defense +5#Health Regeneration +100%"       # a `%` follows the tags 8 and 11
    w, it = tip_world(price + bytes((0x33, 0)), 2)
    assert pk.item_name(w, it, MAIN) == "Dagger#m" + "bd"                                      # a non-special item with the marker: the main.txt 0xbd row
    w, it = tip_world(price, 1)
    assert pk.item_name(w, it, MAIN) == "Dagger"


def test_tooltip_rows_of_the_wire_modifiers():
    w, it = tip_world(bytes((1, 0, 0, 0, 0, 13, 3, 14, 1)), 3)
    it = S.Item(it.code, 1, 0, ((15, 2, 0), (44, 3, 4)))             # `FUN_004387b2`: template payload + `33 00` + (kind, value) entries, two for element damage
    assert pk.item_name(w, it, MAIN) == "Dagger#Damage 3-4#mbd#Defense +2#Fire Damage 3-7"


def test_a_book_and_a_scroll_name_their_spell():
    w, _ = tip_world(bytes((1, 0, 0, 0, 0, 0x2A, 5)), 2, code=0xE01, name="Book")
    w.item_table.spells = (("A", 0, 0),) * 4 + (("Haste", 0, 0),)
    assert pk.item_name(w, S.Item(0xE01, 1), MAIN) == "Book m5a Haste" + "m5b"                # the 0x2a tag: " %s %s%s" with main.txt 0x5a / 0x5b


def test_weapon_swap_lock_while_the_hero_swings():
    w, u = hero_world()
    ui = ui_for(w)
    sword = cell_pos(ui, 0)
    u.action, u.state = mv.ATTACK, mv.ATTACK_STATE
    assert pk.swing_locked(u)
    assert not ui.pack.pick(sword, w, 1)                                  # `FUN_004a235d`: item class < 2 while `+0x78` is 3 / 7 / 8
    assert ui.pack.pick(cell_pos(ui, 3), w, 1)                           # a potion is free
    ui.pack.cancel_carry()
    assert not ui.pack.pick_equipped(w, 1, 0) and not ui.pack.pick_equipped(w, 1, 1)      # `FUN_004b012f`: slots 0 and 1
    u.action, u.state = mv.IDLE, 0
    assert not pk.swing_locked(u) and ui.pack.pick(sword, w, 1)
    u.action, u.state = mv.ATTACK, spells.CAST_STATE                    # casting locks too
    cmds = ui.pack.equip_carried(w, 1)                                    # `FUN_004b028d`: slot < 2 while locked -> the item goes back to the pack
    assert cmds == () and ui.pack.carried is None                       # back to its own pack place: no move
    u.action, u.state = mv.IDLE, 0
    assert ui.pack.pick(sword, w, 1)
    assert [c.dst_kind for c in ui.pack.equip_carried(w, 1)] == [gear.KIND_SLOT]


def test_twinkle_trail_and_blob():
    table = pk.twinkle_table()
    assert len(table[0]) == len(table[1]) == 0x400 and all(8 <= v <= 8 + 0x7FFF // 0x1FF for v in table[0] + table[1])
    px = pk.twinkle_pixels(0, table)
    assert len(px) == 13 and max(a for _, _, a in px) == 0x3F and px[0][2] == 0x3F       # counter 0: the head only, alpha 0x3f, 13 blob points
    full = pk.twinkle_pixels(2 * 6, table)
    assert len(full) == 7 * 13 and [a for _, _, a in full[::13]] == [0x3F, 0x7F, 0xBF, 0xFF, 0xBF, 0x7F, 0x3F]
    assert pk.twinkle_pixels(2 * 0x400, table)[0][:2] == pk.twinkle_pixels(0, table)[0][:2]      # the index wraps at 0x400


@needs_data
def test_real_tooltips_against_the_install():
    from allods2.assets import AssetCache
    from allods2.formats import itemdefs as ii
    from allods2.common import game_fs
    import types
    fs = game_fs()
    a = AssetCache(fs)
    w = types.SimpleNamespace(item_table=a.items(), spell_table=a.spells())
    lines = ii.decode_text(fs.read("main/text/main.txt")).split("\r\n")
    main = types.SimpleNamespace(line=lambda i: lines[i])
    assert pk.item_name(w, S.Item(0x1102, 1), main) == "Bronze Dagger#Damage 3-4#Attack +10"
    assert pk.item_name(w, S.Item(0xE45, 1), main) == "Potion of Health Regeneration#Health Regeneration +100%"
    assert pk.item_name(w, S.Item(0xE06, 1), main) == "Scroll of Fire Arrow#Damage: 13-26#Range: 8"


# --- drawing against the install ---------------------------------------------------------------------------------------------------

@needs_data
def test_the_hit_mask_writes_the_layer_id_over_the_covered_pixels():
    from allods2.common import game_fs
    from allods2.graphics import paperdoll
    fs = game_fs()
    m = paperdoll.hit_mask([("graphics/equipment/mfighter/primary/0001008.256", 3), ("graphics/equipment/mfighter/primary/missing.256", 5)], fs)
    assert m.shape == (240, 160) and set(m.flatten().tolist()) <= {0, 3} and (m == 3).any()       # a missing file covers nothing
