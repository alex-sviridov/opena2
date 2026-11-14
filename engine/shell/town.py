"""The town screens (docs/engine/town.md 3): the town scene (L6, the real one) and the inn and the shop (L4 placeholders: plain dialogs, L7 / L8 replace them),
driven by `engine.town.TownCore`: scene -> Inn / Shop / Leave (clicks on the regions), inn / shop -> Exit (ESC), Leave -> the map (`locations`).

Every click is a message to the core; the events it appends are turned into services here (`Shell.drain_town`)."""

from engine import town as T
from engine import townscene as TS

from . import dialog
from .events import Key, Move, Press, Release
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


class TownScene(Screen):
    """The town scene (L6, docs/engine/town-scenes.md): the picture, the hit mask, the animations.  A left press acts (not the release), the pointer drives the
    hover, ESC / Enter do nothing.  `engine.townscene.SceneState` is the model; without the install a stand-in of three rectangles (shop / inn / leave) keeps the visit loop
    runnable.  The scene is rebuilt at every opening, as the exe's loader does; the entry loop sound stops when the screen is left."""
    name, view = "town", "scene"
    music = None                            # the core's `music` event picks the playlist

    def __init__(self, shell):
        super().__init__(shell)
        self.state, self.mask, self.real = None, TS.StandInMask(), False

    @property
    def core(self):
        return self.shell.town_core()

    def enter(self, **params):
        core = self.core
        spec, self.mask, self.real = TS.load_scene(self.shell.fs, core.town or 1)
        self.state = TS.SceneState.build(spec, self.shell.rng, self.shell.scene_globals, var=core.camp.get)
        if self.shell.mouse is not None:
            self.state.hover(self._region(*self.shell.mouse))
        self._sounds()

    def exit(self):
        self.shell.services.loop(None)

    def _region(self, x, y):
        return self.mask.region_at(x, y, self.origin)

    def point_of(self, region):
        """Screen coordinates of a point of `region` (tests, scripted clicks); None when the mask has none."""
        p = self.mask.point_of(region)
        return None if p is None else (p[0] + self.origin[0], p[1] + self.origin[1])

    def _sounds(self):
        for path, loop in self.state.take_sounds():
            if loop:
                self.shell.services.loop(path)
            else:
                self.shell.play(path)

    def event(self, ev):
        if isinstance(ev, Move):
            self.state.hover(self._region(ev.x, ev.y))
        elif isinstance(ev, Press) and ev.button == 1:
            out = self.state.press(self._region(ev.x, ev.y))
            if out is None or out[0] == "menu":             # `0x41f` (the in-game menu) is not built yet
                return None
            if out[0] == "speech":
                self.shell.play("speech:%s" % out[1])
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
            return Scene(ops)
        return Scene(ops_of(self.state.draw_ops(), ox, oy))


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
