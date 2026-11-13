"""New game (docs/engine/shell.md 3.3): the original's PreCreate screen (`+0x374`, ctor `0x43270d`, resource `0x466`, class vtable `0x5cb998`): the stained-glass hall
`MainArea.bmp` (640x480) with a hit mask `Mask.bmp` (red channel): four heroes, three difficulty tablets, Cancel, OK and the name plate with an edit field.

CONFIRMED (REA, shell.md 3.3): the widget rects (ctor: levels (8 / 296 / 580, 0), heroes (116 / 180 / 392 / 456, 44), Cancel (16, 400), OK (548, 400)); the screen **acts on the
mouse press** (`0x436d48`; a move with the button held selects too), not on the release; hero value 0 Aldor (male fighter), 1 Sagita (female fighter), 2 Galinel (female mage),
3 Gildarius (male mage); the show routine selects hero 0 (`+0x208 := 0`) and the level `+0x20c`; level tablet states 1 selected = `level<n>on`, 2 hover = `level<n>l`, 3 both =
`level<n>lon`; the big portrait `h<n>sel` of the selected hero becomes `h<n>sel<partner>` while its partner pane is lit (pairs 1-2 and 3-4); the name field (`0x4321e9`,
`0x432397`, `0x437829`, `0x437955`): printable characters (>= 0x20) up to **10**, Backspace deletes the last one, the caret is always at the end (`|` blinking every 500 ms),
Enter = OK and ESC = Cancel, **an empty name does nothing**, typing plays `SFX\\Letter2.wav` (INFERRED: the index `+0x1e8` stays 0), clicks `ChrGen\\Level1-3.wav` / `Char.wav` /
`Ok.wav`; clicking a hero swaps the name for its default name (`npcnames` 0x17..0x1a) only while the field holds a default name or "Unnamed" (`0x437d90`); the initial name is
"Master Oberic", a default name is reset to "Aldor" (`npcnames` 0x14) on the next show.  Font4: the exe draws the name left aligned at (300, 433); DECISION: we centre it on the plate (shell.md 3.3).
INFERRED: the initial level is 0 (Easy: the window's `+0x20c` is never initialised before the show; the exe's own selector 1 = Medium is overwritten by the window's level at OK),
the focus sits on the name field from the start, the position of the big portraits (template matching: x 112 for heroes 0-1, 260 for 2-3, y 44), Cancel plays `ChrGen\\Ok.wav`.
Torches: `torch1` / `torch2` are 15-frame flame animations (48x72) on the two braziers, at **(4, 200)** and **(589, 200)** (CONFIRMED by pixel identity: the frames' static pixels equal `MainArea.bmp` there with error
0), advanced by a global 67 ms timer (`0x436222`; the exe starts each torch at a random frame, here 0 and 7).
Paint ticks (CONFIRMED `0x43541e`): the whole panel paints only when more than `0x43` = 67 ms passed since the last paint (`now - last > 67`); the two animations below run inside that tick.
**Sparkle** (the second animation, `+0x70` = `PreCreate\\Blind\\sprites.16a`, 15 frames of 28x28, alpha; `+0x74` = frame, 0 = idle): idle until `now - t0 > delay` with `delay = rand() / 65 + 500` (`rand()` = 0..32767, drawn at the first paint and after every start);
then it picks a rect `i = rand() / (0x7fff / 5)` of the five rects (`+0x80`: the three level rects 48x72, Cancel 64x76, OK 80x76), the point `rect.topleft + (rand() / (0x7fff / w), rand() / (0x7fff / h))`, new delay, frame := 1 (`t0` is not reset, so frame 1 shows for one tick);
a running frame is drawn first, then when `now - t0 > 63` the frame becomes `(f + 1) % 15` and `t0 := now` (frame 0 = idle again).  **Hint pulse** (`0x4364f7`, called only while TipsMode is on and the tips window exists; it is not a cross-fade): for the tip step `+0x218`
(0 heroes, 1 levels, 2 Cancel / OK, later steps nothing) it cycles the group's widgets with a 300 ms phase unless the pointer is over the group (then the 500 ms quiet timer restarts and the phase resumes after the hovered widget);
the pulse draws the hero-0 portrait `h1sel` (or `h1sel2` in phase 1) at (112, 44) plus `h3on` / `h4on` in phases 2 / 3, the level pictures `level<n>l` (`lon` while that level is selected), or `cancell` / `okl`.  The hero vectors (`+0x94 / 0xa8 / 0xbc`) are indexed in screen order (h1, h2, h3, h4 = values 0..3).
Not built: the OK goes on to the character generator panel `+0x36c` (`chargen.py`, L2: `0x4891d8` copies name, level `+ 1` and the hero code, then shows the panel)."""

