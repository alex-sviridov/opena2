"""The shopkeeper panel's animation state (m2 shop fixes, docs/engine/shop-rea2.md 3-4; CONFIRMED in the exe, INFERRED where marked there): which bitmaps the keeper scene draws now.
Pure (no pygame): time comes in as milliseconds, the dice from a `random.Random`, the answer is a list of `Pic(path, x, y)` (panel-relative, painted in order over the
shopkeeper picture, black = transparent) plus the highlight of the selected shelf.

Human (town 1): the clicked shelf plays `shopanim\\%02d\\N.bmp` (set `4 - shelf`; files 1, 2, 3 then 4..9 looping), the keeper idles (`Pose2-3\\1.bmp`) and every 5-9 s plays
files 2..28; Yes / No clips `Yes\\2..12` / `No\\2..12`.  Druid (3) and Kaarg (2): a static `hili_*` picture on the clicked shelf, an `a1` / `a2` idle clip (a2 also on a buy / sell),
the druid's `elven` shelf picture once `Var(0x302)` is set, the Kaarg brazier (`fire\\dark` / `fire\\select`)."""

from dataclasses import dataclass

TICK_MS = 100
NONE = None                                         # no shelf selected (the exe's 100)

KEEPER_AT = {1: (113, 112), 3: (197, 92), 2: (125, 116)}
IDLE = {1: "movies/shopanim/Pose2-3/1.bmp", 3: "movies/shop_druid/a10001.bmp", 2: "movies/shop_kaarg/a10000.bmp"}
CLIP_FILES = {3: 30, 2: 20}                         # druid / Kaarg `a1` / `a2` clips: `counter % N`, files 2..N
HUMAN_IDLE_END = 28
YES_NO_LEN = 12

# human highlight clips: shelf -> (set number, draw at)
HUMAN_CLIP = {0: (4, (189, 108)), 1: (3, (33, 108)), 2: (2, (149, 20)), 3: (1, (37, 20))}
# druid / Kaarg static highlights: shelf -> (file, draw at)
HILITE = {3: {0: ("hili_armor", (5, 112)), 1: ("hili_magic", (5, 52)), 2: ("hili_potion", (121, 36)), 3: ("hili_elven", (93, 172))},
          2: {0: ("hili_armor", (5, 8)), 1: ("hili_magic", (49, 72)), 2: ("hili_potion", (49, 8)), 3: ("hili_weapon", (153, 8))}}
ART = {2: "graphics/interface/shop_kaarg/", 3: "graphics/interface/shop_druid/"}
ELVEN_AT = (93, 172)
FIRE_AT = (193, 204)


@dataclass(frozen=True)
class Pic:
    path: str
    x: int
    y: int


