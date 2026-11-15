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

W, H = 360, 280
PAD, ROW, GAP = dialog.CORNER, 24, 6
CLICK = "sfx/chrgen/ok.wav"


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

    @property
    def core(self):
        return self.shell.town_core()

    def enter(self, **params):
        core = self.core
        spec, self.mask, self.real = TS.load_scene(self.shell.fs, core.town or 1)
        self.state = TS.SceneState.build(spec, self.shell.rng, self.shell.scene_globals, var=core.camp.get)
        self.menu = self.options = self.dialog = None
        if self.shell.mouse is not None:
            self.state.hover(self._region(*self.shell.mouse))
        self._sounds()

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
        if self.dialog is not None:
            return self._dialog_event(ev)
        if self.menu is not None:                           # a modal window: nothing reaches the scene
            return self._menu_event(ev)
        if isinstance(ev, Key) and not ev.ctrl and ev.name == "escape":   # the game's key handler `0x484a76` posts `0x41f` (town-scenes 2.2); Enter does nothing
            self.open_menu()
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
            if out[0] == "speech":                          # `FUN_0041d15e(key)`: the story window; page 1's voice is played (speak_town)
                self.shell.speak_town(out[1])
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
        if self.dialog is not None:
            ops += self.dialog.scene_ops()
        elif self.menu is not None:
            ops += self.options.scene().ops if self.options is not None else self.menu.scene_ops()
        return Scene(ops)
