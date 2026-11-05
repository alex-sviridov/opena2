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
    MOVE = "move"
    ATTACK = "attack"
    SWARM = "swarm"
    DEFEND = "defend"
    PATROL = "patrol"
    CAST = "cast"
    TOWN = "town"
    SDEFAULT = "sdefault"           # minimap cursors (FUN_004accb4)
    SMOVE = "smove"
    SATTACK = "sattack"
    SDEFEND = "sdefend"
    SPATROL = "spatrol"
    SCAST = "scast"

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
    hover_structure: bool = False   # h & 0x20 (no structure is pickable yet)
    hover_enterable: bool = False   # h & 0x800
    hover_is_selected: bool = False # the hovered object is the single selected unit (view+0x994 == view+0x138)
    hover_fogged: bool = False      # h & 0x400 (no fog model yet)
    ctrl: bool = False
    alt: bool = False
    shift: bool = False             # never changes the cursor (R 1.3)
    pending: int = 0                # view+0x9b4, see engine.ui.orders
    dragging: bool = False          # a left capture is open (`mgr+0x9c`) with a non-empty drag rect (press corner and pointer differ in x and y)


def _border(x, y, w, h):
    """Arrow of the screen border rule (table rows of section 6), or None."""
    S = CursorState
    if x == 0:
        return S.ARROW_NW if y == 0 else S.ARROW_W if y < h - 2 else S.ARROW_SW
    if x < w - 2:
        return S.ARROW_N if y == 0 else S.ARROW_S if y >= h - 2 else None
    return S.ARROW_NE if y == 0 else S.ARROW_E if y < h - 2 else S.ARROW_SE


PENDING_CURSORS = {1: CursorState.ATTACK, 2: CursorState.MOVE, 4: CursorState.DEFEND, 5: CursorState.CAST,
                   6: CursorState.SWARM, 8: CursorState.PATROL}
MINIMAP_PENDING = {1: CursorState.SATTACK, 6: CursorState.SATTACK, 2: CursorState.SMOVE, 4: CursorState.SDEFEND,
                   5: CursorState.SCAST, 8: CursorState.SPATROL}


def choose_cursor(inp, previous=None):
    """Cursor state of `FUN_0040b2b8` (CONFIRMED, asm 0x40b2b8-0x40bcb7; research 1.3): border arrows first, nothing
    over the panels, then the pending mode (hover flags and modifiers ignored), else the table by selection,
    hover and Ctrl / Alt.  A mode without a cursor (3, 7) leaves the chooser's local cursor at its initial 0
    (`0x40b30e`), and the epilogue (`0x40bc99`) sets a cursor only when it is non-zero, so the cursor stays the
    one of the previous frame (CONFIRMED): `previous`, DEFAULT when there is none.  (Modes 3 and 7 are cleared in
    the call that arms them, so the UI never shows this.)  The spellbook cast branch and the open-window /
    carried-item overrides are out of scope."""
    S = CursorState
    if inp.mouse is None:
        return S.DEFAULT
    arrow = _border(inp.mouse[0], inp.mouse[1], inp.screen_w, inp.screen_h)
    if arrow is not None:
        return arrow
    if not inp.in_viewport:
        return S.DEFAULT
    if inp.dragging:                                    # `FUN_0041e730` and not `IsRectEmpty` (`0x40b57f`, `0x40bab4`): the rubber-band state shows the default arrow
        return S.DEFAULT                                # (every branch but the open-book cast one, out of scope); also over modes 3 / 7
    if inp.pending:
        cur = PENDING_CURSORS.get(inp.pending)
        if cur is None:                                 # modes 3 and 7 (any value without a table entry): the cursor is not touched
            return previous if previous is not None else S.DEFAULT
        return S.MOVE if cur is S.CAST and inp.hover_fogged else cur
    own = inp.selection == "own"
    if not own:                         # nothing, foreign or structure selection: no orders
        return S.SELECT if inp.hover_unit or inp.hover_structure else S.DEFAULT
    single = inp.selected_count == 1
    hero = single and inp.single_is_hero
    hover_obj = inp.hover_unit or inp.hover_structure
    pickup = hero and ((inp.hover_item_cell and not hover_obj) or (inp.hover_is_selected and inp.hover_item_cell))
    town = hero and inp.hover_enterable
    if hover_obj and inp.hover_hostile:
        if inp.alt:
            return S.MOVE
        if inp.hover_structure:
            return S.SELECT
        return S.SWARM if inp.ctrl else S.ATTACK
    if hover_obj:
        if inp.alt:
            return S.MOVE
        if inp.ctrl:
            return S.ATTACK
        return S.PICKUP if pickup else S.TOWN if town else S.SELECT
    if inp.ctrl:
        return S.SWARM
    if inp.alt:
        return S.MOVE
    return S.PICKUP if pickup else S.MOVE


def choose_minimap_cursor(inside, selection, pending):
    """`FUN_004accb4`: inside the map image with an own non-structure selection the small cursors (smove, or by
    pending mode; modes 3 and 7 give smove), else sdefault.  CONFIRMED (decompile)."""
    if not inside or selection != "own":
        return CursorState.SDEFAULT
    return MINIMAP_PENDING.get(pending, CursorState.SMOVE)
