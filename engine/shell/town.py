"""The town screens (L4 placeholders, docs/engine/town.md 3): the town scene, the inn and the shop as plain dialogs driven by `engine.town.TownCore`.  The
art, hit regions and windows are L6-L8; these screens only carry the mask, the messages and the exits, so the whole visit loop can be played and tested:
scene -> Inn / Shop / Leave, inn / shop -> Exit (ESC), Leave -> the map (`locations`, the L2 stand-in until L5).

Every click is a message to the core; the events it appends are turned into services here (`Shell.drain_town`)."""

from engine import town as T

from . import dialog
from .events import Key, Move, Press, Release
from .scene import Button, Frame, Scene, Text
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


class TownScene(TownPanel):
    name, view = "town", "scene"
    labels = ("Inn", "Shop", "Leave town")

    def title(self):
        c = self.core
        return "Town %d (%s)" % (c.town, c.windows.race) if c.windows else "Town"

    def act(self, i):
        c = self.core
        if i == 0:
            c.send(T.MSG_INN)
        elif i == 1:
            c.send(T.MSG_SHOP)
        else:
            c.leave_town()


class Inn(TownPanel):
    name, view = "inn", "inn"
    labels = ("Exit",)

    def title(self):
        return "Inn (%s)" % self.core.windows.race

    def act(self, i):
        self.core.close_window()

    def escape(self):
        return self._do(0)


class Shop(Inn):
    name, view = "shop", "shop"

    def title(self):
        return "Shop (%s)" % self.core.windows.race
