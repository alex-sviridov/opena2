"""Mouse selection (docs/engine/ui-layout.md section 8): press / release -> `SelectUnits`."""

from engine.sim import SelectUnits
from engine.view.pick import pick_at, pick_in_rect


def drag_threshold(screen_w):
    """Corner distance in x or y above which a release is a drag (FUN_004175c7)."""
    return screen_w * 10 // 640


def clip_to(rect, pos):
    """`pos` clamped into `rect` (x, y, right, bottom exclusive): the `ClipCursor` of the view while a left capture is open (`FUN_0048acbc`)."""
    return (min(max(pos[0], rect.x), rect.right - 1), min(max(pos[1], rect.y), rect.bottom - 1))


def drag_rect(corner, pos):
    """Normalised (left, top, right, bottom) of the capture rect from the press corner to the pointer (`mgr+0x6c`, `NormalizeRect`)."""
    return (min(corner[0], pos[0]), min(corner[1], pos[1]), max(corner[0], pos[0]), max(corner[1], pos[1]))


def drag_nonempty(corner, pos):
    """`IsRectEmpty` is false: the pointer differs from the press in both x and y (a pure horizontal / vertical drag is empty)."""
    return corner is not None and pos is not None and corner[0] != pos[0] and corner[1] != pos[1]


def band_lines(corner, pos):
    """The four 1 px lines (x, y, w, h) of the rubber band `FUN_0042754f` draws in white: normalised rect, lines on
    left .. right-1 and top .. bottom-1 (`FUN_004569a3(l, t, r-1, b-1)`)."""
    l, t, r, b = drag_rect(corner, pos)
    r, b = r - 1, b - 1
    if r < l or b < t:
        return [(l, t, 1, 1)]
    return [(l, t, r - l + 1, 1), (l, b, r - l + 1, 1), (l, t, 1, b - t + 1), (r, t, 1, b - t + 1)]


class SelectionInput:
    """`picks_fn()` -> PickRects of the last draw list (units and structures: `DrawList.hover_picks`); `owner_fn(entity)` -> owner id or None;
    `hostile_fn(entity)` -> bool; `selection_fn()` -> the player's selection tuple."""

    def __init__(self, player_id, screen_w, picks_fn, owner_fn, selection_fn, hostile_fn=lambda e: False):
        self.player_id, self.screen_w = player_id, screen_w
        self.picks_fn, self.owner_fn = picks_fn, owner_fn
        self.selection_fn, self.hostile_fn = selection_fn, hostile_fn
        self.corner = None

    def press(self, x, y):
        self.corner = (x, y)

    def _own(self, entity):
        return self.owner_fn(entity) == self.player_id

    def release(self, x, y, shift=False):
        """`SelectUnits` for the gesture ended at (x, y), or None (selection kept)."""
        if self.corner is None:
            return None
        x0, y0 = self.corner
        self.corner = None
        t = drag_threshold(self.screen_w)
        picks = self.picks_fn()
        if abs(x - x0) > t or abs(y - y0) > t:
            rect = (min(x0, x), min(y0, y), max(x0, x), max(y0, y))
            ids = tuple(e for e in pick_in_rect(picks, rect) if self._own(e))
        else:
            e = pick_at(picks, x, y)
            if e is None or self.owner_fn(e) is None:      # nothing, or a structure (not a unit: `owner_fn` None): the selection stays (`FUN_00417986`)
                return None
            if shift:
                ids = (e,) if self._own(e) else ()
            else:
                sel = self.selection_fn()
                if self.hostile_fn(e) and sel and self._own(sel[0]):
                    return None
                ids = (e,)
        if not ids:
            return None
        return SelectUnits(self.player_id, ids, toggle=shift)

    def right_click(self):
        """Clear the selection (DECISION: the exe's way is untraced)."""
        return SelectUnits(self.player_id, ())
