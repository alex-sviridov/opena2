"""The CREDITS screen (message `0x428`, m2; docs/engine/credits.md, REA in that file): `main\\text\\credits.txt` scrolls up the black screen, `music\\credit.wav` plays,
the cursor is hidden.  One pixel per tick, a tick every 23 ms or more (`0x43bcac`, timeGetTime); the text starts 480 px down.  A line starting with `"` is a picture
(`main\\graphics\\logo\\<name>`) centred on x + 320, any other line is font1 text centred on x + 320: the highlight table (`0x61fa80`) for line 0 and for a line after an
empty line, the normal table (`0x620928`) otherwise.  The scroll ends when the first visible line is past the last line, and any key press or button press ends it earlier
(INFERRED, `0x43bc74` / `0x43bc95` both call the close at `0x43c2d2`, which posts `0x445`).  Close -> the menu (the hall of fame `0x429` is not built)."""

from allods2.text import decode_text

from .events import Key, Press
from .scene import Image, Scene, Text
from .screen import Screen

TEXT = "main/text/credits.txt"
LOGO = "main/graphics/logo/"
TICK_MS = 23                                # `0x43bd50`: a step needs `timeGetTime() - last >= 0x17`
START = 0x1e0                               # `+0x9c` at the screen's start (`0x43bb8a`): the text begins one screen height down
FONT = 1
FALLBACK_LINE = 15                          # without an install


def credit_lines(fs):
    """The lines of `credits.txt` (CR-split like the exe's loader `0x474585`, trailing blank lines kept)."""
    try:
        return decode_text(fs.read(TEXT)).replace("\r\n", "\n").split("\n")
    except (KeyError, OSError, AttributeError):
        return []


class Credits(Screen):
    name = "credits"
    music = "credit"

    def enter(self, **params):
        sh = self.shell
        self.lines = credit_lines(sh.fs) if sh.fs is not None else []
        self.line_h = self._line_height()
        self.offset = START                      # `+0x9c`, falls by 1 per tick
        self.acc = 0.0
        self.widths = {}                         # picture name -> width (centring)

    def _line_height(self):
        if self.shell.fs is None:
            return FALLBACK_LINE
        try:
            from allods2.graphics import Font
            return Font.load("graphics/font1/font1", self.shell.fs).line_height()
        except Exception:                        # noqa: BLE001  no font (synthetic file systems)
            return FALLBACK_LINE

    # -- the scroll ------------------------------------------------------------------------------------------------------------------
    @property
    def first(self):
        """`+0x98`: the first line that can be visible (`|offset| / line height` once the offset is negative)."""
        return 0 if self.offset >= 0 else -self.offset // self.line_h

    def last(self):
        return min(self.first + 480 // self.line_h + 1, len(self.lines))

    def done(self):
        return self.first >= len(self.lines)

    def update(self, dt_ms):
        self.acc += dt_ms
        while self.acc >= TICK_MS:
            self.acc -= TICK_MS
            self.offset -= 1
            if self.done():
                return "menu"
        return None

    def event(self, ev):
        if isinstance(ev, (Key, Press)):
            return "menu"
        return None

    # -- drawing ---------------------------------------------------------------------------------------------------------------------
    def _width(self, name):
        if name not in self.widths:
            try:
                from allods2.graphics.bmp import load_bmp
                self.widths[name] = load_bmp(LOGO + name, self.shell.fs).rgb.shape[1]
            except Exception:                    # noqa: BLE001  a missing picture is skipped by the exe as well (`0x5a0984` finds nothing)
                self.widths[name] = None
        return self.widths[name]

    def scene(self):
        ox, oy = self.origin
        ops = []
        for i in range(max(0, self.first - 10), self.last()):
            line = self.lines[i]
            y = oy + self.offset + i * self.line_h
            if line.startswith('"'):
                name = line.strip('"')
                w = self._width(name) if self.shell.fs is not None else None
                if w is not None:
                    ops.append(Image(LOGO + name, ox + 320 - w // 2, y))
            elif line:
                head = i == 0 or not self.lines[i - 1]
                ops.append(Text(line, ox + 320, y, FONT, "highlight" if head else "normal", 2, 1))
        return Scene(ops, cursor=False)
