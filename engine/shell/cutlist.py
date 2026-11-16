"""The main menu's CUT SCENES window (message `0x43b`, m1; docs/engine/cutscenes.md 5, REA cutscenes-rea.md 5): the main-menu picture under a 392x360 dialog that lists the
chapter videos seen so far (one row per set bit of the seen mask, ascending, titled by `cutscene.txt` line = bit number); Ok plays the selected one and re-opens the list,
Cancel / Esc go back to the menu.  QUIRK (CONFIRMED `0x48a7f4`): Ok passes the **row index** to the player, not the bit number, so a sparse mask replays the wrong video
for the rows past the gap (`ROW_IS_CODE`; the original's behaviour is kept)."""

from engine import cutscene as C

from .dialog import SHADOW
from .events import Key, Move, Press, Release, Wheel
from .options import UI_SOUND
from .saveload import FONT, LISTED, ROW, Fonts, SlotList, Texts, in_rect
from .scene import Button, Fill, Frame, Image, Scene, Text
from .screen import Screen

SIZE = (392, 360)                           # the snapped size of the constructor rect (100, 0x1e, 0x21c, 0x1c2) (ui-layout 11.4)
LEFT = 0x28
ROW_IS_CODE = True                          # the exe's argument of `0x48f919` is the row index


def rows_of(mask, titles):
    """`[(bit, title)]` of the set bits 0..31 ascending (`0x487bfb`); a bit past the last title line gets an empty title."""
    return [(n, titles[n] if n < len(titles) else "") for n in range(32) if (mask >> n) & 1]


class CutList(Screen):
    name = "cutlist"
    music = None

    def enter(self, **params):
        sh = self.shell
        self.texts, self.fonts = Texts(sh.fs), Fonts(sh.fs)
        self.fx, self.fy = (sh.size[0] - SIZE[0]) >> 1, (sh.size[1] - SIZE[1]) >> 1
        self.rows = rows_of(sh.settings.videos_seen, C.cut_titles(sh.fs) if sh.fs is not None else [])
        w, h = SIZE
        self.list = SlotList((LEFT, 0x44, w - 2 * LEFT - 0x18, h - 0x70 - 0x44), [t for _, t in self.rows])
        self.list.set_rows([t for _, t in self.rows], getattr(sh, "cut_selected", 0))           # the global `DAT_00622820`: row 0 at first, then the last Ok
        self.hot = self.pressed = None

    # -- geometry (relative to the dialog) -----------------------------------------------------------------------------------------
    def button_rects(self):
        w, h = SIZE
        return [(w // 7, h - 0x3C, 3 * w // 7 - w // 7, 24), (4 * w // 7, h - 0x3C, 6 * w // 7 - 4 * w // 7, 24)]

    def abs(self, r):
        return (self.fx + r[0], self.fy + r[1], r[2], r[3])

    def _button_at(self, x, y):
        for i, r in enumerate(self.button_rects()):
            if in_rect(self.abs(r), x, y):
                return i
        return None

    # -- input ---------------------------------------------------------------------------------------------------------------------
    def _ok(self):
        if not self.rows:
            return "menu"
        sel = self.list.sel
        self.shell.cut_selected = sel                           # written by Ok only
        code = sel if ROW_IS_CODE else self.rows[sel][0]
        return "cutscene", {"codes": [code], "then": "cutlist"}

    def event(self, ev):
        if isinstance(ev, Move):
            self.hot = self._button_at(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.hot = self.pressed = self._button_at(ev.x, ev.y)
            if self.pressed is not None:
                self.shell.play(UI_SOUND)
            row = self.list.row_at(ev.x - self.fx, ev.y - self.fy)
            if row is not None:
                self.list.sel = row
        elif isinstance(ev, Release) and ev.button == 1:
            hit, down, self.pressed = self._button_at(ev.x, ev.y), self.pressed, None
            self.hot = hit
            if hit is not None and hit == down:
                return self._ok() if hit == 0 else "menu"
        elif isinstance(ev, Wheel):                             # DECISION: the exe has no wheel code (no `0x20a` anywhere); kept as a modern convenience
            self.list.scroll(-1 if ev.dy > 0 else 1)
        elif isinstance(ev, Key) and not ev.ctrl:
            if ev.name == "escape":
                return "menu"                                   # `0x446`
            if ev.name == "return":
                return self._ok()
            if ev.name in ("up", "down") and self.rows:
                self.list.sel = max(0, min(self.list.sel + (1 if ev.name == "down" else -1), len(self.rows) - 1))
                self.list.show()
            elif ev.name in ("pageup", "pagedown") and self.rows:      # list slot `0x4d8fdb`: PageUp / PageDown / Up / Down only; Home / End / Left / Right do nothing
                (self.list.page_up if ev.name == "pageup" else self.list.page_down)()
        return None

    # -- drawing -------------------------------------------------------------------------------------------------------------------
    def scene(self):
        from .mainmenu import DIR
        ox, oy = self.origin
        ops = [Image(DIR + "menu_.bmp", ox, oy), Frame(self.fx, self.fy, *SIZE)]
        w = SIZE[0]
        ops.append(Text(self.texts("d", 0x99), self.fx + w // 2, self.fy + 0x20 + 3, FONT, "normal", 2, 1))
        lx, ly, lw, lh = self.abs(self.list.rect)
        ops += [Fill(lx - 1, ly - 1, lw + 2, lh + 2, (90, 70, 40)), Fill(lx, ly, lw, lh, (20, 16, 12))]
        for k in range(self.list.visible):
            i = self.list.top + k
            if i >= len(self.list.rows):
                break
            y = ly + k * ROW
            if i == self.list.sel:
                ops.append(Fill(lx, y, lw, ROW, (80, 60, 28)))
            ops.append(Text(self.fonts.fit(self.list.rows[i], lw - 8), lx + 4, y + 1, FONT, "highlight" if i == self.list.sel else LISTED, 0, 1))
        n = len(self.list.rows)
        ops.append(Fill(lx + lw, ly, 24, lh, (36, 28, 18)))
        if n > self.list.visible:
            th = max(12, lh * self.list.visible // n)
            ty = ly + (lh - th) * self.list.top // (n - self.list.visible)
            ops.append(Fill(lx + lw + 3, ty, 18, th, (130, 100, 56)))
        for i, (r, label) in enumerate(zip(self.button_rects(), (self.texts("d", 0), self.texts("d", 1)))):
            ops.append(Button(*self.abs(r), label, True, self.hot == i, self.pressed == i))
        return Scene(ops)
