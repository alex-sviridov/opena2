"""Options (docs/engine/shell.md 5): the original's two option windows as shell screens, reached from the main menu with `O` (an engine DECISION: the
original has no options button in its menu, `FUN_004852d8` messages `0x41b` / `0x422` come from the in-game menu).  Three pages on one screen:

* top: a menu dialog (296x168) with Game Options, Sound Options and Exit to Main Menu (`dialogs.txt` 0x24, 0x25, 0x2C), buttons by the `FUN_00450300` stack rule;
* Game Options (message `0x41b`, builder `FUN_004417fa`): the widgets of the original whose option the engine applies, at the original's dialog-relative
  rects; **OK applies** (and saves), Cancel / ESC discards (`FUN_00442e8b`);
* Sound Options (message `0x422`, `FUN_0043cacb`): the three volume sliders, Play / Stop for the music and the original's rects; the sliders act
  **live and are not reverted** by leaving (CONFIRMED), the file is written when the page is left; releasing the SFX slider plays the test sound `sfx[100]`.

Frame sizes follow `FUN_004dc4fc` (`w' = ((w - 8) / 0x60) * 0x60 + 8`, `h' = ((h - 0x68) / 0x40) * 0x40 + 0x68`, centred on the real screen).
Not built (listed in shell.md 5.3): Tips, AutoCast / formation / retreat groups, the track list and Acknowledgments check, the Random Order widget (the exe never
builds it), and the volume ranges of the exe (the engine's sliders are the K11 percent scale)."""

import copy
from dataclasses import dataclass

from engine.ui.layout import Rect
from engine.ui.orders import MainText
from engine.ui.widgets import button_rect

from .events import Key, Move, Press, Release
from .scene import Button, Frame, Image, Scene, Sprite, Text
from .screen import Screen

UI_SOUND = 2                                    # `click`: the dialog text buttons' press (audio.md 2.4)
SLIDER_TEST = 100                               # `sfx[100]` (`0x420eb0(100)`), the slider test sample
RADIOB = "graphics/interface/radiob.256"       # frames 2 / 3 = check box off / on (`0x4d757c`)
SCRLBARS = "graphics/interface/scrlbars.256"   # 24x24 frames; INFERRED look of a horizontal slider: rail 7, thumb 16
RAIL, THUMB, BOX_OFF, BOX_ON = 7, 16, 2, 3
CHECK_CAPTION_DX = 28                           # INFERRED: the caption starts right of the 24 px box
MENU_PICTURE = "main/graphics/MainMenu/menu_.bmp"
TOP, GAME, SOUND = "top", "game", "sound"
GAME_SIZE, SOUND_SIZE, TOP_SIZE = (584, 360), (488, 360), (296, 168)    # snapped; the original's Game Options is 584x424 (more widgets)
SPEED_MAX = 8
PERCENT = 100


