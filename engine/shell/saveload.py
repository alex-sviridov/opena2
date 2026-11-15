"""The Save / Load / Delete windows (docs/engine/save-ui.md; L10d).  Components over a screen (the town scene's menu, the main menu's `load` screen), not screens of their own.

* `SaveDialog` = `FUN_0043ebf6` (class `0x5cbe50`, build slot `FUN_0043ece0`, message handler `0x43f8da`): caption "Save Game", the edit field for the description, the label "Saved Games",
  the list (row 0 = the new file, empty), Ok / Delete / Cancel.  Selecting a row copies its description into the field; Ok is disabled while the field is empty; Ok saves to the
  selected row's file (the typed text equal to a listed description selects that row: `saveslots.choose_target`); Delete asks a Yes / No window and removes the file.
* `LoadDialog` = `FUN_0043deaf` (class `0x5cbdc8`, build slot `0x43df48`, handler `0x43e7f0`): caption "Load Saved Game", the label "Load Game", the list (newest first, the two
  auto-saves included), Ok / Delete / Cancel; Ok and Delete are disabled while the list is empty.
* `Notice` / `Confirm` = the text window family `FUN_00444243` (case 4: Yes / No `main 0x4b / 0x4c`, results `0x447` / `0x448`; one Ok button for a notice), geometry `widgets.text_window`.

Every window is 488x360 (500x420 snapped, `FUN_004dc4fc`) centred on the screen; the rects are relative to its top-left (CONFIRMED from the build slots, listed in save-ui.md).  The look of the
list rows, the edit field and the scroll bar (the exe's `FUN_004d82f8` list class, `FUN_004d601b` edit) is not read from the binary: flat boxes (INFERRED, needs eyes)."""

import struct
import time

from engine import saveslots as SS
from engine.ui import widgets as W

from .events import Key, Move, Press, Release, Wheel
from .options import UI_SOUND, load_texts
from .scene import Button, Fill, Frame, Image, Scene, Text

SIZE = (488, 360)                           # the snapped size of the constructor rect (100, 0x1e, 600, 0x1c2)
LEFT = 0x28                                 # every child starts here and ends `0x28` from the right edge (list `0x40`: the scroll bar takes the rest)
ROW = W.FONT1_PITCH                         # the list's row pitch (INFERRED: font1 pitch 17)
FONT = 1
EDIT_MAX = 0xFF                             # INFERRED: the description buffer is 256 bytes (`0x43f8da` `local_130[256]`); the exe's edit limit is not read
BLINK_MS = 500
LISTED = "normal"

FALLBACK = {("d", 0): "Ok", ("d", 1): "Cancel", ("d", 0x9D): "Delete", ("d", 0x1D): "Save Game", ("d", 0x90): "Saved Games", ("d", 0x97): "Load Saved Game", ("d", 0x18): "Load Game",
            ("m", 0x4B): "Yes", ("m", 0x4C): "No", ("p", 0x32): "Are you sure you want to delete game '", ("p", 0x33): "' ?",
            ("p", 0x37): "Restart last mission", ("p", 0x5F): "Abort mission and return to town"}
NOT_SUPPORTED = "Loading a saved mission is not supported yet."          # only a `Shell` without a `mission_codec` (L10e-B sets it)


class Texts:
    """`dialogs.txt` ("d"), `main.txt` ("m") and `patch.txt` ("p") lines with the exe's English text as the fallback (no install)."""

    def __init__(self, fs):
        from engine.ui.orders import MainText
        t = load_texts(fs)
        self.t = {"d": t["dialogs"], "p": t["patch"], "m": MainText.load(fs) if fs is not None else MainText()}

    def __call__(self, table, i):
        return self.t[table].line(i) or FALLBACK.get((table, i), "")


class Fonts:
    """font1 measure / wrap (our line rule); 6 px per character without an install."""

    def __init__(self, fs):
        self.font = None
        if fs is not None:
            try:
                from allods2.graphics import Font
                self.font = Font.load("graphics/font1/font1", fs)
            except Exception:                           # noqa: BLE001  no font (synthetic file systems)
                self.font = None

    def measure(self, text):
        if self.font is None:
            return 6 * len(text)
        from allods2.graphics.font import font_bytes
        return self.font.measure(font_bytes(text))

    def wrap(self, text, width):
        if self.font is None:
            return text.split("\n")
        return [b.decode("cp866", "replace") if isinstance(b, bytes) else b for b in self.font.wrap(text, width)]

    def fit(self, text, width, tail=False):
        """`text` cut to `width` px (from the right, or from the left with `tail`)."""
        while text and self.measure(text) > width:
            text = text[1:] if tail else text[:-1]
        return text


