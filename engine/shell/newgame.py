"""New game (docs/engine/shell.md 3.2): the original's PreCreate screen (`+0x374`, ctor `0x43270d`, resource `0x466`): the stained-glass hall
`MainArea.bmp` (640x480) with a hit mask `Mask.bmp`: four heroes, three difficulty tablets, Cancel, OK and the name plate.  CONFIRMED: mask values,
bitmaps, `SFX\\ChrGen\\Ok.wav`, music `chrgen`, the level writes the difficulty 0/1/2 (`+0x20c`, Easy / Medium / Hard).  INFERRED from template matching
against `MainArea.bmp`: where each sub-bitmap sits (cancel (16, 400), OK (548, 400), name plate (172, 396), levels (8 / 296 / 580, 0), heroes
(116 / 180 / 392 / 456, 44), big portraits at x 112 for heroes 1-2 and 260 for 3-4, y 44) and the meaning of the bitmap suffixes (`l` = hover,
`lon` = chosen).  Not decoded yet (L2): the name field, the caption lines, the torch animation, the confirm panel and the character screen
`FUN_0049183e`; here OK starts the first campaign map with the chosen difficulty (a placeholder for L2's chain: the party is the map's own hero)."""

import numpy as np

from allods2.graphics import load_bmp

from .events import Move, Press, Release
from .scene import Image, Scene, Text
from .screen import Screen

DIR = "graphics/interface/chrgen/precreate/"
CLICK = "sfx/chrgen/ok.wav"
LEVELS = {20: 0, 40: 1, 60: 2}                          # mask value -> difficulty selector (Easy / Medium / Hard)
HEROES = {80: 0, 100: 1, 120: 2, 140: 3}
CANCEL, OK, PLATE = 160, 180, 200
LEVEL_AT = ((8, 0), (296, 0), (580, 0))
HERO_AT = ((116, 44), (180, 44), (392, 44), (456, 44))
BIG_AT = ((112, 44), (112, 44), (260, 44), (260, 44))
CANCEL_AT, OK_AT, PLATE_AT = (16, 400), (548, 400), (172, 396)
DEFAULT_NAME = "Master Oberic"                          # 0x5efba8
FIRST_MAP = "10"                                        # DECISION: the campaign's first mission until L2 builds the chain
DEFAULT_LEVEL = 1                                       # Medium (the exe's server default, ai.md 10.1)


class NewGame(Screen):
    name = "newgame"
    music = "chrgen"

    def __init__(self, shell):
        super().__init__(shell)
        self.mask = None

    def enter(self, **params):
        if self.mask is None:
            m = load_bmp(DIR + "mask.bmp", self.shell.fs)
            self.mask = np.asarray(m.index if m.index is not None else m.rgb[..., 0])
        self.hero, self.level, self.name_text = None, DEFAULT_LEVEL, DEFAULT_NAME
        self.under = 0
        self.pressed = 0

    def _at(self, x, y):
        ox, oy = self.origin
        x, y = x - ox, y - oy
        return int(self.mask[y, x]) if 0 <= x < 640 and 0 <= y < 480 else 0

    def can_start(self):
        return self.hero is not None

    def event(self, ev):
        if isinstance(ev, Move):
            self.under = self._at(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.under = self.pressed = self._at(ev.x, ev.y)
            if self.under in LEVELS or self.under in HEROES or self.under in (CANCEL, OK):
                if self.under != OK or self.can_start():
                    self.shell.play(CLICK)
        elif isinstance(ev, Release) and ev.button == 1:
            self.under = self._at(ev.x, ev.y)
            hit, self.pressed = self.pressed, 0
            if hit != self.under:
                return None
            if hit in LEVELS:
                self.level = LEVELS[hit]
            elif hit in HEROES:
                self.hero = HEROES[hit]
            elif hit == CANCEL:
                return "menu"                           # Cancel (0x446): kind 2 posts 0x421
            elif hit == OK and self.can_start():
                return "game", {"map": FIRST_MAP, "difficulty": self.level + 1, "hero": self.hero, "name": self.name_text}
        return None

    def update(self, dt_ms):
        return None

    def scene(self):
        ox, oy = self.origin
        ops = [Image(DIR + "mainarea.bmp", ox, oy)]
        for n, (x, y) in enumerate(LEVEL_AT):
            chosen, hot = self.level == n, LEVELS.get(self.under) == n
            if chosen:
                ops.append(Image(DIR + "levels/level%dlon.bmp" % n, ox + x, oy + y))
            elif hot:
                ops.append(Image(DIR + "levels/level%dl.bmp" % n, ox + x, oy + y))
        for n, (x, y) in enumerate(HERO_AT):
            if self.hero == n:
                bx, by = BIG_AT[n]
                ops.append(Image(DIR + "heroes/h%dsel.bmp" % (n + 1), ox + bx, oy + by))
            elif HEROES.get(self.under) == n:
                ops.append(Image(DIR + "heroes/h%don.bmp" % (n + 1), ox + x, oy + y))
        ops.append(Image(DIR + "tablol.bmp", ox + PLATE_AT[0], oy + PLATE_AT[1]))
        ops.append(Text(self.name_text, ox + PLATE_AT[0] + 156, oy + PLATE_AT[1] + 42, 1, "normal", 2 | 8))
        if self.under == CANCEL:
            ops.append(Image(DIR + "cancell.bmp", ox + CANCEL_AT[0], oy + CANCEL_AT[1]))
        if self.under == OK and self.can_start():
            ops.append(Image(DIR + "okl.bmp", ox + OK_AT[0], oy + OK_AT[1]))
        return Scene(ops)