class Keeper:
    def __init__(self, town, rng):
        self.town, self.rng = town, rng
        self.sel = NONE
        self.acc = 0
        self.rest = 0                               # ms since the last clip ended
        self.wait = self._draw_wait()
        self.idle = None                            # (kind, counter): human "idle"; druid / Kaarg "a1" / "a2"
        self.reply = None                           # (kind "yes" | "no", counter) (human)
        self.shelf_clip = {}                        # human: shelf -> counter
        self.fire, self.fire_dir = 0, 0             # Kaarg

    def _draw_wait(self):
        return self.rng.randrange(5) * 1000 + 5000

    # -- events ---------------------------------------------------------------------------------------------------------------------
    def select(self, shelf):
        """An accepted shelf click (`+0xa4`): the old shelf's clip ends on the next step, the new one starts; the Kaarg brazier lights for the weapons shelf (3)."""
        old = self.sel
        if old is not NONE:
            if self.town == 1 and old in self.shelf_clip:
                self.shelf_clip[old] = 9
            if self.town == 2:
                if shelf == 3 and self.fire < 12:
                    self.fire_dir = 1
                elif shelf != 3 and self.fire > 0:
                    self.fire_dir = -1
        if self.town == 1:
            self.shelf_clip[shelf] = 0
        self.sel = shelf

    def yes(self):
        """Human: the Yes clip; druid / Kaarg: a buy / sell plays the `a2` idle clip (bit `0x20`)."""
        if self.town == 1:
            if self.reply is None or self.reply[0] != "yes":
                self.reply = ("yes", 0)
        elif self.idle is None:
            self.idle = ("a2", 0)

    def no(self):
        """Human only (a refused buy); the druid / Kaarg `No` is never drawn."""
        if self.town == 1 and self.reply is None:
            self.reply = ("no", 0)

    # -- time -----------------------------------------------------------------------------------------------------------------------
    def update(self, dt_ms):
        self.acc += dt_ms
        while self.acc >= TICK_MS:
            self.acc -= TICK_MS
            self._tick()

    def _tick(self):
        for shelf in list(self.shelf_clip):
            c = self.shelf_clip[shelf] + 1
            if c == 9 and shelf == self.sel:
                c = 3
            if c >= 10:
                del self.shelf_clip[shelf]
            else:
                self.shelf_clip[shelf] = c
        if self.reply is not None:
            kind, c = self.reply
            self.reply = None if c + 1 >= YES_NO_LEN else (kind, c + 1)
            if self.reply is None:
                self.rest = 0
        if self.idle is not None:
            kind, c = self.idle
            c += 1
            if self.town == 1:
                self.idle = None if c >= HUMAN_IDLE_END else (kind, c)
            else:
                self.idle = None if c % CLIP_FILES[self.town] == 0 else (kind, c)
            if self.idle is None:
                self.rest = 0
        else:
            self.rest += TICK_MS
            if self.rest >= self.wait and self.reply is None and not self.shelf_clip_busy():
                self.wait = self._draw_wait()
                self.rest = 0
                self.idle = ("idle", 0) if self.town == 1 else ("a1" if self.rng.randrange(2) == 0 else "a2", 0)
        if self.town == 2:
            if self.fire_dir == 0:
                self.fire += 1
                if self.fire == 6:
                    self.fire = 0
                if self.fire > 17:
                    self.fire = 12
            else:
                self.fire += self.fire_dir
                if self.fire < 1 or self.fire > 16:
                    self.fire_dir = 0

    def shelf_clip_busy(self):
        return False                                # the idle scheduler tests only the keeper's own clip bits (`+0x240 & 0x10`)

    # -- what to draw ---------------------------------------------------------------------------------------------------------------
    def keeper_pic(self):
        """The keeper bitmap now (idle > Yes > No > rest, `0x4bb3d7`)."""
        x, y = KEEPER_AT[self.town]
        if self.town == 1:
            base = "movies/shopanim/"
            if self.idle is not None:
                return Pic("%sPose2-3/%d.bmp" % (base, self.idle[1] + 1), x, y)
            if self.reply is not None:
                kind, c = self.reply
                return Pic("%sPose2-3/1.bmp" % base if c == 0 else "%s%s/%d.bmp" % (base, "Yes" if kind == "yes" else "No", c + 1), x, y)
            return Pic(IDLE[1], x, y)
        d = "movies/shop_druid/" if self.town == 3 else "movies/shop_kaarg/"
        if self.idle is not None:
            kind, c = self.idle
            return Pic("%s%s%04d.bmp" % (d, kind, c + 1), x, y)
        return Pic(IDLE[self.town], x, y)

    def highlight_pics(self):
        """The clicked shelf's highlight: the human clip frame, the druid / Kaarg static picture."""
        out = []
        if self.town == 1:
            for shelf in sorted(self.shelf_clip):
                number, (x, y) = HUMAN_CLIP[shelf]
                out.append(Pic("graphics/interface/shopanim/%02d/%d.bmp" % (number, self.shelf_clip[shelf] + 1), x, y))
        elif self.sel is not NONE and self.sel in HILITE[self.town]:
            name, (x, y) = HILITE[self.town][self.sel]
            out.append(Pic("%s%s.bmp" % (ART[self.town], name), x, y))
        return out

    def fire_pic(self):
        """The Kaarg brazier frame (`dark` while the weapons shelf is not selected, `select` while it is), None in the other towns."""
        if self.town != 2:
            return None
        f = self.fire
        name, n = (("lite", f + 1) if f < 6 else ("burn", f - 5) if f < 12 else ("cicle", f - 11))
        return Pic("%sfire/%s/%s%d.bmp" % (ART[2], "select" if self.sel == 3 else "dark", name, n), *FIRE_AT)
