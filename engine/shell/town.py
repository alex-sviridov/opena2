"""The town screens (docs/engine/town.md 3): the town scene (L6, the real one), the inn (L7, `engine/shell/inn.py`) and the shop (L8, `engine/shell/shop.py`),
driven by `engine.town.TownCore`: scene -> Inn / Shop / Leave (clicks on the regions), inn / shop -> Exit (ESC), Leave -> the map (`locations`).

Every click is a message to the core; the events it appends are turned into services here (`Shell.drain_town`)."""

from engine import town as T
from engine import townscene as TS

from engine.ui.layout import Rect
from engine.ui.widgets import button_rect

from . import dialog
from .events import Key, Move, Press, Release
from .options import SOUND, OptionsPages, load_texts
from .scene import Button, Fill, Frame, Image, Scene, Sprite, Text
from .screen import Screen
from .tipswin import TipsWindow

W, H = 360, 280
PAD, ROW, GAP = dialog.CORNER, 24, 6
CLICK = "sfx/chrgen/ok.wav"
TIPS_RECT = (0x148, 0, 0x280 - 0x148, 0xC8)       # the scene's tips window `0x4dec24(0x467, 0x148, 0, 0x280, 0xc8, text)` (`0x4ca8b5`, `0x4ce714`, `0x4d0e19`: the three scene classes alike), CONFIRMED
TIPS_OF_TOWN = {2: 12, 3: 11}                     # scene class of town 2 (Kaarg, `0x4d0d46`) -> `#tips12`, town 3 (druid, `0x4ce641`) -> `#tips11`, every other town (`0x4ca7e2`) -> `#tips1`


def tips_key(town):
    """The `town.txt` section a town scene's tips window shows (`FUN_004ddc9c(n)` at the scene load, CONFIRMED callers; the town to class mapping is town-hero 1)."""
    return "#tips%d" % TIPS_OF_TOWN.get(town, 1)


