"""Options (docs/engine/shell.md 5): the original's two option windows, opened from the **in-game menu** (message `0x416` -> Game Options `0x41b` / Sound Options
`0x422`; CONFIRMED `FUN_004852d8` `0x485cc4`: Game Options only while `game+0x404 == 1`, Sound Options in a mission or a running game in town (`0x485bf3`): the main
menu has no way to them, so the shell has no options screen).  `OptionsPages` is the component: one page at a time, `game` or `sound`, no screen of its own.

* Game Options (`FUN_004417fa`): the widgets of the original whose option the engine applies, at the original's dialog-relative rects; **OK applies** (and saves),
  Cancel / ESC discards (`FUN_00442e8b`);
* Sound Options (`FUN_0043cacb`): the three volume sliders, Play / Stop for the music and the original's rects; the sliders act **live and are not reverted** by leaving
  (CONFIRMED), the file is written when the page is left; releasing the SFX slider plays the test sound `sfx[100]`.

Frame sizes follow `FUN_004dc4fc` (`w' = ((w - 8) / 0x60) * 0x60 + 8`, `h' = ((h - 0x68) / 0x40) * 0x40 + 0x68`, centred on the real screen).
Not built (listed in shell.md 5.3): the widgets in `NOT_BUILT`, the track list and Acknowledgments check, the Random Order widget (the exe never builds it), and the volume
ranges of the exe (the engine's sliders are the K11 percent scale)."""

import copy
from dataclasses import dataclass

from allods2.common import as_fs

from engine.ui.layout import Rect
from engine.ui.orders import MainText

from .events import Key, Move, Press, Release
from .scene import Button, Frame, Scene, Sprite, Text

UI_SOUND = 2                                    # `click`: the dialog text buttons' press (audio.md 2.4)
SLIDER_TEST = 100                               # `sfx[100]` (`0x420eb0(100)`), the slider test sample
RADIOB = "graphics/interface/radiob.256"       # frames 2 / 3 = check box off / on (`0x4d757c`)
SCRLBARS = "graphics/interface/scrlbars.256"   # 24x24 frames; INFERRED look of a horizontal slider: rail 7, thumb 16
RAIL, THUMB, BOX_OFF, BOX_ON = 7, 16, 2, 3
CHECK_CAPTION_DX = 28                           # INFERRED: the caption starts right of the 24 px box
GAME, SOUND = "game", "sound"
GAME_SIZE, SOUND_SIZE = (584, 360), (488, 360)        # snapped; the original's Game Options is 584x424 (more widgets)
# the Game Options widgets of the original that are not built (shell.md 5.3): Tips, "Join", AutoCast for units (Own / Allies / Neutral), Formation / Retreat / AutoCast mode radios
NOT_BUILT = ("tips", "join", "autocast_own", "autocast_allies", "autocast_neutral", "formation", "retreat", "autocast_mode")
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


def load_texts(fs):
    """`dialogs.txt` and `patch.txt` as `MainText` (empty lines without a file system)."""
    if fs is None:
        return {"dialogs": MainText(), "patch": MainText()}
    fs = as_fs(fs)
    return {n: MainText.load(fs, p) for n, p in (("dialogs", "main/text/dialogs.txt"), ("patch", "patch/patch.txt"))}


class OptionsPages:
    """One options window at a time over a screen of `size`; `done` is set when it closes (`result`: ok / cancel / return).  `settings` is edited in place
    (the game page through a draft); `services` supplies `sound`, `apply_settings` (live values), `save_settings`, `music`."""

    def __init__(self, texts, size, settings, services, page=GAME):
        self.texts, self.size, self.settings, self.services = texts, size, settings, services
        self.page = page
        self.draft = copy.copy(settings) if page == GAME else None
        self.hot = self.pressed = self.dragging = None
        self.done, self.result = False, None

    def d(self, i):
        return self.texts["dialogs"].line(i)

    def p(self, i):
        return self.texts["patch"].line(i)

    def frame(self):
        """Screen `Rect` of the dialog (centred on the real screen)."""
        w, h = GAME_SIZE if self.page == GAME else SOUND_SIZE
        sw, sh = self.size
        return Rect((sw - w) >> 1, (sh - h) >> 1, w, h)

    def widgets(self):
        f = self.frame()
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
    def current(self):
        """The object the page edits: the draft of the game page, the live settings of the sound page."""
        return self.draft if self.page == GAME else self.settings

    def value(self, w):
        return getattr(self.current(), w.key)

    def set_value(self, w, v):
        s = self.current()
        setattr(s, w.key, v)
        if w.key in ("music", "sfx", "speech"):
            self.services.apply_settings(s)

    def slider_value(self, w, x):
        r = self.screen_rect(w)
        span = max(1, r.w - 24)
        return max(0, min(w.maximum, round((x - r.x - 12) * w.maximum / span)))

    def close(self, result):
        """Close the window: the game page keeps its draft only on `ok` (the Animation -> Lighting rule applied, the file written); the sound page writes the file."""
        if self.page == GAME and result == "ok":
            s = self.draft
            if not s.animation:
                s.lighting = False                      # `0x442fb7`: Animation off forces Lighting off
            self.settings.__dict__.update(s.__dict__)
            self.services.save_settings(self.settings)
        elif self.page == SOUND:
            self.services.save_settings(self.settings)
        self.done, self.result = True, result

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
                self.services.sound(UI_SOUND)
        elif isinstance(ev, Release) and ev.button == 1:
            w, self.pressed = self.pressed, None
            drag, self.dragging = self.dragging, None
            self.hot = self.at(ev.x, ev.y)
            if drag is not None and drag.key == "sfx":
                self.services.sound(SLIDER_TEST)          # `0x474`: the test sample at the new volume
            if w is not None and w is not drag and self.screen_rect(w).contains(ev.x, ev.y):
                self.activate(w)
        elif isinstance(ev, Key) and not ev.ctrl:
            self.key(ev.name)

    def key(self, name):
        if name == "escape":                                 # the common dialog's ESC = message 0x446 (INFERRED for these classes)
            self.close("cancel" if self.page == GAME else "return")
        elif name == "return":                               # Enter = the default button (OK of the game page, Ok of the sound page)
            self.close("ok" if self.page == GAME else "return")

    def activate(self, w):
        if w.kind == "check":
            self.set_value(w, not self.value(w))
        elif w.key in ("ok", "cancel", "return"):
            self.close(w.key)
        elif w.key in ("play", "stop"):
            self.settings.music_enabled = w.key == "play"        # `0x477` / `0x478`
            self.services.apply_settings(self.settings)
            if w.key == "play":
                self.services.music("menu")

    # -- drawing -------------------------------------------------------------------------------------------------------------------
    def scene(self):
        f = self.frame()
        ops = [Frame(f.x, f.y, f.w, f.h)]
        for w in self.widgets():
            r = self.screen_rect(w)
            hot = self.hot is not None and self.hot.rect == w.rect and self.hot.kind == w.kind and self.hot.key == w.key
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
        return Scene(ops, cursor=True)
