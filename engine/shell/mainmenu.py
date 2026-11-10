"""The main menu (docs/engine/shell.md 3; class `0x5cec48`, loader `0x4a7657`, paint `0x4a7b3f`, mouse `0x4a7d0d` / `0x4a813c` / `0x4a81a3`).

A 640x480 picture (`menu_.bmp`) with eight carved buttons, found under the pointer through the 640x480 hit mask `MenuMask.bmp`
(value `0x80 + 0x10 n` = button n; `0x10..0x1e` outline pixels and 0 do nothing).  Hover draws `button<n+1>p.bmp` over the picture at the
button's rect, a held button `button<n+1>.bmp`, and the caption `text<n+1>.bmp` (180x80) sits in the middle tablet at (232, 200).  The click sound
plays on the mouse press of an enabled button, the action runs on the release over the same button.  A disabled button shows no highlight and
does nothing.  The window has no child widgets, so the exe has no key handling here (INFERRED) and neither has the engine; there is no options entry (CONFIRMED: the
options windows open only from the in-game menu, `0x485cc4`, `0x485bf3`)."""

import numpy as np

from allods2.graphics import load_bmp

from .events import Move, Press, Release
from .scene import Image, Scene
from .screen import Screen

DIR = "main/graphics/MainMenu/"
CLICK = "sfx/chrgen/ok.wav"                 # `SFX\ChrGen\Ok.wav` (0x5f4e7c, played by 0x4a815f)
CAPTION_AT = (0xE8, 200)                    # the middle tablet (0x4a7b3f)

#            name,           (x, y, w, h) of button%d.bmp, target screen (None = not built yet)
BUTTONS = (("NEW GAME",     (204, 52, 104, 96), "newgame"),
           ("MULTI PLAYER", (124, 156, 108, 76), None),
           ("CUT SCENES",   (124, 252, 96, 88), None),
           ("CREDITS",      (208, 340, 100, 100), None),
           ("LOAD GAME",    (340, 52, 88, 100), "load"),
           ("SERVER",       (424, 152, 84, 88), None),
           ("HALL OF FAME", (412, 260, 96, 84), None),
           ("EXIT",         (344, 348, 72, 80), "quit"))
N = len(BUTTONS)
# DECISION: what is not built yet is disabled in the original's own way (no highlight, no click); bit n = button n.  Load game stays
# disabled until the Save / load step (the exe disables it too when there is no `game*.sav`, `FUN_0043ff4a`, mask bit 0x10).
DISABLED = 0b01111110                       # all but New game (bit 0) and Exit (bit 7)


def mask_index(value):
    """Mask pixel value -> button index or -1 (`0x4a7d0d`: `0x80 + 0x10 n`)."""
    return (value - 0x80) >> 4 if value >= 0x80 and value & 0x0F == 0 and (value - 0x80) >> 4 < N else -1


class MainMenu(Screen):
    name = "menu"
    music = "menu"

    def __init__(self, shell):
        super().__init__(shell)
        self.mask = None
        self.disabled = DISABLED
        self.under = self.pressed = -1

    def _load(self):
        if self.mask is None:
            m = load_bmp(DIR + "MenuMask.bmp", self.shell.fs)
            self.mask = np.asarray(m.index if m.index is not None else m.rgb[..., 0])

    def enter(self, **params):
        self._load()
        self.under = self.pressed = -1

    def enabled(self, n):
        return n >= 0 and not (self.disabled >> n) & 1

    @property
    def hover(self):
        """The highlighted button (`+0xf0`): the one under the pointer unless another is held; disabled ones never."""
        h = self.under if self.pressed in (-1, self.under) else -1
        return h if self.enabled(h) else -1

    def _at(self, x, y):
        ox, oy = self.origin
        x, y = x - ox, y - oy
        if 0 <= x < 640 and 0 <= y < 480:
            return mask_index(int(self.mask[y, x]))
        return -1

    def event(self, ev):
        if isinstance(ev, Move):
            self.under = self._at(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.under = self._at(ev.x, ev.y)
            if self.enabled(self.under):
                self.pressed = self.under
                self.shell.play(CLICK)                  # only a press on an enabled button (0x4a815f)
        elif isinstance(ev, Release) and ev.button == 1:
            self.under = self._at(ev.x, ev.y)
            hit = self.pressed
            self.pressed = -1
            if hit >= 0 and hit == self.under and self.enabled(hit):
                return BUTTONS[hit][2]
        return None

    def scene(self):
        ox, oy = self.origin
        ops = [Image(DIR + "menu_.bmp", ox, oy)]
        h = self.hover
        if h >= 0:
            x, y, _, _ = BUTTONS[h][1]
            held = self.pressed == h
            ops.append(Image(DIR + "button%d%s.bmp" % (h + 1, "" if held else "p"), ox + x, oy + y))
        if self.under >= 0:
            ops.append(Image(DIR + "text%d.bmp" % (self.under + 1), ox + CAPTION_AT[0], oy + CAPTION_AT[1]))
        return Scene(ops)
