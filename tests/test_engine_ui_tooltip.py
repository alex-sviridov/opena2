"""Tooltip rules (docs/engine/ui-layout.md 11.6b): hover timer, bar cell text, box geometry.  Synthetic, always run; the frame time is passed in."""

import pytest

from engine.ui import Layout, MainText, bar
from engine.ui.tooltip import HIDE_MS, SHOW_MS, TooltipTimer, bar_text, place, split_lines

LAY = Layout.for_size(640, 480)
MAIN = MainText(["Attack <A>", "Move <M>", "Guard <G>", "Defend <D>", "Cast <C>", "Swarm <S>", "Stand Ground <T>", "Retreat <R>"])
CELL0 = (LAY.bar_panel.rect.x + 8 + 5, LAY.bar_panel.rect.y + 7 + 5)
CELL4 = (LAY.bar_panel.rect.x + 8 + 5, LAY.bar_panel.rect.y + 7 + 34 + 5)
measure = lambda s: 6 * len(s)
SCREEN = (640, 480)


def run(timer, pos, steps, text="x", dt=100):
    tip = None
    for _ in range(steps):
        tip = timer.update(dt, pos, lambda p: text, measure, SCREEN)
    return tip


def test_shows_when_the_accumulator_crosses_500ms_after_the_last_move():
    t = TooltipTimer()
    assert t.update(100, (10, 10), lambda p: "x", measure, SCREEN) is None          # first sight of the pointer = a move
    assert run(t, (10, 10), 4) is None and t.acc == 400
    assert run(t, (10, 10), 1) is not None and t.acc == SHOW_MS                     # exactly 500 ms: shown


def test_moving_hides_and_restarts_the_timer_and_drops_the_frame_time():
    t = TooltipTimer()
    t.update(0, (10, 10), lambda p: "x", measure, SCREEN)
    assert run(t, (10, 10), 5) is not None
    assert t.update(100, (11, 10), lambda p: "x", measure, SCREEN) is None and t.acc == 0
    assert run(t, (11, 10), 4) is None
    assert run(t, (11, 10), 1) is not None


def test_hides_after_25500ms():
    t = TooltipTimer()
    t.update(0, (10, 10), lambda p: "x", measure, SCREEN)
    assert run(t, (10, 10), 5, dt=100) is not None
    assert t.update(HIDE_MS - SHOW_MS - 1, (10, 10), lambda p: "x", measure, SCREEN) is not None      # 25 499 ms
    assert t.update(1, (10, 10), lambda p: "x", measure, SCREEN) is None                                # 25 500 ms
    assert HIDE_MS == 25500
    assert run(t, (10, 10), 10) is None                                                                   # never shown again until a move


def test_text_is_asked_once_at_the_crossing_only():
    t = TooltipTimer()
    asked = []
    t.update(0, (3, 3), lambda p: asked.append(p) or "", measure, SCREEN)
    for _ in range(20):
        assert t.update(100, (3, 3), lambda p: asked.append(p) or "", measure, SCREEN) is None
    assert asked == [(3, 3)]                                                     # empty text at 500 ms: nothing until the pointer moves


def test_a_big_frame_that_jumps_over_the_window_still_shows_once():
    t = TooltipTimer()
    t.update(0, (3, 3), lambda p: "x", measure, SCREEN)
    assert t.update(2000, (3, 3), lambda p: "x", measure, SCREEN) is not None


def test_a_frame_starting_past_500_does_not_show():
    t = TooltipTimer()
    t.update(0, (3, 3), lambda p: "", measure, SCREEN)
    t.update(600, (3, 3), lambda p: "", measure, SCREEN)                          # crossed with no text
    assert t.update(100, (3, 3), lambda p: "x", measure, SCREEN) is None          # prev >= 500: the exe's `local_8 < 500` test fails


def test_pointer_leaving_or_modal_clears():
    t = TooltipTimer()
    t.update(0, (3, 3), lambda p: "x", measure, SCREEN)
    assert run(t, (3, 3), 5) is not None
    assert t.update(10, None, lambda p: "x", measure, SCREEN) is None
    t.update(0, (3, 3), lambda p: "x", measure, SCREEN)
    assert run(t, (3, 3), 5) is not None
    assert t.update(10, (3, 3), lambda p: "x", measure, SCREEN, frozen=True) is None


def test_world_press_hides():
    t = TooltipTimer()
    t.update(0, (3, 3), lambda p: "x", measure, SCREEN)
    run(t, (3, 3), 5)
    t.hide()
    assert t.tip is None


@pytest.mark.parametrize("i", range(8))
def test_cell_text_is_main_line_i_with_the_hotkey(i):
    pos = (LAY.bar_panel.rect.x + 8 + (i & 3) * 34 + 5, LAY.bar_panel.rect.y + 7 + (i >> 2) * 34 + 5)
    assert bar_text(LAY, pos, "own", True, MAIN) == MAIN.line(i)
    assert MAIN.line(i).endswith(">")


def test_cast_cell_has_no_tooltip_while_disabled_other_cells_do():
    assert bar_text(LAY, CELL4, "own", False, MAIN) == ""                          # a fighter's Cast cell: mask bit clear
    assert bar_text(LAY, CELL0, "own", False, MAIN) == "Attack <A>"                 # hero or mage alike: the same ids, only the mask differs


@pytest.mark.parametrize("state", ["none", "foreign"])
def test_heads_bar_has_no_cell_tooltips(state):
    assert bar_text(LAY, CELL0, state, True, MAIN) == ""


def test_modal_carried_item_and_gaps_give_nothing():
    assert bar_text(LAY, CELL0, "own", True, MAIN, frozen=True) == ""
    assert bar_text(LAY, CELL0, "own", True, MAIN, carried=True) == ""
    assert bar_text(LAY, (LAY.bar_panel.rect.x + 1, LAY.bar_panel.rect.y + 1), "own", True, MAIN) == ""
    assert bar_text(LAY, (5, 5), "own", True, MAIN) == ""
    assert bar_text(LAY, None, "own", True, MAIN) == ""


def test_box_sits_above_and_right_of_the_pointer():
    tip = place("Attack <A>", (100, 200), measure, SCREEN)
    assert (tip.x, tip.bottom) == (100, 200)
    assert tip.right == 100 + measure("Attack <A>") + 11
    assert tip.y == 200 - 5 - 14


def test_hash_splits_lines_and_widens_to_the_longest():
    assert split_lines("a#bb#c") == ("a", "bb", "c")
    tip = place("a#bbbb#c", (10, 100), measure, SCREEN)
    assert tip.right - tip.x == measure("bbbb") + 11 and tip.bottom - tip.y == 5 + 14 * 3


def test_right_edge_is_pushed_back_and_the_top_pushed_down():
    tip = place("Retreat <R>", (630, 100), measure, SCREEN)
    assert tip.right == 640 and tip.x == 640 - (measure("Retreat <R>") + 11)
    low = place("Attack <A>", (50, 10), measure, SCREEN)
    assert low.y == 0 and low.bottom - low.y == 5 + 14
