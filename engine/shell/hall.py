"""The HALL OF FAME screen (message `0x429`, m3; docs/engine/hall.md): `famehall\\hall.bmp` with the table of `famehall.dat` (rank, name, score) and an OK button.

Window class vtable `0x5cd288`, ctor `0x45b695` (resource `0x4b0`, stored at `game+0x11c`), layout `0x45b90e`, show `0x45bb82`, paint `0x45c159`, mouse move / down / up
`0x45bf50` / `0x45c023` / `0x45c0d3`, close `0x45c3d7` (message `0x445`; the child-closed handler `0x489505` posts `0x421`, the menu).  Row i of the table sits at
`y = 0x91 + trunc(i * 1.5 * line height of font4)`; the columns are the rank `"%d."` at x `0x91` (width 25), the name at x `0xaf` (width 200), both left aligned in the brown
gradient (`0x620e80`, 65 / 47 / 20), and the score `"%d"` with thousands separators (`0x475263`) right aligned at `0x181 + 100`, purple (`0x620e38`, 101 / 39 / 61); font4,
shadow 1.  The OK button is the 44x32 rect at (560, 416) with no picture of its own: a pointer over it draws `Ok_l_off.bmp` there, a held button `Ok_l_on.bmp`; the press plays
`SFX\\ChrGen\\Ok.wav` (`0x45c090`), the release over it closes.  No music request (the exe leaves the playing music alone).  Keys: the exe's window has none (slot `0x6c` =
`0x4dc326`, Tab / arrows); DECISION: Esc and Enter close as well, like every other dialog."""

from .events import Key, Move, Press, Release
from .scene import Image, Scene, Text
from .screen import Screen

BACKGROUND = "main/graphics/famehall/hall.bmp"
OK_OFF = "graphics/interface/Docs/OK/Ok_l_off.bmp"
OK_ON = "graphics/interface/Docs/OK/Ok_l_on.bmp"
OK_RECT = (0x230, 0x1A0, 44, 32)               # `+0xa8`: (560, 416), size (0x2c, 0x20)
CLICK = "sfx/chrgen/ok.wav"                    # `+0xc8`, loaded by `0x45bea2` from `0x5f1080`
TOP = 0x91
RANK_X, NAME_X, SCORE_RIGHT = 0x91, 0xAF, 0x181 + 100
STEP = 1.5                                      # `0x5cd310`
FONT = 4
BROWN = (65, 47, 20)                            # `0x620100` -> `DAT_00620e80`
PURPLE = (101, 39, 61)                          # `0x61fcc8` -> `DAT_00620e38`
FALLBACK_LINE = 17


def thousands(n):
    """`"%d"` after `FUN_00475263`: a comma every three digits from the right (a number of at most 3 digits, or a signed one of 4 characters, stays as it is)."""
    return "{:,}".format(int(n))


class Hall(Screen):
    name = "hall"
    music = None

    def enter(self, **params):
        sh = self.shell
        self.entries = list(sh.load_hall().entries)
        self.line_h = self._line_height()
        self.under = False
        self.held = False

    def _line_height(self):
        if self.shell.fs is None:
            return FALLBACK_LINE
        try:
            from allods2.graphics import Font
            return Font.load("graphics/font4/font4", self.shell.fs).line_height()
        except Exception:                        # noqa: BLE001  no font (synthetic file systems)
            return FALLBACK_LINE

    def row_y(self, i):
        return TOP + int(i * STEP * self.line_h)

    def _inside(self, x, y):
        ox, oy = self.origin
        l, t, w, h = OK_RECT
        return ox + l <= x < ox + l + w and oy + t <= y < oy + t + h

    def event(self, ev):
        if isinstance(ev, Move):
            self.under = self._inside(ev.x, ev.y)           # `0x45bf50`: the pointer over the rect shows `Ok_l_off` (`Ok_l_on` with the button down)
        elif isinstance(ev, Press) and ev.button == 1:
            self.under = self._inside(ev.x, ev.y)
            if self.under:                                  # `0x45c023`: sound and the pressed picture
                self.held = True
                self.shell.play(CLICK)
        elif isinstance(ev, Release) and ev.button == 1:
            self.under = self._inside(ev.x, ev.y)
            self.held = False
            if self.under:                                  # `0x45c0d3` -> `0x45c3d7`
                return "menu"
        elif isinstance(ev, Key) and ev.name in ("escape", "return"):
            return "menu"
        return None

    def scene(self):
        ox, oy = self.origin
        ops = [Image(BACKGROUND, ox, oy)]
        if self.under:
            ops.append(Image(OK_ON if self.held else OK_OFF, ox + OK_RECT[0], oy + OK_RECT[1]))
        for i, e in enumerate(self.entries):
            y = oy + self.row_y(i)
            ops.append(Text("%d." % (i + 1), ox + RANK_X, y, FONT, BROWN, 0, 1))
            ops.append(Text(e.name, ox + NAME_X, y, FONT, BROWN, 0, 1))
            ops.append(Text(thousands(e.a), ox + SCORE_RIGHT, y, FONT, PURPLE, 1, 1))
        return Scene(ops)