class TownPanel(Screen):
    """A dialog with a title and a column of buttons; subclasses give `title()`, `labels` and `act(i)`.  A button acts on the release over the pressed one."""
    view = ""                       # the `TownCore.view` this screen shows
    labels = ()

    def __init__(self, shell):
        super().__init__(shell)
        self.hot = self.pressed = None

    @property
    def core(self):
        return self.shell.town_core()

    def enter(self, **params):
        self.hot = self.pressed = None

    def title(self):
        return ""

    def frame_at(self):
        ox, oy = self.origin
        return ox + (640 - W) // 2, oy + (480 - H) // 2

    def buttons(self):
        fx, fy = self.frame_at()
        top = fy + 96
        return [(fx + PAD, top + i * (ROW + GAP), W - 8 - 2 * PAD, ROW, label) for i, label in enumerate(self.labels)]

    def _at(self, x, y):
        for i, (bx, by, bw, bh, _) in enumerate(self.buttons()):
            if bx <= x < bx + bw and by <= y < by + bh:
                return i
        return None

    def act(self, i):
        raise NotImplementedError

    def _do(self, i):
        self.shell.play(CLICK)
        self.act(i)
        return self.shell.town_screen()

    def event(self, ev):
        if isinstance(ev, Move):
            self.hot = self._at(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.hot = self.pressed = self._at(ev.x, ev.y)
        elif isinstance(ev, Release) and ev.button == 1:
            hit, down, self.pressed = self._at(ev.x, ev.y), self.pressed, None
            self.hot = hit
            if hit is not None and hit == down:
                return self._do(hit)
        elif isinstance(ev, Key) and not ev.ctrl and ev.name == "escape":
            return self.escape()
        return None

    def escape(self):
        return None

    def scene(self):
        fx, fy = self.frame_at()
        cx = fx + dialog.centre_x(W)
        ops = [Frame(fx, fy, W, H), Text(self.title(), cx, fy + 24, 2, "normal", 2, 1)]
        ops += [Button(x, y, w, h, label, True, self.hot == i, self.pressed == i) for i, (x, y, w, h, label) in enumerate(self.buttons())]
        return Scene(ops)


def ops_of(draw_ops, ox=0, oy=0):
    """`SceneState.draw_ops()` tuples -> `Image` / `Sprite` ops at the window origin `(ox, oy)`."""
    return [Image(op[1], ox + op[2], oy + op[3], op[4]) if op[0] == "bmp" else Sprite(op[1], op[2], ox + op[3], oy + op[4]) for op in draw_ops]


# The scene menu: message `0x41f` (CONFIRMED `FUN_004852d8` case `0x41f` -> `FUN_004407c2`: a 440x340 window at (100, 100), buttons in this order; ESC in a town scene posts it too, shell.md 3.5).
# (id, `dialogs.txt` line, enabled, action).  Save (`0x41a`, the save window `FUN_0043ebf6`) is enabled in a town; Load (`0x418`, `FUN_0043deaf`) iff a `game*.sav` exists (CONFIRMED
# `FUN_0043ff4a`); both windows are `engine/shell/saveload.py` (L10d).
MENU = (("save", 0x22, True), ("load", 0x23, True), ("sound", 0x25, True), ("abort", 0x4d, True), ("return", 0x28, True))
ABORT = (("exit_menu", 0x2c, True), ("exit_windows", 0x2d, True), ("return", 0x28, True))     # `0x41c` with `game+0x404 == 0` -> `FUN_00440a22`: messages `0x41e` (end game + main menu), `0x10`, `0x446`
FALLBACK = {0x22: "~Save Game", 0x23: "~Load Game", 0x25: "Sou~nd Options", 0x4d: "Abort Game", 0x28: "~Return to Game", 0x2c: "~Exit to Main Menu", 0x2d: "Exit to ~Windows"}
MENU_W, MENU_H = 392, 296                  # 440x340 snapped by `FUN_004dc4fc` (`w' = ((w - 8) / 0x60) * 0x60 + 8`, `h' = ((h - 0x68) / 0x40) * 0x40 + 0x68`)


class SceneMenu:
    """The window of message `0x41f` over a town scene: page "menu" (Save / Load / Sound Options / Abort Game / Return to Game) and, behind Abort Game, page "abort" (Exit to Main
    Menu / Exit to Windows / Return to Game).  Text buttons act on the release over the pressed one; ESC = Return (`0x446`, the common dialog's key).  `event` returns the outcome
    ("sound",) (open the sound options), ("exit_menu",), ("exit_windows",), ("close",) or None."""

    def __init__(self, texts, origin, save=True, load=True):
        self.texts = texts
        self.flags = {"save": save, "load": load}
        self.page = "menu"
        self.frame = Rect(origin[0] + (640 - MENU_W) // 2, origin[1] + (480 - MENU_H) // 2, MENU_W, MENU_H)
        self.hot = self.pressed = None

    def entries(self):
        if self.page != "menu":
            return ABORT
        return tuple((k, line, self.flags.get(k, en)) for k, line, en in MENU)

    def label(self, line):
        return (self.texts["dialogs"].line(line) if self.texts else "") or FALLBACK[line]

    def rects(self):
        return [button_rect(self.frame, k) for k in range(len(self.entries()))]

    def _at(self, x, y):
        for i, r in enumerate(self.rects()):
            if r.contains(x, y):
                return i
        return None

    def _act(self, i):
        key, _, enabled = self.entries()[i]
        if not enabled:
            return None
        if key == "abort":
            self.page, self.hot = "abort", None
            return None
        return ("close",) if key == "return" else (key,)

    def event(self, ev):
        if isinstance(ev, Move):
            self.hot = self._at(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.hot = self.pressed = self._at(ev.x, ev.y)
        elif isinstance(ev, Release) and ev.button == 1:
            hit, down, self.pressed = self._at(ev.x, ev.y), self.pressed, None
            self.hot = hit
            if hit is not None and hit == down:
                return self._act(hit)
        elif isinstance(ev, Key) and not ev.ctrl and ev.name == "escape":
            return ("close",)
        return None

    def scene_ops(self):
        f = self.frame
        ops = [Frame(f.x, f.y, f.w, f.h)]
        for i, ((_, line, enabled), r) in enumerate(zip(self.entries(), self.rects())):
            ops.append(Button(r.x, r.y, r.w, r.h, self.label(line), enabled, self.hot == i and enabled, self.pressed == i and enabled))
        return ops


class TownScene(Screen):
    """The town scene (L6, docs/engine/town-scenes.md): the picture, the hit mask, the animations.  A left press acts (not the release), the pointer drives the
    hover, ESC opens the scene menu `0x41f` (CONFIRMED `0x484a76`: `game+0x3d4` is never written, so it is empty), Enter does nothing.  `engine.townscene.SceneState` is the model; without the install a stand-in of three rectangles (shop / inn / leave) keeps the visit loop
    runnable.  The scene is rebuilt at every opening, as the exe's loader does; leaving it (click on shop / inn / leave) runs the close hook: every sound slot is released."""
    name, view = "town", "scene"
    music = None                            # the core's `music` event picks the playlist

    def __init__(self, shell):
        super().__init__(shell)
        self.state, self.mask, self.real = None, TS.StandInMask(), False
        self.menu = self.options = None                     # the `0x41f` window / the Sound Options over it
        self.dialog = None                                  # the Save / Load window (L10d), over the scene with the menu gone
        self.story = None                                   # the NPC story window (`storywin.StoryWindow`), modal over the scene
        self.tips_win, self.tips_lines, self.tips_down, self.hint, self.main = None, [], None, False, None

    @property
    def core(self):
        return self.shell.town_core()

    def enter(self, **params):
        core = self.core
        spec, self.mask, self.real = TS.load_scene(self.shell.fs, core.town or 1)
        self.state = TS.SceneState.build(spec, self.shell.rng, self.shell.scene_globals, var=core.camp.get)
        self.menu = self.options = self.dialog = self.story = None
        self._open_tips(core.town or 1)
        if self.shell.mouse is not None:
            self.state.hover(self._region(*self.shell.mouse))
        self._sounds()

    def _open_tips(self, town):
        """The scene's tips window: built at every load while TipsMode `0x622774` is on (`0x4ca855`); the check box writes the option, Close (message `0x45a`) removes it."""
        from allods2.text import decode_text
        from engine.ui.orders import MainText
        from .chargen import measure_font2, wrap_font2
        sh, fs = self.shell, self.shell.fs
        self.hint, self.tips_down, self.tips_lines = bool(sh.settings.tips), None, []
        self.main = MainText.load(fs) if fs is not None else MainText()
        if fs is not None:
            try:
                self.tips_lines = decode_text(fs.read(TS.TOWN_TEXT)).split("\r\n")
            except (KeyError, OSError):
                pass
        wrap = (lambda t, w: wrap_font2(sh, t, w)) if fs is not None else (lambda t, w: t.split("\n"))
        measure = (lambda t: measure_font2(sh, t)) if fs is not None else (lambda t: 7 * len(t))
        self.tips_win = TipsWindow(TIPS_RECT, self.main, wrap, measure)
        self.tips_key = tips_key(town)

    def tips_text(self):
        """The line after the section header (`FUN_004ddc9c`: the text up to the next `#`; one line in the install)."""
        for i, line in enumerate(self.tips_lines):
            if line.strip().lower() == self.tips_key:
                return self.tips_lines[i + 1] if i + 1 < len(self.tips_lines) else ""
        return ""

    def _tips_event(self, ev):
        """Close / check box clicks of the tips window (it sits over the scene: a press on one of its two controls is not a scene click).  True when consumed."""
        ox, oy = self.origin
        if isinstance(ev, Press) and ev.button == 1:
            self.tips_down = self.tips_win.hit(ev.x - ox, ev.y - oy)
            return self.tips_down is not None
        if isinstance(ev, Release) and ev.button == 1 and self.tips_down is not None:
            down, self.tips_down = self.tips_down, None
            if self.tips_win.hit(ev.x - ox, ev.y - oy) == down:
                if down == "close":
                    self.hint = False
                else:
                    self.shell.settings.tips = self.tips_win.toggle()
                    self.shell.services.save_settings(self.shell.settings)
            return True
        return False

    def open_story(self, key):
        """`FUN_0041d15e(key)`: the story window on the `town.txt` section, page 1 voiced at once; without the text file only the voice (`speak_town`) is left."""
        from allods2.text import decode_text
        from engine.ui.orders import MainText
        from .storywin import StoryWindow
        fs = self.shell.fs
        try:
            text = decode_text(fs.read(TS.TOWN_TEXT))
            main = MainText.load(fs)
        except (AttributeError, KeyError, OSError):
            self.shell.speak_town(key)
            return
        self.story = StoryWindow(self.shell, text, key, main)

    def exit(self):
        """The scene's close hook `0x4caaed` (town-scenes 6): every slot is released (loops and one-shots cut), the window is hidden, the object stays."""
        if self.state is not None:
            self.state.release_all()
            self._sounds()
        self.shell.services.loop(None)

    def _region(self, x, y):
        return self.mask.region_at(x, y, self.origin)

    def point_of(self, region):
        """Screen coordinates of a point of `region` (tests, scripted clicks); None when the mask has none."""
        if self.hint and self.tips_win is not None:          # a point not under the tips window's Close / check box (they take the click first)
            p = self.mask.point_of(region, lambda x, y: self.tips_win.hit(x, y) is not None)
        else:
            p = self.mask.point_of(region)
        return None if p is None else (p[0] + self.origin[0], p[1] + self.origin[1])

    def _sounds(self):
        for path, loop in self.state.take_events():
            if loop is TS.STOP:
                self.shell.stop(path)
            elif loop:
                self.shell.services.loop(path)
            else:
                self.shell.play(path)

    def open_menu(self):
        """Message `0x41f`: the scene menu window (`FUN_004407c2`), over the running scene."""
        slots = self.shell.slots
        self.menu = SceneMenu(load_texts(self.shell.fs), self.origin, save=slots is not None, load=slots is not None and slots.any_saves())

    def _menu_event(self, ev):
        if self.options is not None:
            self.options.event(ev)
            if self.options.done:
                self.options = None
            return None
        out = self.menu.event(ev)
        if out is None:
            return None
        if out[0] == "close":
            self.menu = None
        elif out[0] == "sound":                             # `0x422` (`0x485bf3`: allowed in a running game in town)
            self.options = OptionsPages(load_texts(self.shell.fs), self.shell.size, self.shell.settings, self.shell.services, SOUND)
        elif out[0] in ("save", "load"):                    # `0x41a` / `0x418`: the window replaces the menu; closing it resumes the scene (`FUN_004891d8`, +0x140 / +0x13c)
            from .saveload import LoadDialog, SaveDialog
            self.menu = None
            self.dialog = (SaveDialog if out[0] == "save" else LoadDialog)(self.shell, self.shell.slots)
        elif out[0] == "exit_menu":                         # `0x41e`: `FUN_0048f2e5` ends the game, then `0x421` (the main menu)
            self.menu = None
            return "menu"
        elif out[0] == "exit_windows":                      # `0x10`
            self.menu = None
            self.shell.close_window()
        return None

    def _dialog_event(self, ev):
        out = self.dialog.event(ev)
        if out is None:
            return None
        if out[0] == "close":
            self.dialog = None
        elif out[0] == "save":                              # Ok: `FUN_0048dc9f` writes the file, the window closes (no overwrite question in the exe)
            err = self.shell.save_game(out[1], out[2])
            if err is None:
                self.dialog = None
            else:
                self.dialog.notice(err)
        elif out[0] == "load":
            from .saveload import load_file
            status, res = load_file(self.shell, out[1])
            if status == "error":
                self.dialog.notice(res)
                return None
            self.dialog = None
            return res                                      # "town": a new scene of the loaded game (`town -> town`)
        return None

    def event(self, ev):
        if self.story is not None:
            self.story.event(ev)
            if self.story.closed:
                self.story = None
            return None
        if self.dialog is not None:
            return self._dialog_event(ev)
        if self.menu is not None:                           # a modal window: nothing reaches the scene
            return self._menu_event(ev)
        if isinstance(ev, Key) and not ev.ctrl and ev.name == "escape":   # the game's key handler `0x484a76` posts `0x41f` (town-scenes 2.2); Enter does nothing
            self.open_menu()
            return None
        if self.hint and self.tips_win is not None and self._tips_event(ev):
            return None
        if isinstance(ev, Move):
            self.state.hover(self._region(ev.x, ev.y))
        elif isinstance(ev, Press) and ev.button == 1:
            out = self.state.press(self._region(ev.x, ev.y))
            if out is None:
                return None
            if out[0] == "menu":                            # region `0x10`: message `0x41f`
                self.open_menu()
                return None
            if out[0] == "speech":                          # `FUN_0041d15e(key)`: the story window, page 1 voiced
                self.open_story(out[1])
                return None
            c = self.core
            if out[0] == "inn":
                c.send(T.MSG_INN)
            elif out[0] == "shop":
                c.send(T.MSG_SHOP)
            else:
                c.leave_town()
            return self.shell.town_screen()
        return None

    def update(self, dt_ms):
        if self.dialog is not None:
            self.dialog.update(dt_ms)
        self.state.advance(dt_ms)
        self._sounds()
        return None

    def scene(self):
        ox, oy = self.origin
        if not self.real:
            ops = []
            for region, label in ((TS.INN, "Inn"), (TS.SHOP, "Shop"), (TS.LEAVE, "Leave town")):
                x, y, w, h = TS.StandInMask.RECTS[region]
                ops += [Fill(ox + x, oy + y, w, h, (60, 50, 40) if self.state.region != region else (110, 90, 60)), Text(label, ox + x + w // 2, oy + y + h // 2, 1, "normal", 2 | 8, 1)]
        else:
            ops = ops_of(self.state.draw_ops(), ox, oy)
        if self.hint and self.tips_win is not None:
            ops += self.tips_win.ops(self.tips_text(), None, self.tips_down if self.tips_down in ("close", "tips") else None, ox, oy)
        if self.story is not None:
            ops += self.story.ops()
        elif self.dialog is not None:
            ops += self.dialog.scene_ops()
        elif self.menu is not None:
            ops += self.options.scene().ops if self.options is not None else self.menu.scene_ops()
        return Scene(ops)
