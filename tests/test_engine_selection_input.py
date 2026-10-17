"""Mouse selection input (G3b), docs/engine/ui-layout.md section 8."""

import pytest

from engine.sim import SelectUnits
from engine.ui.selection import SelectionInput, drag_threshold
from engine.view.pick import PickRect

ME = 1
PICKS = [PickRect(10, 0, 0, 40, 40), PickRect(11, 100, 0, 140, 40), PickRect(12, 200, 0, 240, 40)]
OWNERS = {10: ME, 11: ME, 12: 2}


def make(w=640, sel=(), hostile=()):
    return SelectionInput(ME, w, lambda: PICKS, OWNERS.get, lambda: sel, lambda e: e in hostile)


def gesture(si, a, b, **kw):
    si.press(*a)
    return si.release(*b, **kw)


@pytest.mark.parametrize("w,t", [(640, 10), (800, 12), (1024, 16)])
def test_threshold_click_vs_drag(w, t):
    assert drag_threshold(w) == t
    si = make(w)
    assert gesture(si, (20, 20), (20 + t, 20)) == SelectUnits(ME, (10,))
    assert gesture(si, (20, 20), (20, 20 + t)) == SelectUnits(ME, (10,))
    assert gesture(si, (20, 20), (20 + t + 1, 40)) == SelectUnits(ME, (10,))      # drag over the own unit
    assert gesture(si, (90, 50), (90 + t + 1, 50)) is None                         # drag over nothing


def test_drag_selects_own_only_and_keeps_selection_on_miss():
    si = make()
    assert gesture(si, (0, 0), (250, 50)) == SelectUnits(ME, (10, 11))
    assert gesture(si, (190, 0), (250, 50)) is None


def test_click_foreign_with_empty_selection():
    assert gesture(make(), (210, 20), (210, 20)) == SelectUnits(ME, (12,))


def test_miss_is_none():
    assert gesture(make(), (70, 20), (70, 20)) is None


def test_shift_toggles_own_only():
    si = make()
    assert gesture(si, (20, 20), (20, 20), shift=True) == SelectUnits(ME, (10,), toggle=True)
    assert gesture(si, (210, 20), (210, 20), shift=True) is None
    assert gesture(si, (0, 0), (250, 50), shift=True) == SelectUnits(ME, (10, 11), toggle=True)


def test_hostile_click_ignored_with_own_selection():
    si = make(sel=(10,), hostile=(12,))
    assert gesture(si, (210, 20), (210, 20)) is None
    assert gesture(si, (110, 20), (110, 20)) == SelectUnits(ME, (11,))
    assert gesture(make(hostile=(12,)), (210, 20), (210, 20)) == SelectUnits(ME, (12,))


def test_right_click_clears_and_release_without_press():
    si = make()
    assert si.right_click() == SelectUnits(ME, ())
    assert si.release(20, 20) is None
