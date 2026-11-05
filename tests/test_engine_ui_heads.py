"""Heads panel, extra panel and hero arrows (docs/engine/ui-layout.md 11.8).  Synthetic: layout and state rules, no install."""

from engine.ui import GameUi, Layout, MainText, bar, info
from test_engine_death import hero, unit, world


def make(size=(640, 480)):
    w = world()
    return GameUi(Layout.for_size(*size), w, 1, MainText(["m%02x" % i for i in range(0x100)]), MainText(), MainText()), w


def test_strip_b_shows_heads_for_nothing_or_a_foreign_selection_and_the_bar_for_an_own_one():
    lay = Layout.for_size(640, 480)
    assert [lay.bar_graphics(s)[1].rsplit("/", 1)[1] for s in ("none", "foreign", "own")] == ["HeadsR.bmp", "HeadsR.bmp", "CommandBarR.bmp"]
    assert [lay.bar_graphics(s)[0].rsplit("/", 1)[1] for s in ("none", "foreign", "own")] == ["HeadsL.bmp", "HeadsL.bmp", "CommandBarL.bmp"]


def test_the_heads_panel_has_no_cells_no_portraits_and_takes_no_clicks():
    """`FUN_004adb65` blits HeadsR alone when `+0x68 == 0`; `FUN_004ad8fd` needs `+0x68` (cells enabled) for a hit: the panel is only a picture."""
    ui, w = make()
    other = unit(w, 3, 8, 8, owner=2)
    for sel in ((), (other.id,)):
        w.players[1].selection = sel
        assert bar.bar_mode(ui.world_state()) == "heads" and bar.enable_mask(ui.world_state(), True) == 0
        assert not any(c.enabled for c in bar.cells(ui.world_state(), True, 0))
        r = ui.layout.bar_panel.rect
        assert ui.mouse_down((r.x + 20, r.y + 20)) == (True, None)             # consumed (it is the panel), no command, no highlight
        assert ui.bar.hl is None


def test_extra_panel_exists_only_above_480_and_holds_the_text_at_1024():
    assert Layout.for_size(640, 480).extra_text is None and Layout.for_size(640, 480).extra_panel is None
    l8 = Layout.for_size(800, 600)
    assert not l8.text_in_extra and l8.extra_text is None and l8.extra_panel.rect.h == 96          # 120 high window, the 242 rows do not fit
    l10 = Layout.for_size(1024, 768)
    assert l10.text_in_extra and (l10.extra_text.x, l10.extra_text.y, l10.extra_text.w, l10.extra_text.h) == (864, 526, 160, 242)
    assert l10.extra_panel.rect.bottom == l10.extra_text.y                                            # picture 46 on top of the 242 text rows
    assert l10.strip_extra_text.rect.y == 526 and l10.strip_extra_text.rect.h == 242


def test_at_1024_the_info_panel_is_forced_to_the_picture_and_the_mode_button_is_dead():
    ui, w = make((1024, 768))
    assert ui.shown_mode == info.MODE_PICTURE
    ui.toggle_mode()
    ui.key("tab")
    assert ui.panel_mode == info.MODE_PICTURE
    p = ui.layout.info_panel.rect
    assert not ui.info_release((p.x + 0x90, p.y + 10))                                  # the mode button is not there
    u8, w8 = make((800, 600))
    u8.toggle_mode()
    assert u8.shown_mode == info.MODE_TEXT


def test_buttons_are_the_same_with_any_selection_in_a_mission():
    ui, w = make()
    other = unit(w, 3, 8, 8, owner=2)
    p = ui.layout.info_panel.rect
    for sel in ((), (other.id,)):
        w.players[1].selection = sel
        assert ui.info_release((p.x + 0x80, p.y + 0xD0)) and ui.modals.kinds() == ("menu",)
        ui.modals.clear()


def test_bar_cell_acts_on_the_press_and_the_release_does_nothing():
    """`FUN_004ad8fd` (slot 0x54) acts, `FUN_004adace` (slot 0x58) only drops a carried item's cursor; a carried item blocks the press (`client+0x3f4`)."""
    from engine.ui import OrderInput
    ui, w = make()
    u = hero(w, 3, 8, 8)
    w.players[1].selection = (u.id,)
    assert ui.world_state() == "own"
    o = OrderInput(1, 640, lambda: w.players[1].selection, ui.world_state, 1, lambda: 0, lambda: 0)
    r = bar.cell_rect(ui.layout, 1)
    pos = (r.x + 5, r.y + 5)
    ui.pack.carried = object()
    assert ui.mouse_down(pos, o) == (True, None) and o.pending == 0                     # an item in the hand: the press does nothing
    ui.pack.carried = None
    assert ui.mouse_down(pos, o) == (True, None) and o.pending == 2 and ui.bar.hl == 1  # Move: pending at once
    assert ui.info_release(pos) is False and ui.mouse_up(pos) is False and o.pending == 2   # the release neither cancels nor repeats
    ui.bar_press((r.x + 100, r.y - 4), o, False)                                          # dragging off the cells (a held move): highlight cleared, mode kept
    assert ui.bar.hl is None and o.pending == 2