import random

import numpy as np

from allods2.graphics import load_bmp
from allods2.text import decode_text

from .events import Key, Move, Press, Release
from .scene import Image, Scene, Sprite, Text
from .screen import Screen
from .tipswin import TipsWindow

DIR = "graphics/interface/chrgen/precreate/"
OK_SOUND, CHAR_SOUND, LETTER_SOUND = "sfx/chrgen/ok.wav", "sfx/chrgen/char.wav", "sfx/letter2.wav"
LEVEL_SOUNDS = ("sfx/chrgen/level1.wav", "sfx/chrgen/level2.wav", "sfx/chrgen/level3.wav")
LEVELS = {20: 0, 40: 1, 60: 2}                          # mask value -> difficulty selector (Easy / Medium / Hard)
HEROES = {80: 0, 100: 1, 120: 2, 140: 3}
CANCEL, OK, PLATE = 160, 180, 200
LEVEL_AT = ((8, 0), (296, 0), (580, 0))
HERO_AT = ((116, 44), (180, 44), (392, 44), (456, 44))
BIG_AT = ((112, 44), (112, 44), (260, 44), (260, 44))
PARTNER = (1, 0, 3, 2)                                  # the other pane of a pair: h1sel2, h2sel1, h3sel4, h4sel3
CANCEL_AT, OK_AT, PLATE_AT = (16, 400), (548, 400), (172, 396)   # INFERRED by template matching (shell.md 3.3); the hover pictures `cancell` / `okl` are INFERRED too
NAME_AT, NAME_FONT, NAME_MAX = (300, 433), 4, 10
PLATE_W = 312                                               # tablol.bmp
HERO_NAMES = ("Aldor", "Sagita", "Galinel", "Gildarius")      # male fighter, female fighter, female mage, male mage (npcnames 0x17..0x1a; 0x19 / 0x1a are Gildarius / Galinel in the file)
HERO_CODE = (0x00, 0x80, 0xC0, 0x40)                    # `window+0x484 >> 0` per hero value: bit 0x40 mage, bit 0x80 female (`4891d8`, table `0x5cdd60`)
TIPS_WINDOW = (232, 48, 408, 136)                       # CONFIRMED: `0x4dec24(0x467, 0xe8, 0x30, 0x280, 0xb8)` = SetRect (l, t, r, b) = (232, 48, 640, 184), a child of the panel (at the screen origin)
TIPS_LINE = {8: 14, 9: 16, 10: 18}                      # `#tipsN` header lines of town.txt (the text is the next line)
UNNAMED = "Unnamed"
INITIAL_NAME = "Master Oberic"                          # 0x5efba8
DEFAULT_LEVEL = 0                                       # INFERRED (see the module doc)
BLINK_MS = 500
TORCH_AT = ((4, 200), (589, 200))                       # CONFIRMED by pixel identity of the static part of the frames against `MainArea.bmp`
PAINT_TICK_MS = 0x43                                    # CONFIRMED `0x43541e`: the panel paints (and animates) when more than 67 ms passed
SPARK = DIR + "blind/sprites.16a"                       # CONFIRMED (`0x433c58`, stored in `+0x70`): 15 frames, 28x28, alpha
SPARK_FRAMES, SPARK_STEP_MS = 15, 0x3f                  # a frame lasts until `now - t0 > 63`
SPARK_RECTS = tuple((x, y, 48, 72) for x, y in LEVEL_AT) + ((16, 400, 64, 76), (548, 400, 80, 76))   # `+0x80` (ctor `0x4331c5-0x43330a`): level rects, Cancel, OK
RAND_MAX = 0x7fff
HINT_QUIET_MS, HINT_STEP_MS = 500, 300                  # `0x4364f7`: 500 ms since the last hover of the hinted group, then the phase advances every 300 ms
HINT_GROUPS = ((tuple(HEROES), 4), (tuple(LEVELS), 3), ((CANCEL, OK), 2))      # per tip step: the hover values that keep the pulse quiet, the phase count
HINT_PHASE = {20: 1, 40: 2, 60: 3, 80: 1, 100: 2, 120: 3, 140: 4, 160: 1, 180: 2}   # the phase a remembered hover value resumes at (the switch at `0x4365b3`)
TORCH_FRAMES, TORCH_MS, TORCH_START = 15, 67, (0, 7)     # 15 frames, the global timer's 67 ms (`0x436222`); the exe's random start frame is a DECISION here