def frame_origin(size):
    return (size[0] - SIZE[0]) >> 1, (size[1] - SIZE[1]) >> 1


def in_rect(r, x, y):
    return r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]


class TextBox:
    """The text window family on the screen: `kind` "notice" (one Ok, `0x445`) or "confirm" (Yes / No: result `0x447` / `0x448`).  `event` returns True (Yes / Ok), False (No / ESC) or None."""

    def __init__(self, texts, fonts, size, message, kind):
        self.message, self.kind, self.fonts, self.texts = message, kind, fonts, texts
        raw = (316, 494) if kind == "confirm" else (576, 384)           # the delete confirmation's constructor rect (0x40, 100, 0x17c, 0x252); the pause window's for a notice
        n = 2 if kind == "confirm" else 1
        self.geo = W.text_window(raw, lambda w: len(fonts.wrap(message, w)), False, n)
        self.x, self.y = (size[0] - self.geo.w) >> 1, (size[1] - self.geo.h) >> 1
        self.labels = [texts("m", 0x4B), texts("m", 0x4C)] if kind == "confirm" else [texts("d", 0)]
        self.hot = self.pressed = None

    def rects(self):
        return [(self.x + r[0], self.y + r[1], r[2], r[3]) for r in self.geo.buttons]

    def _at(self, x, y):
        for i, r in enumerate(self.rects()):
            if in_rect(r, x, y):
                return i
        return None

    def event(self, ev):
        if isinstance(ev, Move):
            self.hot = self._at(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.hot = self.pressed = self._at(ev.x, ev.y)
        elif isinstance(ev, Release) and ev.button == 1:
            hit, down, self.pressed = self._at(ev.x, ev.y), self.pressed, None
            self.hot = hit
            if hit is not None and hit == down:
                return hit == 0
        elif isinstance(ev, Key) and not ev.ctrl:
            if ev.name == "escape":
                return False                                  # `FUN_004dc595`: ESC = message `0x446`
            if ev.name == "return":
                return True if self.kind == "notice" else None    # Enter acts on the focused button only (`FUN_004d5f0f`); the first button has the initial focus (shell.md)
        return None

    def ops(self):
        g = self.geo
        ops = [Frame(self.x, self.y, g.w, g.h)]
        tx, ty, tw, _ = g.text
        for n, line in enumerate(self.fonts.wrap(self.message, tw)):
            ops.append(Text(line, self.x + tx, self.y + ty + W.FONT1_PITCH * n, FONT, LISTED, 0, 1))
        for i, (r, label) in enumerate(zip(self.rects(), self.labels)):
            ops.append(Button(*r, label, True, self.hot == i, self.pressed == i))
        return ops


class SlotList:
    """The list box: rows of text, one selected, scrolled by whole rows."""

    def __init__(self, rect, rows=()):
        self.rect = rect                                  # (x, y, w, h) relative to the dialog
        self.rows = list(rows)
        self.sel = 0
        self.top = 0

    @property
    def visible(self):
        return max(1, self.rect[3] // ROW)

    def set_rows(self, rows, sel=None):
        self.rows = list(rows)
        self.sel = max(0, min(self.sel if sel is None else sel, len(self.rows) - 1))
        self.top = min(self.top, max(0, len(self.rows) - self.visible))
        self.show()

    def show(self):
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + self.visible:
            self.top = self.sel - self.visible + 1

    def scroll(self, d):
        self.top = max(0, min(self.top + d, max(0, len(self.rows) - self.visible)))

    def row_at(self, x, y):
        rx, ry, rw, rh = self.rect
        if not (rx <= x < rx + rw and ry <= y < ry + rh):
            return None
        i = self.top + (y - ry) // ROW
        return i if i < len(self.rows) else None


class SlotDialog:
    """What the two dialogs share: geometry, the list, the buttons (Ok / Delete / Cancel at 3W/20..7W/20, 8W/20..12W/20, 13W/20..17W/20), the nested Yes / No window.  Subclasses give
    `rows()`, `select`, `ok()`, `delete_text()` and the draw of their header."""

    def __init__(self, shell, slots, hidden):
        self.shell, self.slots_dir, self.hidden = shell, slots, hidden
        self.texts, self.fonts = Texts(shell.fs), Fonts(shell.fs)
        self.fx, self.fy = frame_origin(shell.size)
        self.slots = []
        self.box = None                                   # the open Yes / No / notice window
        self.confirm_file = None
        self.hot = self.pressed = None
        self.blink_ms = 0
        self.blink_on = True
        self.list = SlotList(self.list_rect())
        self.refresh()

    # -- geometry (relative to the dialog) ------------------------------------------------------------------------------------------------
    list_y, list_h, button_y = 0, 0, 0

    def list_rect(self):
        return (LEFT, self.list_y, SIZE[0] - 0x68, self.list_h)

    def button_rects(self):
        w = SIZE[0]
        return [(3 * w // 20, self.button_y, 7 * w // 20 - 3 * w // 20, 24), (8 * w // 20, self.button_y, 12 * w // 20 - 8 * w // 20, 24),
                (13 * w // 20, self.button_y, 17 * w // 20 - 13 * w // 20, 24)]

    def abs(self, r):
        return (self.fx + r[0], self.fy + r[1], r[2], r[3])

    # -- model ------------------------------------------------------------------------------------------------------------------------
    def refresh(self, sel=None):
        self.slots = self.slots_dir.scan(include_hidden=not self.hidden) if self.slots_dir is not None else []
        self.list.set_rows(self.rows(), sel)

    def rows(self):
        return [SS.entry_text(s) for s in self.slots]

    def enabled(self):
        """(Ok, Delete, Cancel) enable flags."""
        raise NotImplementedError

    def delete_file(self):
        """The slot the Delete button acts on (None = nothing)."""
        raise NotImplementedError

    def ok(self):
        raise NotImplementedError

    def selected(self, i):
        self.list.sel = i
        self.list.show()

    def start_delete(self):
        s = self.delete_file()
        if s is None:
            return
        msg = self.texts("p", 0x32) + s.description + self.texts("p", 0x33)
        self.confirm_file = s.name
        self.box = TextBox(self.texts, self.fonts, self.shell.size, msg, "confirm")

    def finish_delete(self):
        name, self.confirm_file = self.confirm_file, None
        if name is not None:
            try:
                self.slots_dir.delete(name)
            except OSError as e:
                self.box = TextBox(self.texts, self.fonts, self.shell.size, "%s: %s" % (name, e.strerror or e), "notice")
        self.refresh(self.list.sel)
        self.after_delete()

    def after_delete(self):
        pass

    def notice(self, text):
        self.box = TextBox(self.texts, self.fonts, self.shell.size, text, "notice")

    # -- input --------------------------------------------------------------------------------------------------------------------------
    def _button_at(self, x, y):
        for i, r in enumerate(self.button_rects()):
            if in_rect(self.abs(r), x, y):
                return i
        return None

    def _act(self, i):
        ok, delete, cancel = self.enabled()
        if i == 0 and ok:
            return self.ok()
        if i == 1 and delete:
            self.start_delete()
        elif i == 2:
            return ("close",)
        return None

    def event(self, ev):
        """None, or ("close",) / ("save", file, description) / ("load", file)."""
        if self.box is not None:
            r = self.box.event(ev)
            if r is None:
                return None
            kind, self.box = self.box.kind, None
            if kind == "confirm" and r:
                self.finish_delete()
            return None
        if isinstance(ev, Move):
            self.hot = self._button_at(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.hot = self.pressed = self._button_at(ev.x, ev.y)
            if self.pressed is not None and self.enabled()[self.pressed]:
                self.shell.play(UI_SOUND)
            row = self.list.row_at(ev.x - self.fx, ev.y - self.fy)
            if row is not None:
                self.select(row)
        elif isinstance(ev, Release) and ev.button == 1:
            hit, down, self.pressed = self._button_at(ev.x, ev.y), self.pressed, None
            self.hot = hit
            if hit is not None and hit == down:
                return self._act(hit)
        elif isinstance(ev, Wheel):
            self.list.scroll(-1 if ev.dy > 0 else 1)
        elif isinstance(ev, Key) and not ev.ctrl:
            if ev.name == "escape":
                return ("close",)                              # message `0x446`
            if ev.name == "return":
                return self._act(0)                            # `0x444` = the same case as Ok (`0x43f8da`)
            if ev.name in ("up", "down") and self.rows_count():
                self.select(max(0, min(self.list.sel + (1 if ev.name == "down" else -1), self.rows_count() - 1)))
            else:
                return self.key(ev)
        return None

    def key(self, ev):
        return None

    def rows_count(self):
        return len(self.list.rows)

    def select(self, i):
        self.selected(i)

    def update(self, dt_ms):
        self.blink_ms += dt_ms
        if self.blink_ms > BLINK_MS:
            self.blink_ms -= BLINK_MS
            self.blink_on = not self.blink_on

    # -- drawing ------------------------------------------------------------------------------------------------------------------------
    def head_ops(self):
        return []

    def ops(self):
        ox, oy = self.fx, self.fy
        ops = [Frame(ox, oy, *SIZE)]
        ops += self.head_ops()
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
        n = len(self.list.rows)                               # the scroll bar: a track at the right of the list and a thumb (drawn only when rows scroll)
        sx = lx + lw
        ops.append(Fill(sx, ly, 24, lh, (36, 28, 18)))
        if n > self.list.visible:
            th = max(12, lh * self.list.visible // n)
            ty = ly + (lh - th) * self.list.top // (n - self.list.visible)
            ops.append(Fill(sx + 3, ty, 18, th, (130, 100, 56)))
        flags = self.enabled()
        for i, (r, label) in enumerate(zip(self.button_rects(), (self.texts("d", 0), self.texts("d", 0x9D), self.texts("d", 1)))):
            ops.append(Button(*self.abs(r), label, flags[i], self.hot == i and flags[i], self.pressed == i and flags[i]))
        if self.box is not None:
            ops += self.box.ops()
        return ops

    def scene_ops(self):
        return self.ops()


class SaveDialog(SlotDialog):
    list_y, list_h, button_y = 0x80, 0x90, 0x110 + 0x18

    def __init__(self, shell, slots):
        self.text = ""
        super().__init__(shell, slots, hidden=True)

    def rows(self):
        return [""] + [SS.entry_text(s) for s in self.slots]          # row 0 = the new file (`Add(&DAT_0061b1fc)`: the empty entry)

    def enabled(self):
        return bool(self.text), len(self.slots) > 0 and self.list.sel > 0, True

    def delete_file(self):
        return self.slots[self.list.sel - 1] if self.list.sel > 0 else None          # `0x43f8da`: `if (sel != 0)` (row 0 cannot be deleted)

    def selected(self, i):
        """`0x46e` (list selection): the description of the row goes into the field (row 0 clears it)."""
        super().selected(i)
        self.text = self.slots[i - 1].description if i > 0 else ""

    def after_delete(self):
        self.selected(self.list.sel)                      # the exe re-sends the selection message for the new selected row (`0x46e`)

    def target(self):
        return SS.choose_target(self.text, self.list.sel, self.slots)

    def ok(self):
        t = self.target()
        if t is None:
            return None
        row, name, description = t
        self.list.sel = row
        return ("save", name, description)

    def key(self, ev):
        if ev.name == "backspace":
            self.text = self.text[:-1]
        elif ev.char and len(self.text.encode(SS.ENCODING, "replace")) < EDIT_MAX:
            self.text += ev.char
        else:
            return None
        self.blink_ms, self.blink_on = 0, True
        return None

    def head_ops(self):
        w = SIZE[0]
        ox, oy = self.fx, self.fy
        ops = [Text(self.texts("d", 0x1D), ox + w // 2, oy + 0x20 + 3, FONT, "normal", 2, 1)]
        ex, ey, ew, eh = self.abs((LEFT, 0x44, w - 0x50, 0x18))
        ops += [Fill(ex - 1, ey - 1, ew + 2, eh + 2, (90, 70, 40)), Fill(ex, ey, ew, eh, (20, 16, 12))]
        shown = self.fonts.fit(self.text, ew - 12, tail=True)
        ops.append(Text(shown + ("|" if self.blink_on else ""), ex + 4, ey + 4, FONT, "normal", 0, 1))
        ops.append(Text(self.texts("d", 0x90), ox + LEFT, oy + 0x68 + 3, FONT, "normal", 0, 1))
        return ops


class LoadDialog(SlotDialog):
    list_y, list_h, button_y = 0x5C, 0xC0, 0x11C + 0x18

    def __init__(self, shell, slots):
        super().__init__(shell, slots, hidden=False)

    def enabled(self):
        has = bool(self.slots)
        return has, has, True                              # `0x43df48`: Ok and Delete off when the list is empty

    def delete_file(self):
        return self.slots[self.list.sel] if self.slots else None

    def ok(self):
        """`0x444` / `0x479`: a selection below 0 closes as a cancel; else the file of the selected row."""
        if not self.slots:
            return ("close",)
        return ("load", self.slots[self.list.sel].name)

    def head_ops(self):
        w = SIZE[0]
        ox, oy = self.fx, self.fy
        return [Text(self.texts("d", 0x97), ox + w // 2, oy + 0x20 + 3, FONT, "normal", 2, 1), Text(self.texts("d", 0x18), ox + LEFT, oy + 0x44 + 3, FONT, "normal", 0, 1)]


# -- the main menu's LOAD screen ---------------------------------------------------------------------------------------------------------------------------------------------------

REFUSED = (Exception,)                  # a damaged file may fail anywhere inside the typed readers / the world rebuild: every failure is a notice, never a crash


def refusal(e):
    """The notice text of a load failure: the reader's own message ("Invalid save file", "Outdated save file", the multiplayer text), else "Invalid save file (detail)"."""
    from engine import savegame
    text = str(e) or type(e).__name__
    if not isinstance(e, savegame.S.MultiplayerSave) and not text.startswith(("Invalid save file", "Outdated save file")):
        text = "Invalid save file (%s)" % text[:160]
    return text


def load_file(shell, name):
    """Load a slot into the shell (the exe's `0x419` -> `FUN_0048db37`).  Returns `("ok", screen)` (the screen the shell goes to) or `("error", text)` for a notice: an unreadable / refused
    file (the reader's own messages: "Invalid save file", "Outdated save file", multiplayer saves), a damaged one (any failure of the readers, no matter its kind), a mission-kind file
    without a `MissionSaveCodec`.  **Nothing of the shell changes unless the load succeeded**, so a refused file leaves the running game / the dialog as it was (DECISION: the exe goes to the
    main menu, `FUN_0040d480` failing posts `0x421`; the engine parses before it replaces anything, so staying is safe: save-ui 3)."""
    from engine import savegame
    try:
        save = savegame.S.parse_save(shell.slots.read(name))
        mission = savegame.kind(save) == "mission"
        if mission:
            codec = shell.mission_codec
            if codec is None:
                return "error", NOT_SUPPORTED
            params = codec.load(save, install=shell.fs)
        else:
            game = savegame.from_save(save, install=shell.fs, seed=time.time_ns() & 0xFFFFFFFF, resume_location=True)
        return "ok", (shell.resume_mission(params) if mission else shell.resume(game))
    except RecursionError:
        return "error", "Invalid save file (nested too deeply)"
    except MemoryError:
        return "error", "Invalid save file (too large)"
    except REFUSED as e:
        return "error", refusal(e)


from .screen import Screen  # noqa: E402


class LoadGame(Screen):
    """The main menu's LOAD button (message `0x418` with no game running): the main menu picture under the Load window; Cancel goes back to the menu (`0x421`), Ok loads."""
    name = "load"
    music = None

    def __init__(self, shell):
        super().__init__(shell)
        self.dialog = None

    def enter(self, **params):
        self.dialog = LoadDialog(self.shell, self.shell.slots)

    def exit(self):
        self.dialog = None

    def event(self, ev):
        d = self.dialog
        if d is None:
            return "menu"
        out = d.event(ev)
        if out is None:
            return None
        if out[0] == "close":
            return "menu"
        status, res = load_file(self.shell, out[1])
        if status == "error":
            d.notice(res)
            return None
        return res

    def update(self, dt_ms):
        if self.dialog is None:
            return "menu"
        self.dialog.update(dt_ms)
        return None

    def scene(self):
        from .mainmenu import DIR
        ox, oy = self.origin
        ops = [Image(DIR + "menu_.bmp", ox, oy)]
        if self.dialog is not None:
            ops += self.dialog.ops()
        return Scene(ops)
