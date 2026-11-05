"""J1 widget table and command bar (docs/engine/ui-layout.md 11.1, 11.2, 11.6): rect rules, cell states, hit tests.  Synthetic, always run."""

import pytest

from engine.ui import Layout, OrderInput, bar
from engine.ui.widgets import (BUTTON_PITCH, DIALOG_SIZE, INFO_BUTTONS, WIDGETS, button_rect, cell_rect, centred, complete_window, failed_window, info_button_rect, origin, snap_dialog,
                               text_window, text_window_buttons, widget_rect)


@pytest.mark.parametrize("size", Layout.SIZES)
def test_panel_origins_follow_the_resolution(size):
    lay = Layout.for_size(*size)
    w, h = size
    assert origin(lay, "P") == (w - 160, 238) and origin(lay, "B") == (w - 160, 158) and origin(lay, "V") == (0, 0)
    assert origin(lay, "menu") == ((w - 296) // 2, (h - 296) // 2)               # dialogs are centred on the SCREEN (`FUN_004dc4fc`)
    r = widget_rect(lay, "info.back")
    assert (r.x, r.y, r.w, r.h) == (w - 160, 238, 160, 242)
    assert widget_rect(lay, "bar.back").h == 80 and widget_rect(lay, "info.portrait").y == 240


def test_dialog_sizes_snap_to_0x60_by_0x40_steps():
    assert snap_dialog(340, 340) == (296, 296) and snap_dialog(340, 240) == (296, 232)           # menu, End Quest (`FUN_004dc4fc`)
    assert snap_dialog(576, 384) == (488, 360) and snap_dialog(580, 240) == (488, 232)           # pause (first snap), story
    assert snap_dialog(384, 180) == (296, 168) and snap_dialog(488, 217) == (488, 168)           # complete window; the pause height after the text rule


@pytest.mark.parametrize("size", Layout.SIZES)
def test_every_fixed_dialog_is_centred_on_the_screen(size):
    lay = Layout.for_size(*size)
    sw, sh = size
    for name in ("menu", "endquest", "story"):
        f = widget_rect(lay, name + ".frame")
        assert (f.w, f.h) == DIALOG_SIZE[name] and f.x == (sw - f.w) >> 1 and f.y == (sh - f.h) >> 1
    s = widget_rect(lay, "story.frame")
    ok = widget_rect(lay, "story.ok")
    assert (ok.x - s.x, ok.y - s.y, ok.w, ok.h) == (200, 172, 80, 26)
    assert centred(lay, 488, 168) == ((sw - 488) >> 1, (sh - 168) >> 1)
    for w in WIDGETS.values():
        assert (w.origin in ("P", "B", "V", "S") or w.origin in DIALOG_SIZE) and len(w.rect) == 4


def test_text_window_height_rule_of_0x443238():
    """`b = t + 0x90 + text widget bottom`, bottom = 0x38 (0x44 with a caption) + 17 per wrapped line (font1 height 15 + 2), then `FUN_004dc4fc` again."""
    one = text_window((576, 384), 1, False, 1)
    assert (one.w, one.h, one.text, one.caption) == (488, 168, (0x28, 0x38, 408, 17), None)         # the Pause notice at one line
    assert one.buttons == ((488 // 2 - 0x30, 168 - 0x3C, 96, 24),)                               # case 0: 96 x 24 centred, y h - 0x3c
    assert [text_window((576, 384), n, False, 1).h for n in range(16)] == [168, 168, 232, 232, 232, 232, 296, 296, 296, 296, 360, 360, 360, 360, 424, 360]    # 0x90 + 0x38 + 17 n snapped; 15: scroll
    cap = text_window((576, 384), 1, True, 1)
    assert cap.text[1] == 0x44 and cap.caption == (0x28, 0x30, 408, 16)                          # OffsetRect(0, 0xc) before the caption widget (`0x443510`)
    assert text_window((576, 384), lambda width: 1 if width == 408 else 99, False, 1).h == 168       # the line count is asked with the text width w' - 0x50
    big = text_window((576, 384), 15, False, 1)                                                    # 15 * 15 > 216: the widget keeps its rect and gets a scroll bar
    assert big.scroll and big.h == 360 and big.text[3] == 360 - 0x58 - 0x38
    assert not text_window((576, 384), 14, False, 1).scroll and text_window((576, 384), 14, False, 1).h == 424


def test_text_window_button_cases():
    w = 488
    assert text_window_buttons(w, 168, 2) == [(w // 7, 108, 3 * w // 7 - w // 7, 24), (4 * w // 7, 108, 6 * w // 7 - 4 * w // 7, 24)]
    assert [(x, x + ww) for x, _, ww, _ in text_window_buttons(w, 168, 3)] == [(3 * w // 20, 7 * w // 20), (8 * w // 20, 12 * w // 20), (13 * w // 20, 17 * w // 20)]


def test_failed_window_adds_0x40_without_a_new_snap_and_stacks_its_two_buttons():
    f = failed_window((576, 280), 0)
    assert (f.w, f.h, f.place_h) == (488, 232, 168)                                                # text window (168) + 0x40 (`FUN_0044d237` 0x44d263)
    assert f.buttons == ((61, 232 - 0x60, 366, 24), (61, 232 - 0x48, 366, 24))                     # w/8 .. 7w/8; `0x44d2b7` / `0x44d30a`
    assert f.caption == (0x28, 0x30, 408, 16) and f.text[1] == 0x44


def test_complete_window_is_the_menu_class_dialog_296_by_168():
    c = complete_window()
    assert (c.w, c.h) == (296, 168) and c.text == (0x28, 0x20, 0xC0, 0x30)
    assert c.buttons == ((0x28, 84, 208, 24), (0x28, 108, 208, 24))                                # stack top `h - 0x60` of the rect argument, 24 px each


def test_menu_button_rule_is_x_28_to_width_minus_30_with_pitch_1e_from_y_28():
    lay = Layout.for_size(640, 480)
    f = widget_rect(lay, "menu.frame")
    b0, b1 = button_rect(f, 0), button_rect(f, 1)
    assert b0.x == f.x + 0x28 and b0.right == f.right - 0x30 and b0.y == f.y + 0x28            # CONFIRMED `0x4400d7` rect arg (0, 0, 0xf0, 0x28)
    assert b1.y - b0.y == BUTTON_PITCH == 0x1E and b0.h == 0x1E
    assert button_rect(f, 6).bottom <= f.bottom                                  # the 7 single-player entries fit


@pytest.mark.parametrize("size", Layout.SIZES)
def test_info_button_hit_rects(size):
    lay = Layout.for_size(*size)
    px, py = origin(lay, "P")
    assert info_button_rect(lay, "book").contains(px, py + 36) is False and info_button_rect(lay, "book").contains(px + 27, py + 35)
    assert info_button_rect(lay, "mode").contains(px + 0x80, py) and info_button_rect(lay, "mode").contains(px + 159, py + 35)
    assert info_button_rect(lay, "pack").contains(px, py + 202) and info_button_rect(lay, "pack").contains(px + 27, py + 241)
    m = info_button_rect(lay, "menu")
    assert (m.x - px, m.y - py, m.right - px, m.bottom - py) == (0x7E, 0xCE, 0x9E, 0xEE)
    assert INFO_BUTTONS["menu"][0] == (0x7E, 0xCE)


def test_command_cells_are_34_px_cells_at_8_7():
    lay = Layout.for_size(640, 480)
    assert (cell_rect(lay, 0).x, cell_rect(lay, 0).y) == (480 + 8, 158 + 7)
    assert (cell_rect(lay, 5).x, cell_rect(lay, 5).y) == (480 + 8 + 34, 158 + 7 + 34)
    assert cell_rect(lay, 3).x == 480 + 8 + 3 * 34 and cell_rect(lay, 7).y == 158 + 7 + 34 and cell_rect(lay, 4).w == 34
    assert bar.cell_at(lay, (cell_rect(lay, 6).x + 5, cell_rect(lay, 6).y + 5)) == 6
    assert bar.cell_at(lay, (0, 0)) is None


def test_enable_mask_and_pressed_highlight():
    assert bar.enable_mask("own", False) == 0xEF and bar.enable_mask("own", True) == 0xFF
    assert bar.enable_mask("foreign", True) == 0 and bar.enable_mask("none", True) == 0
    assert bar.bar_mode("none") == bar.bar_mode("foreign") == "heads" and bar.bar_mode("own") == "commands"
    assert bar.cells("none", False, 0) == ()
    cs = bar.cells("own", False, 0)
    assert [c.enabled for c in cs] == [True] * 4 + [False] + [True] * 3 and not any(c.pressed for c in cs)
    # the highlight stays on the button of the pending target mode (attack 1, move 2, defend 4, cast 5, swarm 6)
    assert [c.index for c in bar.cells("own", True, 4) if c.pressed] == [3]
    assert [c.index for c in bar.cells("own", True, 6) if c.pressed] == [5]
    assert [c.index for c in bar.cells("own", True, 1) if c.pressed] == [0] and bar.cells("own", True, 8) == bar.cells("own", True, 0)


def make_order(state="own", sel=(7,)):
    return OrderInput(1, 640, lambda: sel, lambda: state, 1, lambda: 0, lambda: 0)


def test_cell_press_runs_the_hotkey_of_the_button():
    o = make_order()
    assert bar.press(0, o, False) is None and o.pending == 1                       # Attack: pending mode 1
    bar.press(1, o, False)
    assert o.pending == 2
    bar.press(3, o, False)
    assert o.pending == 4
    bar.press(5, o, False)
    assert o.pending == 6
    guard = bar.press(2, o, False)                                                  # Guard acts at once and clears the mode
    assert type(guard).__name__ == "Guard" and o.pending == 0
    stop = bar.press(6, o, False)
    assert type(stop).__name__ == "Stop" and o.pending == 0


def test_disabled_cell_and_foreign_selection_do_nothing():
    o = make_order()
    assert bar.press(4, o, False) is None and o.pending == 0                        # Cast is "empty" for a fighter
    f = make_order("foreign")
    assert bar.press(0, f, True) is None and f.pending == 0
    assert bar.press(None, o, False) is None


# -- the bar window's press rules (`FUN_004ad8fd`, ui-layout 11.2) ----------------------------------------------------------------
def test_press_acts_at_once_and_the_highlight_follows_the_pending_mode():
    o, w = make_order(), bar.BarWindow()
    assert w.press(0, o, False, False) == (None, False) and o.pending == 1 and w.hl == 0      # Attack: acts on the press, no release needed
    assert w.highlight(o.pending) == 0
    w.press(3, o, False, False)
    assert o.pending == 4 and w.hl == 3                                                         # another cell replaces the mode
    cmd, _ = w.press(2, o, False, False)                                                        # Guard: acts at once, the highlight is cleared (0x40b)
    assert type(cmd).__name__ == "Guard" and o.pending == 0 and w.hl is None


def test_pressing_the_highlighted_cell_again_does_nothing():
    o, w = make_order(), bar.BarWindow()
    w.press(1, o, False, False)
    assert w.press(1, o, False, False) == (None, False) and o.pending == 2 and w.hl == 1       # `+0x60 == i`: return 1 (also a double click, slot 0x5c)
    w.press(0, o, False, False)
    assert o.pending == 1


def test_moving_off_the_cells_clears_the_highlight_but_not_the_mode():
    o, w = make_order(), bar.BarWindow()
    w.press(0, o, False, False)
    assert w.press(None, o, False, False) == (None, False)                                      # a gap / outside the cells: +0x60 = -1, message 0x40c(-1)
    assert w.hl is None and o.pending == 1                                                      # the pending mode stays (FUN_00418a02(0) changes nothing)
    assert w.press(4, o, False, False) == (None, False) and w.hl is None                        # a disabled cell (no spells) is a gap too


def test_the_gap_press_closes_the_book_only_in_cast_mode():
    o, w = make_order(sel=(7,)), bar.BarWindow()
    o.pending = 5
    assert w.press(None, o, True, True) == (None, True)                                         # `FUN_00418a02(0)`: pending 5 and the book open -> close it
    o.pending = 1
    assert w.press(None, o, True, True) == (None, False)


def test_cast_cell_does_nothing_while_the_book_is_open():
    o, w = OrderInput(1, 640, lambda: (7,), lambda: "own", 1, lambda: 3, lambda: 1), bar.BarWindow()
    assert w.press(4, o, True, True) == (None, False) and o.pending == 0 and w.hl is None       # `FUN_0041aef1` != 0: return 1
    w.press(4, o, True, False)
    assert o.pending == 5 and w.hl == 4


def test_heads_panel_takes_no_press():
    o, w = make_order("none"), bar.BarWindow()
    assert w.press(0, o, True, False) == (None, False) and o.pending == 0 and w.hl is None
