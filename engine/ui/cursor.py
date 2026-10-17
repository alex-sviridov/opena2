"""Cursor choice (docs/engine/ui-layout.md section 6, FUN_0040b2b8): a pure function of the input state."""

from dataclasses import dataclass
from enum import Enum


class CursorState(Enum):
    DEFAULT = "default"
    SELECT = "select"
    PICKUP = "pickup"
    ARROW_N = "arrow0"
    ARROW_NE = "arrow1"
    ARROW_E = "arrow2"
    ARROW_SE = "arrow3"
    ARROW_S = "arrow4"
    ARROW_SW = "arrow5"
    ARROW_W = "arrow6"
    ARROW_NW = "arrow7"

    @property
    def cursor_name(self):
        """Name of the cursor set in allods2.anim.ui.CURSORS."""
        return self.value


@dataclass(frozen=True)
class CursorInput:
    mouse: tuple = None             # (x, y) or None when the pointer is outside the window
    screen_w: int = 640
    screen_h: int = 480
    in_viewport: bool = False
    hover_unit: bool = False
    hover_hostile: bool = False
    hover_item_cell: bool = False
    selection: str = "none"         # "none" | "own" | "foreign"
    selected_count: int = 0
    single_is_hero: bool = False


def _border(x, y, w, h):
    """Arrow of the screen border rule (table rows of section 6), or None."""
    S = CursorState
    if x == 0:
        return S.ARROW_NW if y == 0 else S.ARROW_W if y < h - 2 else S.ARROW_SW
    if x < w - 2:
        return S.ARROW_N if y == 0 else S.ARROW_S if y >= h - 2 else None
    return S.ARROW_NE if y == 0 else S.ARROW_E if y < h - 2 else S.ARROW_SE


def choose_cursor(inp):
    """Cursor state: border arrows first, then pickup / select over the viewport, else default."""
    if inp.mouse is None:
        return CursorState.DEFAULT
    arrow = _border(inp.mouse[0], inp.mouse[1], inp.screen_w, inp.screen_h)
    if arrow is not None:
        return arrow
    if not inp.in_viewport:
        return CursorState.DEFAULT
    own = inp.selection == "own"
    if own and inp.selected_count == 1 and inp.single_is_hero and inp.hover_item_cell and not inp.hover_unit:
        return CursorState.PICKUP
    if inp.hover_unit and (not own or not inp.hover_hostile):
        return CursorState.SELECT
    return CursorState.DEFAULT