def snap(w, h):
    """The dialog constructor's size rule (`FUN_004dc4fc`)."""
    return ((w - 8) // 0x60) * 0x60 + 8, ((h - 0x68) // 0x40) * 0x40 + 0x68


@dataclass
class W:
    """One widget: `kind` button / check / slider / label; rect dialog-relative (x, y, w, h)."""
    kind: str
    rect: tuple
    text: str = ""
    key: str = ""                   # settings field (check / slider) or the action name (button)
    maximum: int = 1
    flags: int = 0


class Options(Screen):
    name = "options"

    def __init__(self, shell):
        super().__init__(shell)
        self.page = TOP
        self.draft = None
        self.hot = self.pressed = None
        self.dragging = None
        self.texts = None

    # -- text ----------------------------------------------------------------------------------------------------------------------
    def _load_texts(self):
        if self.texts is None:
            fs = self.shell.fs
            self.texts = {n: MainText.load(fs, p) if fs is not None else MainText()
                          for n, p in (("dialogs", "main/text/dialogs.txt"), ("patch", "patch/patch.txt"))}
        return self.texts

    def d(self, i):
        return self._load_texts()["dialogs"].line(i)

    def p(self, i):
        return self._load_texts()["patch"].line(i)

    # -- pages ---------------------------------------------------------------------------------------------------------------------
    def enter(self, **params):
        self.page = TOP
        self.draft = None
        self.hot = self.pressed = self.dragging = None

    def frame(self):
        """Screen `Rect` of the current page's dialog (centred on the real screen)."""
        w, h = {TOP: TOP_SIZE, GAME: GAME_SIZE, SOUND: SOUND_SIZE}[self.page]
        sw, sh = self.shell.size
        return Rect((sw - w) >> 1, (sh - h) >> 1, w, h)

    def widgets(self):
        f = self.frame()
        if self.page == TOP:
            return [W("button", (b.x - f.x, b.y - f.y, b.w, b.h), self.d(i), act)
                    for k, (i, act) in enumerate(((0x24, "game"), (0x25, "sound"), (0x2C, "back")))
                    for b in (button_rect(f, k),)]
        if self.page == GAME:
            bw = f.w
            ws = [W("label", (0x28, 0x14, f.w - 0x50, 0x14), self.d(0x96), flags=2),
                  W("label", (0x28, 0x38, 0xC0, 0x18), self.d(0x32)),
                  W("slider", (0x28, 0x54, 0xC0, 0x18), "", "game_speed", SPEED_MAX),
                  W("check", (0x28, 0x78, 0xC0, 0x18), self.d(0x37), "day_night"),
                  W("check", (0x28, 0x94, 0xC0, 0x18), self.d(0x35), "smoothing"),
                  W("check", (0x28, 0xB0, 0xC0, 0x18), self.p(0x34), "shadows"),
                  W("check", (0x28, 0xCC, 0xC0, 0x18), self.p(0x35), "lighting"),
                  W("check", (0x28, 0xE8, 0xC0, 0x18), self.p(0x36), "animation"),
                  W("check", (0x118, 0x29, 0xD8, 0x18), self.d(0x39), "show_health"),
                  W("check", (0x118, 0x45, 0xD8, 0x18), self.d(0x4E), "flying_damage")]
            y = 0x108
            ws += [W("button", (bw // 7, y, 2 * bw // 7, 0x18), self.d(0), "ok"),
                   W("button", (4 * bw // 7, y, 2 * bw // 7, 0x18), self.d(1), "cancel")]
            return ws
        w = f.w
        return [W("label", (0x28, 0x14, w - 0x50, 0x19), self.d(7), flags=2),
                W("button", (0x28, 0x100, 0x64, 0x18), self.d(0xD), "play"),
                W("button", (0x96, 0x100, 0x66, 0x18), self.d(0xF), "stop"),
                W("button", (0x28, 0x122, 0xD4, 0x18), self.d(0), "return"),
                W("label", (0x102, 0xAF, w - 0x28 - 0x102, 0x0F), self.d(0x10)),
                W("slider", (0x102, 0xBE, w - 0x28 - 0x102, 0x18), "", "music", PERCENT),
                W("label", (0x102, 0xE0, w - 0x28 - 0x102, 0x0F), self.d(0x11)),
                W("slider", (0x102, 0xF0, w - 0x28 - 0x102, 0x18), "", "sfx", PERCENT),
                W("label", (0x102, 0x113, w - 0x28 - 0x102, 0x0F), self.d(0x12)),
                W("slider", (0x102, 0x122, w - 0x28 - 0x102, 0x18), "", "speech", PERCENT)]

    def screen_rect(self, w):
        f = self.frame()
        x, y, ww, hh = w.rect
        return Rect(f.x + x, f.y + y, ww, hh)

    def at(self, x, y):
        for w in self.widgets():
            if w.kind in ("button", "check", "slider") and self.screen_rect(w).contains(x, y):
                return w
        return None

    # -- values --------------------------------------------------------------------------------------------------------------------
    def settings(self):
        """The object the current page edits: the draft of the game page, the live settings elsewhere."""
        return self.draft if self.page == GAME and self.draft is not None else self.shell.settings

    def value(self, w):
        return getattr(self.settings(), w.key)

    def set_value(self, w, v):
        s = self.settings()
        setattr(s, w.key, v)
        if w.key in ("music", "sfx", "speech"):
            self.shell.services.apply_settings(s)

    def slider_value(self, w, x):
        r = self.screen_rect(w)
        span = max(1, r.w - 24)
        return max(0, min(w.maximum, round((x - r.x - 12) * w.maximum / span)))

    def open_page(self, page):
        self.page = page
        self.hot = self.pressed = self.dragging = None
        self.draft = copy.copy(self.shell.settings) if page == GAME else None

    def leave_page(self, apply=False):
        """Back to the top page; the game page's draft is kept only with `apply` (OK); the sound page's live values are saved."""
        if self.page == GAME and apply:
            s = self.draft
            if not s.animation:
                s.lighting = False                      # `0x442fb7`: Animation off forces Lighting off
            self.shell.settings.__dict__.update(s.__dict__)
            self.shell.services.save_settings(self.shell.settings)
        elif self.page == SOUND:
            self.shell.services.save_settings(self.shell.settings)
        self.open_page(TOP)

    # -- events --------------------------------------------------------------------------------------------------------------------
    def event(self, ev):
        if isinstance(ev, Move):
            self.hot = self.at(ev.x, ev.y)
            if self.dragging is not None:
                self.set_value(self.dragging, self.slider_value(self.dragging, ev.x))
        elif isinstance(ev, Press) and ev.button == 1:
            self.hot = w = self.at(ev.x, ev.y)
            self.pressed = w
            if w is not None and w.kind == "slider":
                self.dragging = w
                self.set_value(w, self.slider_value(w, ev.x))
            elif w is not None and w.kind == "button":
                self.shell.play(UI_SOUND)
        elif isinstance(ev, Release) and ev.button == 1:
            w, self.pressed = self.pressed, None
            drag, self.dragging = self.dragging, None
            self.hot = self.at(ev.x, ev.y)
            if drag is not None and drag.key == "sfx":
                self.shell.play(SLIDER_TEST)              # `0x474`: the test sample at the new volume
            if w is not None and w is not drag and self.at(ev.x, ev.y) is not None and self.screen_rect(w).contains(ev.x, ev.y):
                return self.activate(w)
        elif isinstance(ev, Key) and not ev.ctrl:
            return self.key(ev.name)
        return None

    def key(self, name):
        if name == "escape":
            return self.back()
        if self.page == TOP:
            return self.top_key(name)
        if name == "return":                                # Enter = the default button (OK of the game page, Return of the sound page)
            return self.activate(W("button", (0, 0, 0, 0), "", "ok" if self.page == GAME else "return"))
        return None

    def top_key(self, name):
        if name == "o":
            self.open_page(GAME)
        elif name == "n":
            self.open_page(SOUND)
        elif name == "e":
            return "menu"
        return None

    def back(self):
        """ESC / Cancel: the top page leaves for the menu, a page returns to the top (the game page discards its draft)."""
        if self.page == TOP:
            return "menu"
        self.leave_page(apply=False)
        return None

    def activate(self, w):
        if w.kind == "check":
            self.set_value(w, not self.value(w))
            return None
        act = w.key
        if act == "game":
            self.open_page(GAME)
        elif act == "sound":
            self.open_page(SOUND)
        elif act == "back":
            return "menu"
        elif act == "ok":
            self.leave_page(apply=True)
        elif act == "cancel":
            self.leave_page(apply=False)
        elif act == "return":
            self.leave_page()
        elif act in ("play", "stop"):
            self.shell.settings.music_enabled = act == "play"       # `0x477` / `0x478`
            self.shell.services.apply_settings(self.shell.settings)
            if act == "play":
                self.shell.services.music("menu")
        return None

    # -- drawing -------------------------------------------------------------------------------------------------------------------
    def scene(self):
        f = self.frame()
        ox, oy = self.origin
        ops = [Image(MENU_PICTURE, ox, oy), Frame(f.x, f.y, f.w, f.h)]          # the dialog stands over the menu picture, as the exe's dialogs stand over their screen
        for w in self.widgets():
            r = self.screen_rect(w)
            hot = w is not None and self.hot is not None and self.hot.rect == w.rect and self.hot.kind == w.kind and self.hot.key == w.key
            if w.kind == "label":
                x = r.x + r.w // 2 if w.flags & 2 else r.x
                ops.append(Text(w.text, x, r.y + (3 if w.flags & 2 else 0), 1, "normal", w.flags & 2, 1))
            elif w.kind == "button":
                pressed = self.pressed is not None and self.pressed.rect == w.rect and hot
                ops.append(Button(r.x, r.y, r.w, r.h, w.text, True, hot, pressed))
            elif w.kind == "check":
                ops.append(Sprite(RADIOB, BOX_ON if self.value(w) else BOX_OFF, r.x + 1, r.y, True))
                ops.append(Text(w.text, r.x + CHECK_CAPTION_DX, r.y + 5, 1, "label" if hot else "normal", 0, 1))
            elif w.kind == "slider":
                for x in range(r.x, r.right, 24):
                    ops.append(Sprite(SCRLBARS, RAIL, min(x, r.right - 24), r.y))
                pos = self.value(w)
                ops.append(Sprite(SCRLBARS, THUMB, r.x + pos * (r.w - 24) // w.maximum, r.y))
        return Scene(ops)