def is_default_name(name):
    """`0x437d90`: one of the four hero names or "Unnamed" (case-insensitive)."""
    return name.lower() in {n.lower() for n in HERO_NAMES} | {UNNAMED.lower()}


class NewGame(Screen):
    name = "newgame"
    music = "chrgen"

    def __init__(self, shell, rng=None):
        super().__init__(shell)
        self.rng = rng or random.Random()                    # injectable for the tests (the exe uses the CRT `rand()`, 0..32767)
        self.now = 0                                         # ms accumulated by update(); the exe's statics persist over visits, so these do not reset in enter()
        self.paint_at, self.spark_t0, self.spark_delay, self.started = 0, 0, 0, False
        self.spark, self.spark_pos, self.spark_draw = 0, (0, 0), None
        self.hint_t1 = self.hint_t2 = 0
        self.hint_last, self.hint_phase, self.hint_ops = -1, 0, []
        self.mask = None
        self.name_text = INITIAL_NAME
        self.hero, self.level = 0, DEFAULT_LEVEL

    def enter(self, **params):
        if self.mask is None:
            m = load_bmp(DIR + "mask.bmp", self.shell.fs)
            self.mask = np.asarray(m.index if m.index is not None else m.rgb[..., 0])
        if is_default_name(self.name_text):                  # the show routine `0x433628`: a default name goes back to line 0x14
            self.name_text = HERO_NAMES[0]
        self.hero, self.level = 0, DEFAULT_LEVEL             # `+0x208 := 0`; the level as left by the window (INFERRED 0)
        self.under, self.held = 0, False
        self.tips_win, self.tips_n, self.tips_hover, self.tips_down = None, 0, None, None
        if self.shell.settings.tips:                          # `0x43371e`: TipsMode on builds the window (`#tips8`, counter `+0x218` = 0)
            from engine.ui.orders import MainText
            from .chargen import measure_font2, wrap_font2
            self.main = getattr(self, "main", None) or MainText.load(self.shell.fs)
            self.town = getattr(self, "town", None) or decode_text(self.shell.fs.read("main/text/town.txt")).split("\r\n")
            self.tips_win = TipsWindow(TIPS_WINDOW, self.main, lambda t, w: wrap_font2(self.shell, t, w), lambda t: measure_font2(self.shell, t))
        self.blink_on, self.blink_ms = True, 0
        self.anim_ms = 0
        self.spark, self.spark_draw, self.hint_ops = 0, None, []         # the show routine `0x4334df` clears `+0x74`; the timers are the exe's statics and stay

    # -- input ---------------------------------------------------------------------------------------------------------------------
    def _at(self, x, y):
        ox, oy = self.origin
        x, y = x - ox, y - oy
        return int(self.mask[y, x]) if 0 <= x < 640 and 0 <= y < 480 else 0

    def _select(self, v):
        """`0x434f15`: a level or hero is selected (move with the button held, or the press)."""
        if v in LEVELS and LEVELS[v] != self.level:
            self.level = LEVELS[v]
        elif v in HEROES:
            new = HEROES[v]
            if new != self.hero and is_default_name(self.name_text):      # `0x436ebb-0x4371a0`
                self.name_text = HERO_NAMES[new]
            self.hero = new

    def _ok(self):
        if not self.name_text:
            return None                                       # `0x437829`: an empty name does nothing
        self.shell.play(OK_SOUND)
        return "chargen", {"difficulty": self.level + 1, "hero": self.hero, "hero_code": HERO_CODE[self.hero], "name": self.name_text}

    def _cancel(self):
        self.shell.play(OK_SOUND)                            # `0x437955` plays the Cancel sound (the second `ChrGen\Ok.wav`)
        return "menu"

    def name_ops(self, ox=0, oy=0):
        """The name (DECISION, the exe draws it left aligned at the rect's left, shell.md 3.3): centred on the plate; the blink caret is a separate Text just after the name so it never shifts it."""
        cx = ox + PLATE_AT[0] + PLATE_W // 2
        m = self.measure_name(self.name_text)
        ops = [Text(self.name_text, cx, oy + NAME_AT[1], NAME_FONT, "normal", 2, 0)]
        if self.blink_on:
            ops.append(Text("|", cx - m // 2 + m, oy + NAME_AT[1], NAME_FONT, "normal", 0, 0))
        return ops

    def measure_name(self, text):
        from allods2.graphics.font import Font, font_bytes
        f = getattr(self.shell, "_font4", None)
        if f is None:
            f = self.shell._font4 = Font.load("graphics/font4/font4", self.shell.fs)
        return f.measure(font_bytes(text))

    def tips_text(self):
        i = TIPS_LINE[8 + self.tips_n] + 1
        return self.town[i] if len(self.town) > i else ""

    def _tips_press(self, v):
        """`0x4372d1` (called by the press handler `0x436d48` with the mask id): the first hero click shows `#tips9`, a level click after that `#tips10`."""
        if self.tips_win is None:
            return
        if v in HEROES and self.tips_n == 0:
            self.tips_n = 1
        elif v in LEVELS and self.tips_n == 1:
            self.tips_n = 2

    def _tips_event(self, ev):
        """Mouse over the tips window: swallowed (a child above the panel); the Close release removes it (`0x45a`), the check box release writes TipsMode (`0x46e`)."""
        if isinstance(ev, (Move, Press, Release)) and self.tips_win is not None:
            ox, oy = self.origin
            h = self.tips_win.hit(ev.x - ox, ev.y - oy)
            if isinstance(ev, Move):
                self.tips_hover = h
            elif ev.button == 1 and h:
                if isinstance(ev, Press):
                    self.tips_down = h
                else:
                    down, self.tips_down = self.tips_down, None
                    if down == h and h == "close":
                        self.tips_win = None
                    elif down == h and h == "tips":
                        self.shell.settings.tips = self.tips_win.toggle()
                        self.shell.services.save_settings(self.shell.settings)
            return bool(h)
        return False

    def event(self, ev):
        if self._tips_event(ev):
            return None
        if isinstance(ev, Move):
            self.under = self._at(ev.x, ev.y)
            if self.held:
                self._select(self.under)
        elif isinstance(ev, Press) and ev.button == 1:
            self.under = v = self._at(ev.x, ev.y)
            self.held = True
            self._tips_press(v)
            if v in LEVELS:
                self.shell.play(LEVEL_SOUNDS[LEVELS[v]])
                self._select(v)
            elif v in HEROES:
                self.shell.play(CHAR_SOUND)
                self._select(v)
            elif v == CANCEL:
                return self._cancel()
            elif v == OK:
                return self._ok()
        elif isinstance(ev, Release) and ev.button == 1:
            self.held = False
            self.under = self._at(ev.x, ev.y)
        elif isinstance(ev, Key) and not ev.ctrl:
            if ev.name == "return":
                return self._ok()
            if ev.name == "escape":
                return self._cancel()
            if ev.name == "backspace":
                if self.name_text:
                    self.name_text = self.name_text[:-1]
                    self.shell.play(LETTER_SOUND)
                    self._caret()
            elif ev.char and len(self.name_text) < NAME_MAX:
                self.name_text += ev.char
                self.shell.play(LETTER_SOUND)
                self._caret()
        return None

    def _caret(self):
        self.blink_on, self.blink_ms = True, 0                # a typed key restarts the blink (`+0x70 := 1`)

    def update(self, dt_ms):
        self.anim_ms += dt_ms
        self.blink_ms += dt_ms
        if self.blink_ms > BLINK_MS:
            self.blink_ms -= BLINK_MS
            self.blink_on = not self.blink_on
        self.now += dt_ms
        if not self.started:                                 # the first paint: the statics of `0x43541e` / `0x4364f7` are set
            self.started = True
            self.paint_at = self.spark_t0 = self.hint_t1 = self.hint_t2 = self.now
            self.spark_delay = self._rand() // 65 + 500
        if self.now - self.paint_at > PAINT_TICK_MS:
            self.paint_at = self.now
            self._paint_tick()
        return None

    def _rand(self):
        return self.rng.randrange(RAND_MAX + 1)

    def _paint_tick(self):
        """One paint of the panel (`0x43541e`): the hint pulse, then the sparkle; both store what they draw (the exe draws before it advances)."""
        self.hint_ops = self._hint() if self.shell.settings.tips and self.tips_win is not None else []
        if self.spark == 0:
            self.spark_draw = None
            if self.now - self.spark_t0 > self.spark_delay:
                i = self._rand() // (RAND_MAX // len(SPARK_RECTS))
                x0, y0, w, h = SPARK_RECTS[min(i, len(SPARK_RECTS) - 1)]       # i == 5 only for rand() == 0x7fff (an out-of-range read in the exe)
                dx, dy = self._rand() // (RAND_MAX // w), self._rand() // (RAND_MAX // h)
                self.spark_pos = (x0 + dx, y0 + dy)
                self.spark_delay = self._rand() // 65 + 500
                self.spark = 1
        else:
            self.spark_draw = (self.spark, self.spark_pos)
            if self.now - self.spark_t0 > SPARK_STEP_MS:
                self.spark = (self.spark + 1) % SPARK_FRAMES
                self.spark_t0 = self.now

    def _hint(self):
        """`0x4364f7` (CONFIRMED): the pulse of the widgets the tip step talks about; returns (path, x, y) pictures."""
        now, mask = self.now, self.under
        if now - self.hint_t1 < HINT_QUIET_MS:
            self.hint_t2 = now
            return []
        if self.hint_last in HINT_PHASE:
            self.hint_phase = HINT_PHASE[self.hint_last]
        ops, count = [], -1
        if self.tips_n < len(HINT_GROUPS):
            keep, count = HINT_GROUPS[self.tips_n]
            if mask in keep:
                self.hint_t1 = self.hint_t2 = now
                self.hint_last = mask
                return []
            p = self.hint_phase = self.hint_phase % count
            if self.tips_n == 0:
                ops.append((DIR + "heroes/h1sel%s.bmp" % ("2" if p == 1 else ""), 112, 44))
                if p in (2, 3):
                    ops.append((DIR + "heroes/h%don.bmp" % (p + 1), *HERO_AT[p]))
            elif self.tips_n == 1:
                ops.append((DIR + "levels/level%d%s.bmp" % (p, "lon" if self.level == p else "l"), *LEVEL_AT[p]))
            else:
                ops.append((DIR + ("cancell.bmp" if p == 0 else "okl.bmp"), *(CANCEL_AT if p == 0 else OK_AT)))
        self.hint_last = -1
        if now - self.hint_t2 > HINT_STEP_MS and count != -1:
            self.hint_phase = (self.hint_phase + 1) % count
            self.hint_t2 = now
        return ops

    # -- drawing -------------------------------------------------------------------------------------------------------------------
    def scene(self):
        ox, oy = self.origin
        ops = [Image(DIR + "mainarea.bmp", ox, oy)]
        for t, (x, y) in enumerate(TORCH_AT):
            frame = (self.anim_ms // TORCH_MS + TORCH_START[t]) % TORCH_FRAMES
            ops.append(Image(DIR + "torch%d/t%d%04d.bmp" % (t + 1, t + 1, frame), ox + x, oy + y))
        hover_hero = HEROES.get(self.under)
        for n, (x, y) in enumerate(LEVEL_AT):
            sel, hot = self.level == n, LEVELS.get(self.under) == n
            if sel or hot:                                    # states 1 / 2 / 3 -> on / l / lon (paint `0x43541e`)
                ops.append(Image(DIR + "levels/level%d%s.bmp" % (n, "lon" if sel and hot else "on" if sel else "l"), ox + x, oy + y))
        for n, (x, y) in enumerate(HERO_AT):
            if self.hero == n:
                partner = PARTNER[n] == hover_hero
                bx, by = BIG_AT[n]
                ops.append(Image(DIR + "heroes/h%dsel%s.bmp" % (n + 1, str(PARTNER[n] + 1) if partner else ""), ox + bx, oy + by))
            elif hover_hero == n:
                ops.append(Image(DIR + "heroes/h%don.bmp" % (n + 1), ox + x, oy + y))
        ops.append(Image(DIR + "tablol.bmp", ox + PLATE_AT[0], oy + PLATE_AT[1]))
        if self.under == CANCEL:
            ops.append(Image(DIR + "cancell.bmp", ox + CANCEL_AT[0], oy + CANCEL_AT[1]))
        if self.under == OK:
            ops.append(Image(DIR + "okl.bmp", ox + OK_AT[0], oy + OK_AT[1]))
        for path, x, y in self.hint_ops:                      # the hint pulse (`0x4364f7`) and the sparkle (the second animation) are drawn after the widgets
            ops.append(Image(path, ox + x, oy + y))
        if self.spark_draw is not None:
            frame, (x, y) = self.spark_draw
            ops.append(Sprite(SPARK, frame, ox + x, oy + y))
        ops += self.name_ops(ox, oy)
        if self.tips_win is not None:
            ops += self.tips_win.ops(self.tips_text(), self.tips_hover, self.tips_down if self.tips_down == self.tips_hover else None, ox, oy)
        return Scene(ops)
