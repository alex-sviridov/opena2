"""Command bar (window 6), pure part (docs/engine/ui-layout.md 11.2): cell states and hit tests."""

from dataclasses import dataclass

from . import orders
from .widgets import CELLS, cell_rect

# cell i = `FUN_00418a02(i + 1)`: button numbers 1 attack, 2 move, 3 guard, 4 defend, 5 cast, 6 swarm, 7 stand ground, 8 retreat
CELL_KEYS = ("a", "m", "g", "d", "c", "s", "t", "r")
CELL_TEXT = tuple(range(8))                         # main.txt i: "Attack <A>" ... = the tooltip of cell i (CONFIRMED `FUN_004ad61c`)
BASE_MASK = 0xEF                                    # every button but Cast (`FUN_0041757b`)
CAST_BIT = 0x10
PENDING_CELLS = {orders.ATTACK: 0, orders.MOVE: 1, orders.DEFEND: 3, orders.CAST: 4, orders.SWARM: 5}


@dataclass(frozen=True)
class Cell:
    index: int
    enabled: bool
    pressed: bool


def enable_mask(state, cast_enabled):
    """`FUN_0041757b`: `0xef | 0x10 (a castable slot)` for an own selection, 0 for none / foreign (the Heads panel has no cells)."""
    if state != "own":
        return 0
    return BASE_MASK | (CAST_BIT if cast_enabled else 0)


def bar_mode(state):
    """'heads' (nothing / foreign selection: HeadsR, a bare picture) or 'commands' (an own selection)."""
    return "commands" if state == "own" else "heads"


def cells(state, cast_enabled, pending, highlight=-1):
    """The eight cells with their enabled / pressed state; empty for the heads panel.  The pressed highlight stays while a target mode is pending;
    `highlight` (a `BarWindow.hl`: a cell or None) overrides it when the window's own state differs from the pending mode."""
    if bar_mode(state) != "commands":
        return ()
    mask = enable_mask(state, cast_enabled)
    pressed = PENDING_CELLS.get(pending) if highlight == -1 else highlight
    return tuple(Cell(i, bool(mask >> i & 1), pressed == i) for i in range(CELLS))


def cell_at(layout, pos):
    """Index of the cell under `pos`, or None."""
    for i in range(CELLS):
        if cell_rect(layout, i).contains(*pos):
            return i
    return None


def press(i, ordering, cast_enabled):
    """The left press on cell `i`: an enabled cell runs the key of its button (`OrderInput.key`).  Returns the command or None."""
    state = ordering.state_fn()
    if i is None or not enable_mask(state, cast_enabled) >> i & 1:
        return None
    cmd, _ = ordering.key(CELL_KEYS[i])
    return cmd


IMMEDIATE_CELLS = (2, 6, 7)            # Guard, Stand Ground, Retreat: the view clears the highlight at once (message 0x40b)


class BarWindow:
    """The window's own highlight `+0x60` (`hl`) and the press rules of `FUN_004ad8fd` (CONFIRMED, ui-layout 11.2).  The highlight follows the view's
    pending mode (messages 0x40d set it, 0x40b clears it) except that a press on no enabled cell clears it without touching the mode."""

    def __init__(self):
        self.hl = None
        self.clicked = False           # set when a press ran a button (the exe's click sound `0x40c295`)
        self.seen = 0                  # the pending mode the highlight last followed

    def sync(self, pending):
        if pending != self.seen:
            self.seen, self.hl = pending, PENDING_CELLS.get(pending)

    def highlight(self, pending):
        self.sync(pending)
        return self.hl

    def press(self, i, ordering, cast_enabled, book_open):
        """The left press, and every move with the left button held over the bar (`FUN_004adb35` calls the press).  Returns (command, close_book).
        Heads panel: nothing (the cells flag `+0x68` is clear).  Enabled cell: nothing when it already is the highlight, nothing for Cast while the
        book is open, else it becomes the highlight and the view runs the button (`0x40c` -> `FUN_00418a02`).  Anywhere else (a disabled cell, the
        gaps): highlight cleared and `0x40c(-1)` = `FUN_00418a02(0)`, which only closes the book when Cast is the pending mode."""
        if bar_mode(ordering.state_fn()) != "commands":
            return None, False
        self.sync(ordering.pending)
        if i is None or not enable_mask("own", cast_enabled) >> i & 1:
            self.hl = None
            return None, ordering.pending == orders.CAST and book_open
        if self.hl == i or (i == 4 and book_open):
            return None, False
        self.hl = i
        self.clicked = True
        cmd = press(i, ordering, cast_enabled)
        if i in IMMEDIATE_CELLS:
            self.hl = None
        else:
            self.sync(ordering.pending)
        return cmd, False
