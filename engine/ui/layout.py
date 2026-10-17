"""In-game interface layout per screen mode (docs/engine/ui-layout.md sections 1-4, CONFIRMED)."""

from dataclasses import dataclass

_IF = "graphics/interface/"
COLUMN_W = 160              # right column width (FUN_00483129)
STRIP_W = 16                # left strips, drawn inside the view at W-176 (FUN_00406f43)
MINIMAP_CENTER = (72, 82)   # image centre inside the minimap panel (FUN_004ac414)

# name -> (y, h, left graphics, right graphics); y offsets are the same at every mode.
_COLUMN = {
    "crystal": (0, 158, ("CrystalL.bmp",), ("CrystalR.bmp",)),                          # FUN_004ab753 / FUN_004ac414
    "bar": (158, 80, ("HeadsL.bmp", "CommandBarL.bmp"), ("HeadsR.bmp", "CommandBarR.bmp")),   # FUN_004ad57e, FUN_004adb65
    "info": (238, 242, ("HumanBackL.bmp", "TextBackL.bmp"), ("HumanBackR.bmp", "TextBackR.bmp")),  # FUN_004adf45 / FUN_004af3bf
}
# mode -> (extra strip graphic, extra panel graphic, height): FUN_004b0823 / FUN_004b0a10, FUN_00406f43
_EXTRA = {
    (640, 480): None,
    (800, 600): ("extra800l.bmp", "extra800r.bmp", 96),
    (1024, 768): ("extra1024l.bmp", "extra1024r.bmp", 46),
}
EXTRA_Y = 480
BOTTOM_BAR_H = 90           # FUN_004a2bba / FUN_004c61e7: (0, H-90, W-160, H)


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h

    def contains(self, x, y):
        return self.x <= x < self.right and self.y <= y < self.bottom

    def intersects(self, other):
        return self.x < other.right and other.x < self.right and self.y < other.bottom and other.y < self.bottom

    def translate(self, dx, dy):
        return Rect(self.x + dx, self.y + dy, self.w, self.h)


@dataclass(frozen=True)
class Panel:
    name: str
    rect: Rect
    graphics: tuple


def _paths(names):
    return tuple(_IF + n for n in names)


class Layout:
    SIZES = tuple(_EXTRA)
    MINIMAP_CENTER = MINIMAP_CENTER

    def __init__(self, w, h):
        self.size = (w, h)
        self.screen = Rect(0, 0, w, h)
        self.viewport = Rect(0, 0, w - COLUMN_W, h // 32 * 32)
        self.cells = (self.viewport.w // 32, self.viewport.h // 32)
        col_x, strip_x = w - COLUMN_W, w - COLUMN_W - STRIP_W
        panels = {}
        for key, (y, ph, left, right) in _COLUMN.items():
            panels["strip_" + key] = Panel("strip_" + key, Rect(strip_x, y, STRIP_W, ph), _paths(left))
            panels["panel_" + key] = Panel("panel_" + key, Rect(col_x, y, COLUMN_W, ph), _paths(right))
        extra = _EXTRA[self.size]
        self.strip_extra = self.extra_panel = None
        if extra:
            left, right, eh = extra
            self.strip_extra = Panel("strip_extra", Rect(strip_x, EXTRA_Y, STRIP_W, eh), _paths((left,)))
            self.extra_panel = Panel("extra_panel", Rect(col_x, EXTRA_Y, COLUMN_W, eh), _paths((right,)))
        self.strip_a, self.strip_b, self.strip_c = (panels["strip_" + k] for k in ("crystal", "bar", "info"))
        self.strip_d = self.strip_extra
        self.strips = tuple(s for s in (self.strip_a, self.strip_b, self.strip_c, self.strip_d) if s)
        self.crystal, self.bar_panel, self.info_panel = (panels["panel_" + k] for k in ("crystal", "bar", "info"))
        self.minimap = self.crystal.rect
        self.bottom_bar = Rect(0, h - BOTTOM_BAR_H, w - COLUMN_W, BOTTOM_BAR_H)

    @classmethod
    def for_size(cls, w, h):
        if (w, h) not in _EXTRA:
            raise ValueError(f"unsupported screen size {w}x{h}")
        return cls(w, h)

    def bar_graphics(self, selection_state):
        """(strip B, panel) graphic of the bar: Heads for 'none' / 'foreign', else CommandBar (view+0x140 / +0x144)."""
        i = 0 if selection_state in ("none", "foreign") else 1
        return self.strip_b.graphics[i], self.bar_panel.graphics[i]
