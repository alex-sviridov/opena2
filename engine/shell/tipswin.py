"""The tips window of the original (docs/engine/chargen.md 1.5; class `0x4dec24`, builder `0x4deca4`, base `0x4dbc50`): a framed window with a text box, a Close button
and the check box "Show tips next time".  The caller gives the window rect (`SetRect` order l, t, r, b, relative to its parent); every child is laid out from the
window size (w, h): text box (20, 24, w - 28, h - 36) as (l, t, r, b), Close (w - 120, h - 40, w - 40, h - 22) main.txt 0x7f, check box (40, h - 40, w - 124, h - 24)
main.txt 0x80, built checked (`vtable+0x44(1)`).  The frame is the 11.4 dialog frame of w - 8 x h - 8 plus the 8 px shadow (`0x4deeb0`).

The check box click sends message `0x46e` (id 0xf, state) to the window, which stores the state into TipsMode `0x622774` at once (`0x4df278`); the engine writes
`Settings.tips` and saves it.  Close posts `0x45a`, which the owner answers by removing the window; ESC / Enter / `0x445` / `0x446` return 0 (nothing).

Text box (class `0x5cfdc8`, `0x4d4e9b`, paint `0x4d5134` -> `0x45e01d`, CONFIRMED): the text is wrapped to the box width (`0x45ccbb`: a line is kept while its font2 measure is < the width), line `n` is drawn left aligned at (box left, box top + n * pitch) with pitch = glyph-0 height + 2 (font2: 12), at most height / pitch lines; a line that is not the last of its paragraph is
justified (`0x45da67`: the word gaps share the free width equally, x accumulates as a double and is truncated per word); no centring, no margin beyond the box rect.
Only Close and the check box take mouse input (INFERRED: the text box and frame return 0, so a click elsewhere reaches the owner beneath)."""

from . import dialog
from .options import RADIO_OFF, RADIO_ON, RADIOB, SHADOW
from .scene import Button, Frame, Sprite, Text

TEXT_L, TEXT_R = 40, 44                                  # DECISION: skull sprites cover x 0..38 / w-44..w; the text box is inset to clear them (the exe's own box is 20 / 28)
CLOSE_W = 64
TEXT_FONT, LINE = 2, 12                                  # LINE = pitch = glyph-0 height of font2 (10) + 2 (`0x4d4e9b`, pitch argument 0)


def rect_has(r, x, y):
    return r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]


class TipsWindow:
    """One tips window: `rect` = (x, y, w, h) in the owner's coordinates (the SetRect (l, t, r, b) turned into a size, made absolute through the parent's origin), `main` = `MainText`."""

    def __init__(self, rect, main, wrap, measure):
        self.rect, self.main, self.wrap, self.measure = rect, main, wrap, measure
        x, y, w, h = rect
        row = dialog.bottom_row_y(h, 18)                      # DECISION: the exe's bottom row (h - 40 .. h - 22) runs onto the bottom border band; moved up to clear it (`dialog.py`)
        self.text_box = (x + TEXT_L, y + 24, w - TEXT_R - TEXT_L, row - 4 - 24)      # DECISION: the exe box (20, 24, w - 28, h - 36) runs into the 48 px corner skulls; inset in x only, and it ends above the control row (chargen.md 1.5)
        x0, x1 = dialog.between_corners(w)                    # DECISION: the bottom row sits between the corner skulls: Close (64 wide, the exe's 80) at the right end, the check box before it
        cx, cy, cw, ch = dialog.clamp_inside((x1 - CLOSE_W, row, CLOSE_W, 18), w, h)
        self.close = (x + cx, y + cy, cw, ch)
        kx, ky, kw, kh = dialog.clamp_inside((x0, row + 1, cx - 4 - x0, 16), w, h)
        self.check = (x + kx, y + ky, kw, kh)
        self.checked = True                                   # `0x4deca4`: state 1 at build

    def hit(self, x, y):
        """"close" / "tips" / None; the rest of the window is not an input target (INFERRED: the static text and the frame return 0, so the click reaches the owner beneath)."""
        if rect_has(self.close, x, y):
            return "close"
        if rect_has(self.check, x, y):
            return "tips"
        return None

    def toggle(self):
        """The check box click: the new state (the owner stores it into TipsMode)."""
        self.checked = not self.checked
        return self.checked

    def ops(self, text, hover=None, pressed=None, ox=0, oy=0):
        """Draw ops, the window at (ox, oy) + `rect`."""
        x, y, w, h = self.rect
        x, y = x + ox, y + oy
        tx, ty, tw, th = self.text_box
        tx, ty = tx + ox, ty + oy
        ops = [Frame(x, y, w, h)]
        lines = [(ln, last) for para in text.replace("\r\n", "\n").split("\n")
                 for lines_ in [self.wrap(para, tw - 1)] for ln, last in zip(lines_, [False] * (len(lines_) - 1) + [True])]
        for n, (line, last) in enumerate(lines[:th // LINE]):
            words = line.split(" ")
            if last or len(words) < 2:
                ops.append(Text(line, tx, ty + LINE * n, TEXT_FONT, "label", 0, 1))
                continue
            gap = (tw - sum(self.measure(w) for w in words)) / (len(words) - 1)          # `0x45da67`
            fx = float(tx)
            for w in words:
                ops.append(Text(w, int(fx), ty + LINE * n, TEXT_FONT, "label", 0, 1))
                fx += self.measure(w) + gap
        kx, ky = self.check[0] + ox, self.check[1] + oy                               # `0x4d7b31`: frame 5 (on) / 4 (off) at (x + 1, y), shadow 4 at (x + 5, y + 4), caption (x + 22, y + 3)
        on = RADIO_ON if self.checked else RADIO_OFF
        ops += [Sprite(RADIOB, on, kx + 5, ky + 4, SHADOW), Sprite(RADIOB, on, kx + 1, ky),
                Text(self.main.line(0x80), kx + 22, ky + 3, TEXT_FONT, "header" if hover == "tips" else "label", 0, 1)]
        cx, cy, cw, ch = self.close
        cx, cy = cx + ox, cy + oy
        ops.append(Button(cx, cy, cw, ch, self.main.line(0x7F), True, hover == "close", pressed == "close"))
        return ops
