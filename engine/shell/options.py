"""Options (docs/engine/shell.md 5): the original's two option windows, opened from the **in-game menu** (message `0x416` -> Game Options `0x41b` / Sound Options
`0x422`; CONFIRMED `FUN_004852d8` `0x485cc4`: Game Options only while `game+0x404 == 1`, Sound Options in a mission or a running game in town (`0x485bf3`): the main
menu has no way to them, so the shell has no options screen).  `OptionsPages` is the component: one page at a time, `game` or `sound`, no screen of its own.

* Game Options (`FUN_004417fa`): every widget of the original at its dialog-relative rect (L2 added Tips, Join, the AutoCast checks and the three radio groups); **OK applies** (and saves),
  Cancel / ESC discards (`FUN_00442e8b`);
* Sound Options (`FUN_0043cacb`): the three volume sliders, Play / Stop for the music and the original's rects; the sliders act **live and are not reverted** by leaving
  (CONFIRMED), the file is written when the page is left; releasing the SFX slider plays the test sound `sfx[100]`.

Frame sizes follow `FUN_004dc4fc` (`w' = ((w - 8) / 0x60) * 0x60 + 8`, `h' = ((h - 0x68) / 0x40) * 0x40 + 0x68`, centred on the real screen).
Not built (listed in shell.md 5.3): the track list and Acknowledgments check, the Random Order widget (the exe never builds it), and the volume
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
SCRLBARS = "graphics/interface/scrlbars.256"   # 24x24 frames (CONFIRMED draw `0x4da80f`, horizontal): left 0 (3 pressed), rail 7, right 8 (11 pressed), thumb 10
LEFT_END, LEFT_PRESSED, RAIL, RIGHT_END, RIGHT_PRESSED, THUMB = 0, 3, 7, 8, 11, 10
BOX_OFF, BOX_ON = 2, 3
SHADOW = 4                                      # the darken level of every widget shadow (`0x1c(x, y, frame, 4, 0)`)
BTN = 24                                        # the width of the end frames
CHECK_CAPTION_DX = 30                           # `0x4d757c`: the caption at left + 6 + the width of frame 0 (24), top + 5
GAME, SOUND = "game", "sound"
GAME_SIZE, SOUND_SIZE = (584, 424), (488, 360)        # snapped (`FUN_004dc4fc`): 600x480 -> 584x424
RADIO_OFF, RADIO_ON = 0, 1                      # CONFIRMED `0x4d7e04` (the radio group paint): `radiob.256` frames 0 / 1 = off / on, 24x24
RADIO_ROW, RADIO_TOP = 24, 0x120                # the row pitch = the height of frame 0; the group rect (l, 0x120)-(r, 0x168) = 3 rows, its caption label is the 0x18 above it (0x108)
RADIO_CAPTION_TOP, RADIO_CAPTION_H = 0x108, 0x18
BITS = {"autocast_own": 1, "autocast_allies": 2, "autocast_neutral": 4}     # `0x62277c` bits of the "AutoCast for units" checks
MODE_BITS = (0, 0x10, 0x30)                     # the AutoCast-mode radio: Minimum / Average / Maximum (CONFIRMED OK handler `0x442e8b`: value 1 ORs 0x18, 2 ORs 0x38 onto the start value 8; init: 0x20 -> 2, else 0x10 -> 1)
NOT_BUILT = ()                                  # every Game Options widget of the original is built since L2 (Tips and Join are stored only, shell.md 5.3)
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
        self.side = None                                # "left" / "right": the end region held down (the pressed end frames 3 / 11)
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
                  W("check", (0x118, 0x45, 0xD8, 0x18), self.d(0x4E), "flying_damage"),
                  W("check", (0x118, 0x61, 0xD8, 0x18), self.d(0x9C), "tips"),
                  W("check", (0x118, 0x7D, 0xD8, 0x18), self.d(0x57), "message_colours"),
                  W("label", (0x118, 0x9A, 0xD8, 0x14), self.d(0xA6)),
                  W("check", (0x118, 0xB0, 0xD8, 0x18), self.d(0xA7), "autocast_own"),
                  W("check", (0x118, 0xCC, 0xD8, 0x18), self.d(0xA8), "autocast_allies"),
                  W("check", (0x118, 0xE8, 0xD8, 0x18), self.d(0xA9), "autocast_neutral")]
            for (l, r, cap, first, key) in ((0x28, 0xD0, 0x3A, 0x3C, "formation"), (0xD0, 0x178, 0x3F, 0x41, "retreat"), (0x178, 0x220, 0xAA, 0xAB, "autocast_mode")):
                ws.append(W("label", (l, RADIO_CAPTION_TOP, r - l, RADIO_CAPTION_H), self.d(cap)))
                ws += [W("radio", (l, RADIO_TOP + RADIO_ROW * i, r - l, RADIO_ROW), self.d(first + i), key, i) for i in range(3)]
            y = 0x170
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
            if w.kind in ("button", "check", "slider", "radio") and self.screen_rect(w).contains(x, y):
                return w
        return None

    # -- values --------------------------------------------------------------------------------------------------------------------
    def current(self):
        """The object the page edits: the draft of the game page, the live settings of the sound page."""
        return self.draft if self.page == GAME else self.settings

    def value(self, w):
        s = self.current()
        if w.key in BITS:
            return bool(s.autocasting & BITS[w.key])
        if w.key == "autocast_mode":
            v = 2 if s.autocasting & 0x20 else 1 if s.autocasting & 0x10 else 0
        else:
            v = getattr(s, w.key)
        return v == w.maximum if w.kind == "radio" else v

    def set_value(self, w, v):
        s = self.current()
        if w.key in BITS:
            s.autocasting = (s.autocasting & ~BITS[w.key]) | (BITS[w.key] if v else 0)
        elif w.key == "autocast_mode":
            s.autocasting = (s.autocasting & ~0x30) | MODE_BITS[v]
        else:
            setattr(s, w.key, v)
        if w.key in ("music", "sfx", "speech"):
            self.services.apply_settings(s)

    # -- slider geometry (CONFIRMED `0x4da80f`, `0x4da324`, `0x4da4a1`, `0x4dade4`) ---------------------------------------------------
    @staticmethod
    def usable(r):
        return r.w - (2 * BTN - 8) - 12

    def thumb_left(self, w):
        """The thumb's hit rect starts here and is 16 wide (`0x4da324`); the frame is drawn 1 px right of it."""
        r = self.screen_rect(w)
        return r.x - 4 + BTN + (self.usable(r) * self.value(w) // w.maximum if w.maximum else 0)

    def slider_value(self, w, x):
        """`0x4da4a1`: `max * (x - (left + 2 + 24)) / usable`, truncated toward zero, clamped to 0..max."""
        r = self.screen_rect(w)
        n = w.maximum * (x - (r.x + 2 + BTN))
        v = int(n / self.usable(r)) if self.usable(r) else 0
        return max(0, min(w.maximum, v))

    @staticmethod
    def step(w):
        """The step of a click beside the thumb (`0x4dade4`): `max / 16`, at least 1."""
        return max(1, w.maximum >> 4)

    def slider_press(self, w, x):
        """A press on a slider (`0x4dade4`): left of the thumb steps down, right of it up, on it starts the drag (the value follows the pointer)."""
        tl = self.thumb_left(w)
        if x < tl:
            self.side = "left"
            self.set_value(w, max(0, self.value(w) - self.step(w)))
        elif x >= tl + 16:
            self.side = "right"
            self.set_value(w, min(w.maximum, self.value(w) + self.step(w)))
        else:
            self.dragging = w
            self.set_value(w, self.slider_value(w, x))

    def close(self, result):
        """Close the window: the game page keeps its draft only on `ok` (the Animation -> Lighting rule applied, the file written); the sound page writes the file."""
        if self.page == GAME and result == "ok":
            s = self.draft
            if not s.animation:
                s.lighting = False                      # `0x442fb7`: Animation off forces Lighting off
            mode = 2 if s.autocasting & 0x20 else 1 if s.autocasting & 0x10 else 0
            s.autocasting = 8 | MODE_BITS[mode] | (s.autocasting & 7)       # `0x442e8b`: AutoCasting is rebuilt from 8 | mode | the three checks
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
                self.slider_press(w, ev.x)
            elif w is not None and w.kind == "button":
                self.services.sound(UI_SOUND)
            elif w is not None and w.kind in ("check", "radio"):
                self.activate(w)                              # CONFIRMED `0x4d77e6` / `0x4d806b`: the left-button press toggles / selects (no release step)
        elif isinstance(ev, Release) and ev.button == 1:
            w, self.pressed = self.pressed, None
            drag, self.dragging = self.dragging, None
            self.side = None
            self.hot = self.at(ev.x, ev.y)
            sfx = drag if drag is not None else (w if w is not None and w.kind == "slider" else None)
            if sfx is not None and sfx.key == "sfx":
                self.services.sound(SLIDER_TEST)          # `0x474`: the test sample at the new volume
            if w is not None and w.kind not in ("slider", "check", "radio") and self.screen_rect(w).contains(ev.x, ev.y):
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
        elif w.kind == "radio":
            self.set_value(w, w.maximum)
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
            elif w.kind == "radio":
                on = RADIO_ON if self.value(w) else RADIO_OFF
                group_hot = self.hot is not None and self.hot.kind == "radio" and self.hot.key == w.key
                ops.append(Sprite(RADIOB, on, r.x + 5, r.y + 4, SHADOW))             # `0x4d7e04`: silhouette (+5, +4), frame (+1, 0), caption (+6 + 24, +5)
                ops.append(Sprite(RADIOB, on, r.x + 1, r.y))
                ops.append(Text(w.text, r.x + CHECK_CAPTION_DX, r.y + 5, 1, "label" if group_hot and self.value(w) else "normal", 0, 1))   # gold only on the selected row while the group has the pointer
            elif w.kind == "check":
                ops.append(Sprite(RADIOB, BOX_ON if self.value(w) else BOX_OFF, r.x + 5, r.y + 4, SHADOW))
                ops.append(Sprite(RADIOB, BOX_ON if self.value(w) else BOX_OFF, r.x + 1, r.y))
                ops.append(Text(w.text, r.x + CHECK_CAPTION_DX, r.y + 5, 1, "label" if hot else "normal", 0, 1))
            elif w.kind == "slider":
                held = self.pressed is not None and self.pressed.rect == w.rect
                left = LEFT_PRESSED if held and self.side == "left" else LEFT_END
                right = RIGHT_PRESSED if held and self.side == "right" else RIGHT_END
                ops += [Sprite(SCRLBARS, left, r.x + 4, r.y + 4, SHADOW), Sprite(SCRLBARS, left, r.x, r.y)]
                for k in range(1, r.w // BTN):
                    ops += [Sprite(SCRLBARS, RAIL, r.x + k * BTN + 4, r.y + 4, SHADOW), Sprite(SCRLBARS, RAIL, r.x + k * BTN, r.y)]
                tl = self.thumb_left(w)
                ops += [Sprite(SCRLBARS, THUMB, tl + 5, r.y + 4, SHADOW), Sprite(SCRLBARS, right, r.right - BTN + 4, r.y + 4, SHADOW),
                        Sprite(SCRLBARS, right, r.right - BTN, r.y), Sprite(SCRLBARS, THUMB, tl + 1, r.y)]
        return Scene(ops, cursor=True)
