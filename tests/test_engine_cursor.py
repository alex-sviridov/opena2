"""Cursor choice (G3b), docs/engine/ui-layout.md section 6."""

import pytest

from engine.ui.cursor import CursorInput, CursorState as S, choose_cursor

W, H = 640, 480


def ci(x, y, **kw):
    return CursorInput((x, y), W, H, **kw)


@pytest.mark.parametrize("x,y,want", [
    (0, 0, S.ARROW_NW), (0, 100, S.ARROW_W), (0, H - 2, S.ARROW_SW), (0, H - 1, S.ARROW_SW),
    (100, 0, S.ARROW_N), (100, H - 2, S.ARROW_S), (100, H - 1, S.ARROW_S),
    (W - 2, 0, S.ARROW_NE), (W - 1, 100, S.ARROW_E), (W - 2, H - 2, S.ARROW_SE),
    (W - 1, H - 1, S.ARROW_SE)])
def test_border_arrows(x, y, want):
    assert choose_cursor(ci(x, y, in_viewport=True, hover_unit=True)) is want


def test_arrow_names():
    assert [s.cursor_name for s in (S.ARROW_N, S.ARROW_NE, S.ARROW_E, S.ARROW_SE, S.ARROW_S, S.ARROW_SW,
                                    S.ARROW_W, S.ARROW_NW)] == ["arrow%d" % i for i in range(8)]
    assert (S.DEFAULT.cursor_name, S.SELECT.cursor_name, S.PICKUP.cursor_name) == ("default", "select", "pickup")


def test_default_and_outside():
    assert choose_cursor(ci(100, 100, in_viewport=True)) is S.DEFAULT
    assert choose_cursor(ci(100, 100, in_viewport=False, hover_unit=True)) is S.DEFAULT
    assert choose_cursor(CursorInput(None)) is S.DEFAULT
    assert choose_cursor(ci(1, 100, in_viewport=True)) is S.DEFAULT


def test_select():
    assert choose_cursor(ci(100, 100, in_viewport=True, hover_unit=True)) is S.SELECT
    assert choose_cursor(ci(100, 100, in_viewport=True, hover_unit=True, hover_hostile=True)) is S.SELECT
    assert choose_cursor(ci(100, 100, in_viewport=True, hover_unit=True, selection="foreign",
                            selected_count=1, hover_hostile=True)) is S.SELECT
    assert choose_cursor(ci(100, 100, in_viewport=True, hover_unit=True, selection="own",
                            selected_count=2)) is S.SELECT


def test_own_selection_over_hostile_is_default():
    assert choose_cursor(ci(100, 100, in_viewport=True, hover_unit=True, hover_hostile=True,
                            selection="own", selected_count=1)) is S.DEFAULT


def test_pickup():
    kw = dict(in_viewport=True, hover_item_cell=True, selection="own", selected_count=1, single_is_hero=True)
    assert choose_cursor(ci(100, 100, **kw)) is S.PICKUP
    assert choose_cursor(ci(100, 100, **{**kw, "single_is_hero": False})) is S.DEFAULT
    assert choose_cursor(ci(100, 100, **{**kw, "selected_count": 2})) is S.DEFAULT
    assert choose_cursor(ci(100, 100, **{**kw, "selection": "foreign"})) is S.DEFAULT
    assert choose_cursor(ci(100, 100, **{**kw, "selection": "none"})) is S.DEFAULT
