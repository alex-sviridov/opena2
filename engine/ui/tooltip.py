"""Tooltips (docs/engine/ui-layout.md 11.6b): the hover timer of the mouse manager (`FUN_004268c4`), the text of a command-bar cell (`FUN_004ad61c`) and the
box geometry (`FUN_0042787b`).  Pure state: the caller passes the frame time in milliseconds (never the sim tick), so tests are deterministic."""

from dataclasses import dataclass

from . import bar

SHOW_MS = 500            # the hover accumulator crosses 500 ms (`FUN_004268c4`: `499 < acc` and the previous value `< 500`)
HIDE_MS = 0x639C         # 25 500 ms: `acc >= 0x639c` hides a shown tooltip (`FUN_00427e45`)
LINE_H = 14              # `FUN_0042787b`: height = 5 + 14 * lines; `FUN_00427999` draws line i at top + 4 + 14 * i
TEXT_DX, TEXT_DY = 5, 4  # text origin inside the box
PAD_W, PAD_H = 11, 5     # box width = widest line + 11, height = 14 * lines + 5
LINE_BREAK = "#"         # `FUN_0042677d` / `FUN_00427999` split the text at every '#' (`FUN_005a1cf8(0x23)`)

# `FUN_00427999` colours (8-bit channels; the exe packs them into the screen's 565 format): fill, light line, dark line (channel order INFERRED R, G, B)
FILL, LIGHT, DARK = (0x24, 0x2C, 0x27), (0xA0, 0x78, 0x32), (0x50, 0x3C, 0x18)


@dataclass(frozen=True)
class Tip:
    lines: tuple
    x: int            # box rect (left, top, right, bottom exclusive of nothing: the exe's RECT, bottom = the pointer y)
    y: int
    right: int
    bottom: int


def split_lines(text):
    return tuple(text.split(LINE_BREAK))


def place(text, pos, measure, screen):
    """The box of `text` for a pointer at `pos` (`FUN_0042787b`): left = pointer x, bottom = pointer y, top = y - 5 - 14 * lines, right = x + widest + 11; then
    shifted left when the right edge passes the screen's right (`DAT_00621418`) and down when the top is above the clip top (`DAT_00621414`, 0).  The box always
    sits above and to the right of the pointer; there is no left / bottom clamp.  `screen` = (w, h): the two clip globals are set at run time (INFERRED w and 0)."""
    lines = split_lines(text)
    widest = max(measure(s) for s in lines)
    x, y = pos
    left, top, right, bottom = x, y - PAD_H - LINE_H * len(lines), x + widest + PAD_W, y
    if right > screen[0]:
        left, right = left + screen[0] - right, screen[0]
    if top < 0:
        top, bottom = 0, bottom - top
    return Tip(lines, left, top, right, bottom)


def bar_text(layout, pos, state, cast_enabled, main, frozen=False, carried=False):
    """`FUN_004ad61c` (bar vtable slot 5): the tooltip text under `pos`, '' when none.  Only the commands bar (own selection) has cells; only a cell whose mask bit
    is set answers (a disabled cell has no tooltip); never while a modal window is open (`client+0x404 & 0xe`) or an item is carried (`client+0x3f4`).
    The text is main.txt line `i` (`FUN_0041f350(i)`, the hotkey letter is part of the line: "Attack <A>")."""
    if frozen or carried or pos is None or state != "own":
        return ""
    i = bar.cell_at(layout, pos)
    if i is None or not bar.enable_mask(state, cast_enabled) >> i & 1:
        return ""
    return main.line(bar.CELL_TEXT[i])


class TooltipTimer:
    """`FUN_004268c4` (per frame) + `FUN_00426594` (pointer moved).  `update(dt, pos, text_fn, measure, screen)` -> the shown `Tip` or None."""

    def __init__(self):
        self.acc = 0
        self.pos = None
        self.tip = None

    def hide(self):
        """`FUN_00427e45`: also run by the left press in the world (`FUN_0042748f`, begin of a selection / order capture)."""
        self.tip = None

    def moved(self, pos):
        """`FUN_00426594` at the event itself (the shell sees the move before the frame): timer 0, hide, stamp the position; the frame after it counts in full."""
        if pos != self.pos:
            self.pos, self.acc, self.tip = pos, 0, None

    def update(self, dt, pos, text_fn, measure, screen, frozen=False):
        if pos is None or frozen:
            self.pos, self.acc, self.tip = None, 0, None
            return None
        if pos != self.pos:                                   # the pointer moved: timer 0, hide; this frame's dt is dropped (last := now)
            self.pos, self.acc, self.tip = pos, 0, None
            return None
        prev = self.acc
        self.acc += dt
        if SHOW_MS <= self.acc < HIDE_MS and prev < SHOW_MS and self.tip is None:
            text = text_fn(pos)                               # asked once, at the crossing: no text then = no tooltip until the pointer moves again
            if text:
                self.tip = place(text, pos, measure, screen)
        if self.acc >= HIDE_MS:
            self.tip = None
        return self.tip
