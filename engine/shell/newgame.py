"""New game (docs/engine/shell.md 3.3): the original's PreCreate screen (`+0x374`, ctor `0x43270d`, resource `0x466`, class vtable `0x5cb998`): the stained-glass hall
`MainArea.bmp` (640x480) with a hit mask `Mask.bmp` (red channel): four heroes, three difficulty tablets, Cancel, OK and the name plate with an edit field.

CONFIRMED (REA, shell.md 3.3): the widget rects (ctor: levels (8 / 296 / 580, 0), heroes (116 / 180 / 392 / 456, 44), Cancel (16, 400), OK (548, 400)); the screen **acts on the
mouse press** (`0x436d48`; a move with the button held selects too), not on the release; hero value 0 Aldor (male fighter), 1 Sagita (female fighter), 2 Galinel (female mage),
3 Gildarius (male mage); the show routine selects hero 0 (`+0x208 := 0`) and the level `+0x20c`; level tablet states 1 selected = `level<n>on`, 2 hover = `level<n>l`, 3 both =
`level<n>lon`; the big portrait `h<n>sel` of the selected hero becomes `h<n>sel<partner>` while its partner pane is lit (pairs 1-2 and 3-4); the name field (`0x4321e9`,
`0x432397`, `0x437829`, `0x437955`): printable characters (>= 0x20) up to **10**, Backspace deletes the last one, the caret is always at the end (`|` blinking every 500 ms),
Enter = OK and ESC = Cancel, **an empty name does nothing**, typing plays `SFX\\Letter2.wav` (INFERRED: the index `+0x1e8` stays 0), clicks `ChrGen\\Level1-3.wav` / `Char.wav` /
`Ok.wav`; clicking a hero swaps the name for its default name (`npcnames` 0x17..0x1a) only while the field holds a default name or "Unnamed" (`0x437d90`); the initial name is
"Master Oberic", a default name is reset to "Aldor" (`npcnames` 0x14) on the next show.  Font4 draws the name at (300, 433), left aligned.
INFERRED: the initial level is 0 (Easy: the window's `+0x20c` is never initialised before the show; the exe's own selector 1 = Medium is overwritten by the window's level at OK),
the focus sits on the name field from the start, the position of the big portraits (template matching: x 112 for heroes 0-1, 260 for 2-3, y 44), Cancel plays `ChrGen\\Ok.wav`.
Torches: `torch1` / `torch2` are 15-frame flame animations (48x72) on the two braziers, at **(4, 200)** and **(589, 200)** (CONFIRMED by pixel identity: the frames' static pixels equal `MainArea.bmp` there with error
0), advanced by a global 67 ms timer (`0x436222`; the exe starts each torch at a random frame, here 0 and 7).
Not built: the hover cross-fade `0x4364f7`, the tips window `#tips8` (the TipsMode option is not built; the tips window is a framed dialog with an OK button, class `0x4dec24`), the character generator panel `+0x36c` that follows OK (shell.md 3.3: L2); OK here starts the first campaign map (`10`) with the level and the hero's code."""

import numpy as np

from allods2.graphics import load_bmp

from .events import Key, Move, Press, Release
from .scene import Image, Scene, Text
from .screen import Screen

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
HERO_NAMES = ("Aldor", "Sagita", "Galinel", "Gildarius")      # male fighter, female fighter, female mage, male mage (npcnames 0x17..0x1a; 0x19 / 0x1a are Gildarius / Galinel in the file)
HERO_CODE = (0x00, 0x80, 0xC0, 0x40)                    # `window+0x484 >> 0` per hero value: bit 0x40 mage, bit 0x80 female (`4891d8`, table `0x5cdd60`)
UNNAMED = "Unnamed"
INITIAL_NAME = "Master Oberic"                          # 0x5efba8
FIRST_MAP = "10"                                        # DECISION: the campaign's first mission until L2 builds the chain
DEFAULT_LEVEL = 0                                       # INFERRED (see the module doc)
BLINK_MS = 500
TORCH_AT = ((4, 200), (589, 200))                       # CONFIRMED by pixel identity of the static part of the frames against `MainArea.bmp`
TORCH_FRAMES, TORCH_MS, TORCH_START = 15, 67, (0, 7)     # 15 frames, the global timer's 67 ms (`0x436222`); the exe's random start frame is a DECISION here


def is_default_name(name):
    """`0x437d90`: one of the four hero names or "Unnamed" (case-insensitive)."""
    return name.lower() in {n.lower() for n in HERO_NAMES} | {UNNAMED.lower()}


class NewGame(Screen):
    name = "newgame"
    music = "chrgen"

    def __init__(self, shell):
        super().__init__(shell)
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
        self.blink_on, self.blink_ms = True, 0
        self.anim_ms = 0

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
        return "game", {"map": FIRST_MAP, "difficulty": self.level + 1, "hero": self.hero, "hero_code": HERO_CODE[self.hero],
                        "name": self.name_text}

    def _cancel(self):
        self.shell.play(OK_SOUND)                            # `0x437955` plays the Cancel sound (the second `ChrGen\Ok.wav`)
        return "menu"

    def event(self, ev):
        if isinstance(ev, Move):
            self.under = self._at(ev.x, ev.y)
            if self.held:
                self._select(self.under)
        elif isinstance(ev, Press) and ev.button == 1:
            self.under = v = self._at(ev.x, ev.y)
            self.held = True
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
        return None

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
        text = self.name_text + ("|" if self.blink_on else "")
        ops.append(Text(text, ox + NAME_AT[0], oy + NAME_AT[1], NAME_FONT, "normal", 0, 0))
        return Scene(ops)
