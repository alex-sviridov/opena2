"""The three town scenes (L6, docs/engine/town-scenes.md): hit mask, click table, hover and the animation state machines, as pure code.

No pygame, no shell import.  `engine/shell/town.py` is the screen over it.  Everything the scenes read from the install is read here at run time (`Mask.load`,
`SceneSpec.measure`: frame counts of the sprite sets / bitmap lists); nothing derived from the game files is stored in the repository.

`SceneState` = one open scene: `advance(dt_ms)` is one *draw* of the exe (the starters run every draw, the step - hover, the human random rolls, the tick - runs
once the wall clock passed 67 ms human / 100 ms druid and Kaarg since the last step, `> period` as the exe tests it), `hover(region)` is the mouse-move / step hover,
`press(region)` the left press, `draw_ops()` the layers in the exe's draw order, `take_sounds()` the sounds started since the last call.  Randomness is an
injected `random.Random` (`rand(n)` = `randrange(n)`, `FUN_004a0fd0`); the process-global counters and delays live in `Globals`.

Marks as in the spec: INFERRED parts are marked in the comments (the woman's step body, the druid / Kaarg timer stamps, the baba idle draw, the once-per-frame horse sound,
the initial guard-sound latch)."""

from dataclasses import dataclass, field

import numpy as np

W, H = 640, 480
SHOP, INN, LEAVE, MENU = 1, 2, 8, 0x10                 # region flags (the other flags are the NPC regions)
LEAVE_GATE, CHAPTER = 0x301, 0x300                      # Scenario variables

REGION_OF_BYTE = {0x80: 2, 0x90: 1, 0xa0: 8, 0xb0: 0x10, 0xc0: 4, 0x20: 0x400, 0x40: 0x800, 0x50: 0x1000, 0x60: 0x200}      # `0x4cd8b7`; every other byte -> -1
BYTE_OF_REGION = {v: k for k, v in REGION_OF_BYTE.items()}

TOWN_DIR = {1: "graphics/interface/town/", 2: "graphics/interface/town_kaarg/", 3: "graphics/interface/town_druid/"}
BIRDS_DIR = "graphics/interface/townbirds/"
SFX = {1: "sfx/town/", 2: "sfx/town_kaarg/", 3: "sfx/town_druid/"}
ENTRY_LOOP = {1: "sfx/town/crowd.wav", 2: "sfx/town_kaarg/kvox1.wav", 3: "sfx/town_druid/dforest1.wav"}        # looped, priority 0x80
RACE = {1: "human", 2: "kaarg", 3: "druid"}
STEP_MS = {1: 67, 2: 100, 3: 100}


class Globals:
    """The exe's process globals (they survive visits, town-scenes 6): the stars play counter `0x628260`, the first-bird delay `0x628254`, the druid birds / trees
    delays `0x628234 / 0x628244`, the Kaarg voices / birds delays `0x628224 / 0x628240`.  None = not rolled yet (the first value is rolled once per process)."""

    def __init__(self):
        self.stars = 0
        self.bird_delay = self.druid_birds = self.druid_trees = self.kaarg_voices = self.kaarg_birds = None


# -- the hit mask ---------------------------------------------------------------------------------------------------------------------------

class Mask:
    """`townmask.bmp` (8-bit 640x480, top row first).  `region_at` is `0x4cd8b7`: the point minus the window origin, -1 outside the 640x480 rect, else the table
    lookup of the byte (the dither noise pixels give whatever their byte says: a faithful port)."""

    def __init__(self, index):
        self.index = index

    @classmethod
    def load(cls, fs, town):
        from allods2.graphics.bmp import load_bmp
        bm = load_bmp(TOWN_DIR[town] + "townmask.bmp", fs)
        return cls(bm.index if bm.index is not None else bm.rgb[..., 0])          # a grey-palette file comes back as plain RGB: the grey value is the byte

    def region_at(self, x, y, origin=(0, 0)):
        x, y = x - origin[0], y - origin[1]
        if not (0 <= x < W and 0 <= y < H):
            return -1
        return REGION_OF_BYTE.get(int(self.index[y, x]), -1)

    def point_of(self, region):
        """A point of `region` deep inside its dense area (nearest pixel to the median whose 3x3 neighbourhood is all the same byte), None when the mask has none."""
        ys, xs = np.nonzero(self.index == BYTE_OF_REGION[region])
        if len(xs) == 0:
            return None
        mx, my = np.median(xs), np.median(ys)
        for i in np.argsort((xs - mx) ** 2 + (ys - my) ** 2):
            x, y = int(xs[i]), int(ys[i])
            if 0 < x < W - 1 and 0 < y < H - 1 and (self.index[y - 1:y + 2, x - 1:x + 2] == self.index[y, x]).all():
                return x, y
        return int(xs[0]), int(ys[0])


class StandInMask:
    """The scene without an install: three non-overlapping rectangles (shop / inn / leave), so the visit loop runs headless."""
    RECTS = {SHOP: (60, 100, 140, 120), INN: (250, 100, 140, 120), LEAVE: (440, 100, 140, 120)}          # x, y, w, h

    def region_at(self, x, y, origin=(0, 0)):
        x, y = x - origin[0], y - origin[1]
        for region, (rx, ry, rw, rh) in self.RECTS.items():
            if rx <= x < rx + rw and ry <= y < ry + rh:
                return region
        return -1

    def point_of(self, region):
        r = self.RECTS.get(region)
        return None if r is None else (r[0] + r[2] // 2, r[1] + r[3] // 2)


# -- the data of a scene --------------------------------------------------------------------------------------------------------------------

def _default_count(path):
    """The frame counts the spec measured on the install, used until `SceneSpec.measure` reads the files (synthetic tests)."""
    p = path.lower()
    table = (("townbirds/tavern", 10), ("townbirds/shopie", 30), ("town/door", 9), ("townbirds/guards", 8), ("town/stars", 9), ("town/sign", 10), ("town/fluger", 8),
             ("townbirds/birds", 57), ("townbirds/horse", 15), ("townbirds/baba", 31), ("townbirds/dervish", 30), ("town_druid/bug", 183), ("town_druid/lizard", 42),
             ("town_kaarg/dervish", 30), ("town_kaarg/guard", 55), ("town_kaarg/maingates", 11))
    if "town_kaarg/girl" in p:
        return 31 if "/g1" in p else 30
    if "town_druid/man" in p:
        return (19, 19, 20)[int(p.rsplit("/a", 1)[1][0]) - 1]
    if "town_druid/woman" in p:
        return (15, 20, 20)[int(p.rsplit("/a", 1)[1][0]) - 1]
    if "townbirds/baba" in p:
        return 32 if "/a2/" in p else 31
    return next(n for k, n in table if k in p)


@dataclass
class SceneSpec:
    """What differs per town: the step period, the entry loop, the hover patches and the click table; `counts` = measured frame counts by the path used with
    `count()` (a sprite file path or a bitmap-list key such as `town_druid/man/a1`)."""
    town: int
    race: str
    step_ms: int
    base: str
    entry_loop: str
    hover_patch: dict = field(default_factory=dict)        # region -> (path, x, y)
    counts: dict = field(default_factory=dict)

    @classmethod
    def for_town(cls, town, counts=None):
        d = TOWN_DIR[town]
        patches = {1: {1: (d + "shop_l.bmp", 0x108, 0x108), 2: (d + "tavern_l.bmp", 0x90, 0x14c)},
                   3: {1: (d + "hili_shop.bmp", 0x1a4, 0xe0), 2: (d + "hili_tavern.bmp", 0, 0xb8)},
                   2: {1: (d + "hili_shop.bmp", 0x148, 0x100), 2: (d + "hili_tavern.bmp", 0x1e0, 0xc4)}}[town]
        return cls(town, RACE[town], STEP_MS[town], d, ENTRY_LOOP[town], patches, dict(counts or {}))

    def count(self, key):
        return self.counts[key] if key in self.counts else _default_count(key)

    def measure(self, fs):
        """Frame counts from the install: sprite files by their frame number, bitmap lists by probing 0.. / 1.. until the first missing file (`0x4ce914` loops, the
        Kaarg lists).  Keys not present stay on the defaults."""
        from allods2.graphics import SpriteFile
        for key in self.asset_keys():
            try:
                if key.endswith(".16a"):
                    self.counts[key] = len(SpriteFile.load(key, fs).sprites)
                else:
                    self.counts[key] = self._probe(fs, key)
            except (KeyError, OSError, ValueError):
                self.counts[key] = 0
        return self

    @staticmethod
    def _probe(fs, key):
        """`key` = `dir/prefix` (`town_druid/man/a1`: files `a10001.bmp`..; Kaarg `girl1/g1`: `g1000`..): the number of consecutive files."""
        first = 1 if ("town_druid" in key or key.endswith("/g2")) else 0              # the Kaarg girls' second variant is numbered g2001..g2030 (measured; the spec said g2000..)
        width = 3 if "/girl" in key else 4
        d, _, prefix = key.rpartition("/")
        n = 0
        while fs.exists("%s/%s%0*d.bmp" % (d, prefix, width, first + n)):
            n += 1
        return n

    def asset_keys(self):
        b, t = BIRDS_DIR, self.base
        if self.town == 1:
            keys = [b + "tavern/sprites.16a", b + "shopie/sprites.16a", b + "guards/sprites.16a"]
            keys += ["%sbirds%d/sprites.16a" % (b, i) for i in range(1, 10)]
            keys += ["%shorse%d/a%d/sprites.16a" % (b, k, a) for k in range(1, 6) for a in range(1, 4)]
            keys += ["%sbaba%d/a%d/sprites.16a" % (b, k, a) for k in range(1, 5) for a in range(1, 3)]
            keys += ["%sdervish%d/sprites.16a" % (b, k) for k in range(1, 5)]
            return keys
        if self.town == 3:
            return [t + "bug/sprites.16a", t + "lizard/sprites.16a"] + ["%s%s/a%d" % (t, who, v) for who in ("man", "woman") for v in (1, 2, 3)]
        return [t + "girl%d/g%d" % (g, v) for g in (1, 2) for v in (1, 2)] + [t + "guard/g", t + "dervish/d", t + "maingates/m"]


def load_scene(fs, town, counts=None):
    """`(spec, mask, real)`: the spec with the measured counts and the real mask of the install; the stand-in mask (`real` False) when `fs` is None or the files are missing."""
    spec = SceneSpec.for_town(town, counts)
    if fs is None:
        return spec, StandInMask(), False
    try:
        mask = Mask.load(fs, town)
    except (KeyError, OSError, ValueError):
        return spec, StandInMask(), False
    return spec.measure(fs), mask, True


# -- click table (CONFIRMED, town-scenes 2.1) -----------------------------------------------------------------------------------------------

SPEECH = {1: {},
          2: {4: "kaargwoman_%d", 0x200: "kaargwoman_%d", 0x400: "kaargman_%d", 0x800: "kaargguard_%d"},
          3: {0x200: "druidinnkeeper_%d", 0x1000: "druidshopkeeper_%d"}}


def click(town, region, var):
    """The outcome of a left press on `region`: ("shop",), ("inn",), ("leave",), ("menu",) (INFERRED: message `0x41f`, the in-game menu), ("speech", name) or None.  The human
    leave gate (`Var(0x301)`) is `TownCore.leave_town`'s: the scene only reports "leave"."""
    if region == SHOP:
        return ("shop",)
    if region == INN:
        return ("inn",)
    if region == LEAVE:
        return ("leave",)
    if region == MENU:
        return ("menu",)
    name = SPEECH[town].get(region)
    return ("speech", name % var(CHAPTER)) if name else None


# -- the state machines ---------------------------------------------------------------------------------------------------------------------

class SceneState:
    """One open scene.  Subclasses: `Human`, `Druid`, `Kaarg` (`SceneState.build` picks by town)."""

    def __init__(self, spec, rng, glob=None, var=None):
        self.spec, self.rng, self.g = spec, rng, glob or Globals()
        self.var = var or (lambda n: 0)
        self.now = self.last_step = 0                   # ms on the scene's own clock (the load stamps are 0)
        self.region = -1                                # `+0xb4`
        self.flags = 0                                  # `+0x208`
        self.sounds = []
        self.latch = set()                              # the entry-sound latches
        if spec.entry_loop:
            self.sounds.append((spec.entry_loop, True))

    @staticmethod
    def build(spec, rng, glob=None, var=None):
        return {1: Human, 2: Kaarg, 3: Druid}[spec.town](spec, rng, glob, var)

    # -- helpers
    def rand(self, n):
        return self.rng.randrange(n)

    def play(self, path, loop=False):
        self.sounds.append((path, loop))

    def sfx(self, name):
        self.play(SFX[self.spec.town] + name)

    def take_sounds(self):
        out, self.sounds = self.sounds, []
        return out

    def count(self, key):
        return self.spec.count(key)

    def path(self, rel):
        return self.spec.base + rel

    # -- the clock (the exe's draw)
    def advance(self, dt_ms):
        self.now += dt_ms
        if self.now - self.last_step > self.spec.step_ms:
            self.hover(self.region)
            self.rolls()
            self.tick()
            self.last_step = self.now
        self.starters()                                                    # order step / starters INFERRED: a started animation shows its frame 0 in the draw that starts it
        self.after_draw()

    def starters(self):
        pass

    def rolls(self):
        pass

    def tick(self):
        pass

    def after_draw(self):
        pass

    def hover(self, region):
        self.region = region

    def press(self, region, vars=None):
        return click(self.spec.town, region, vars or self.var)

    def draw_ops(self):
        raise NotImplementedError

    # drawing helpers: ("bmp", path, x, y, key) and ("spr", path, frame, x, y)
    @staticmethod
    def bmp(path, x, y, key=False):
        return ("bmp", path, x, y, key)

    @staticmethod
    def spr(path, frame, x, y):
        return ("spr", path, frame, x, y)


class Human(SceneState):
    """Town 1 (`0x4ca23c`).  Flags: 1 shopie, 2 tavern, 0x10 stars, 0x20 fluger, 0x40 sign, 0x80 birds, 0x100 horse, 0x200 baba, 0x400 dervish."""
    TAV, SHOPIE, GATE, SIGN, FLUGER, STARS, SHOP_L, TAV_L = (124, 312), (276, 296), (180, 148), (360, 232), (308, 64), (340, 288), (264, 264), (144, 332)
    GUARDS = (184, 158)
    HORSE_POS = ((104, 404), (104, 404), (256, 344), (448, 400), (140, 400))                  # `0x5f66e0`
    BABA_POS = ((216, 364), (308, 424), (384, 424), (580, 384))                               # `0x5f6708`
    DERVISH_POS = ((224, 364), (324, 424), (392, 420), (592, 388))                            # `0x5f6728`

    def __init__(self, spec, rng, glob=None, var=None):
        super().__init__(spec, rng, glob, var)
        self.horse_kind = self.rand(5)                                  # `0x4cb6c6`: per visit
        self.baba_kind = self.rand(4)
        self.dervish_kind = self.rand(4)
        while self.dervish_kind == self.baba_kind:
            self.dervish_kind = self.rand(4)
        self.flags = 0x400                                              # the dervish runs for the whole visit
        self.tav = self.shopie = self.sign = self.fluger = self.stars = 0
        self.stars_frame = 0                                            # `+0x1bc`: 0 = nothing drawn
        self.gate, self.gate_snd = 8, 0
        self.guard_f, self.guard_dir = spec.count(BIRDS_DIR + "guards/sprites.16a") - 1, 1
        self.guard_snd = 1                                              # `+0xf0`, heap in the exe; INFERRED 1: the guards start up, so the first guard sound is Guard1
        self.dervish = 0
        self.horse = self.baba = -1                                     # frame counters, -1 = idle
        self.horse_set = self.baba_set = 0
        self.horse_base = self.baba_base = 0
        self.horse_delay, self.baba_delay = self.rand(2000) + 2000, self.rand(2000) + 2000        # first deadlines after the load (`0x4ca7e2`)
        self.bird_base = 0
        self.bird_group = self.bird_count = 0
        self.bird_f = [0, 0, 0]
        if self.g.bird_delay is None:
            self.g.bird_delay = self.rand(2000) + 1000
        self.horse_latch = None

    # -- paths
    def horse_path(self):
        return "%shorse%d/a%d/sprites.16a" % (BIRDS_DIR, self.horse_kind + 1, self.horse_set + 1)

    def baba_path(self):
        return "%sbaba%d/a%d/sprites.16a" % (BIRDS_DIR, self.baba_kind + 1, self.baba_set + 1)

    def dervish_path(self):
        return "%sdervish%d/sprites.16a" % (BIRDS_DIR, self.dervish_kind + 1)

    # -- starters (every draw: `0x4cda92`, `0x4cae28`)
    def starters(self):
        if not self.flags & 0x80 and self.now - self.bird_base > self.g.bird_delay:                   # birds (`0x4cb05d`)
            self.flags |= 0x80
            self.bird_group = self.rand(3)
            self.bird_count = self.rand(3) + 1
            self.sfx("birds1.wav" if self.bird_count == 1 else "birds2.wav")
            self.g.bird_delay = self.rand(2000) + 1000                                                 # the next first-delay / the value returned
            self.bird_f = [0, 0, 0]
        if not self.flags & 0x200 and self.now - self.baba_base > self.baba_delay:                    # `0x4cd73b`
            self.baba_delay = self.rand(5000) + 2000
            self.baba, self.baba_set = 0, self.rand(2)
            self.flags |= 0x200
        if not self.flags & 0x100 and self.now - self.horse_base > self.horse_delay:                  # `0x4cd7d0`
            self.horse_delay = self.rand(5000) + 2000
            self.horse, self.horse_set = 0, self.rand(3)
            self.flags |= 0x100

    # -- hover (`0x4cdbea`)
    def hover(self, region):
        self.region = region
        self.guard_dir = 1
        if region == -1:
            self.latch.discard("shop")
        elif region == SHOP:
            if self.rand(100) > 0x5f and not self.flags & 1:                                           # 4 % per step
                self.flags |= 1
            if "shop" not in self.latch:
                self.latch.add("shop")
                self.play("sfx/town/shop/enter.wav")
        elif region == INN:
            self.flags |= 2
        elif region == 4:
            pass
        elif region == LEAVE:
            self.guard_dir = -1 if self.var(LEAVE_GATE) == 0 else 1
        else:
            self.flags |= region                                                                       # 0x10 stars; 0x200 / 0x400 / 0x800 / 0x1000 OR-ed as the exe does

    def rolls(self):
        if self.rand(100) > 0x5e:                                                                      # sign 5 %
            self.flags |= 0x40
        if self.rand(100) > 0x61:                                                                      # fluger 2 %
            self.flags |= 0x20

    # -- tick (`0x4cd606`)
    def _run(self, counter, n, flag, sound=None):
        """One step of a counted animation: the sound at counter 0, then ++, at `n` -> 0 and the flag clears."""
        if counter == 0 and sound:
            self.sfx(sound)
        counter += 1
        if counter >= n:
            counter = 0
            self.flags &= ~flag
        return counter

    def tick(self):
        f = self.flags
        if f & 1:
            self.shopie = self._run(self.shopie, self.count(BIRDS_DIR + "shopie/sprites.16a"), 1)
        if f & 2:
            self.tav = self._run(self.tav, self.count(BIRDS_DIR + "tavern/sprites.16a"), 2, "point.wav")
        self._gate()
        if f & 0x10:
            self._stars()
        if f & 0x40:
            self.sign = self._run(self.sign, self.count(TOWN_DIR[1] + "sign"), 0x40, "flag.wav")
        if f & 0x20:
            self.fluger = self._run(self.fluger, self.count(TOWN_DIR[1] + "fluger"), 0x20, "flugel.wav")
        if f & 0x80:
            for k in range(self.bird_count):
                self.bird_f[k] += 1
        if f & 0x400:
            n = self.count(self.dervish_path())
            self.dervish = (self.dervish + 1) % n if n else -1
        if f & 0x200:
            self.baba += 1
            self.baba_base = self.now
            if self.baba >= self.count(self.baba_path()):
                self.baba = -1
                self.flags &= ~0x200
        if f & 0x100:
            self.horse += 1
            self.horse_base = self.now
            if self.horse >= self.count(self.horse_path()):
                self.horse = -1
                self.flags &= ~0x100
        self._guards()

    def _gate(self):
        if self.var(LEAVE_GATE) == 0:
            self.gate = 8                                                                              # closed
        elif self.region == LEAVE:
            if self.gate > 0:
                if self.gate_snd != 1:
                    self.gate_snd = 1
                    self.sfx("gateup.wav")
                self.gate -= 1
        elif self.gate < 8:
            if self.gate_snd != 2:
                self.gate_snd = 2
                self.sfx("gatedn.wav")
            self.gate += 1

    def _stars(self):
        """`0x4cd2ac` (CONFIRMED): sound at counter 0; frames 1..8; at 9 the global counter ++ (10 -> both zero), nothing shown, the flag clears."""
        if self.stars == 0:
            self.sfx("stars.wav")
        self.stars += 1
        if self.stars < 9:
            self.stars_frame = self.stars
        else:
            self.g.stars += 1
            if self.g.stars == 10:
                self.stars = 0
                self.g.stars = 0
            self.stars_frame = 0
            self.flags &= ~0x10

    def _guards(self):
        """`0x4cce81` (CONFIRMED, REA): frame += dir; Guard2 when dir is +1 and the latch is 0, Guard1 when dir is -1 and the latch is set; clamp at 0 and n-1 (dir reset)."""
        n = self.count(BIRDS_DIR + "guards/sprites.16a")
        self.guard_f += self.guard_dir
        if self.guard_dir == 1 and self.guard_snd == 0:
            self.sfx("guard2.wav")
            self.guard_snd = 1
        elif self.guard_dir == -1 and self.guard_snd != 0:
            self.sfx("guard1.wav")
            self.guard_snd = 0
        if self.guard_f < 0:
            self.guard_dir = self.guard_f = 0
        elif self.guard_f >= n:
            self.guard_dir = 0
            self.guard_f = n - 1

    def after_draw(self):
        """The parts of the exe's draw that are not the step: the bird flyers end and stamp (`0x4caf00`), the horse sounds (INFERRED: once per frame, the exe fires
        on every draw the frame matches)."""
        if self.flags & 0x80:
            n = self.count("%sbirds%d/sprites.16a" % (BIRDS_DIR, self.bird_group * 3 + 1))
            if all(self.bird_f[k] >= n for k in range(self.bird_count)):
                self.flags &= ~0x80
            self.bird_base = self.now
        key = (self.horse_set, self.horse)
        if self.horse >= 0 and key != self.horse_latch:
            s, f = key
            if f == 14 and s in (0, 1, 2) or (s == 1 and f == 8):
                self.sfx("horse2.wav")
            elif s == 2 and f == 1:
                self.sfx("horse1.wav")
        self.horse_latch = key if self.horse >= 0 else None

    # -- draw (`0x4cb05d`, town-scenes 3.4)
    def draw_ops(self):
        t = TOWN_DIR[1]
        ops = [self.bmp(t + "townmain.bmp", 0, 0)]
        if self.flags & 0x80:
            for k in range(self.bird_count):
                path = "%sbirds%d/sprites.16a" % (BIRDS_DIR, self.bird_group * 3 + k + 1)
                if self.bird_f[k] < self.count(path):
                    ops.append(self.spr(path, self.bird_f[k], 0, 0))
            ops.append(self.bmp(t + "town_add.bmp", 0, 0, True))                                       # colour-key blit over the flyers (CONFIRMED: only while flyers are up)
        if self.region == SHOP:
            ops.append(self.bmp(t + "shop_l.bmp", *self.SHOP_L))
        if self.region == INN:
            ops.append(self.bmp(t + "tavern_l.bmp", *self.TAV_L))
        ops.append(self.spr(BIRDS_DIR + "tavern/sprites.16a", self.tav, *self.TAV))
        ops.append(self.bmp(t + "sign/v%02d.bmp" % self.sign, *self.SIGN))
        ops.append(self.bmp(t + "door/t%02d.bmp" % self.gate, *self.GATE))
        if self.stars_frame:
            ops.append(self.bmp(t + "stars/s%02d.bmp" % self.stars_frame, *self.STARS))
        ops.append(self.spr(BIRDS_DIR + "shopie/sprites.16a", self.shopie, *self.SHOPIE))
        ops.append(self.bmp(t + "fluger/f%02d.bmp" % self.fluger, *self.FLUGER))
        ops.append(self.spr(BIRDS_DIR + "guards/sprites.16a", self.guard_f, *self.GUARDS))
        ops.append(self.spr(self.horse_path(), max(self.horse, 0), *self.HORSE_POS[self.horse_kind]))       # frame -1 draws frame 0 (CONFIRMED)
        if self.baba >= 0:                                                                             # idle baba: not drawn (INFERRED, the spec only says -1)
            ops.append(self.spr(self.baba_path(), self.baba, *self.BABA_POS[self.baba_kind]))
        if self.dervish >= 0:
            ops.append(self.spr(self.dervish_path(), self.dervish, *self.DERVISH_POS[self.dervish_kind]))
        return ops


class Druid(SceneState):
    """Town 3 (`0x4ce2b9`).  Flags: 1 man (shop), 2 woman (inn), 0x80 bug, 0x100 lizard."""
    MAN_POS = {0: (0x150, 0xf4), 1: (0x150, 0xf4), 2: (0x154, 0xe0)}
    WOMAN_POS = {0: (0xa4, 0xc8), 1: (0xa4, 0xc8), 2: (0x98, 0xb8)}
    BUG_POS, LIZARD_POS = (0, 0xd4), (0, 0x12c)
    LIZARD = (                                                                                       # `0x5f68c8`, animation 4.11, frames 1-based, -1 ends
        (39, 40, 41, 42, 41, 40, 39, 38),
        tuple(range(28, 39)),
        (2, 3, 4, 5, 6, 7) + (8,) * 13 + (22, 23, 24, 25, 26, 27),
        (2, 3, 4, 5, 6, 7) + (8,) * 13 + tuple(range(9, 19)) + (19,) * 10 + tuple(range(20, 28)))

    def __init__(self, spec, rng, glob=None, var=None):
        super().__init__(spec, rng, glob, var)
        self.man_v = self.wom_v = -1                                    # variant of the running animation, -1 idle
        self.man_f = self.wom_f = 0
        self.man_stamp = self.wom_stamp = 0                             # timer stamps: the load's are unread (open question 4); INFERRED 0 = load
        self.man_delay, self.wom_delay = self.rand(5000) + 3500, self.rand(5000) + 3500
        self.bug_v, self.bug_f = -1, 0
        self.bug_stamp, self.bug_delay = 0, self.rand(10000) + 10000
        self.liz_seq, self.liz_i = -1, 0
        self.stamp = {"bird": None, "tree": None, "wolf": None}         # None = fires at the first draw (INFERRED like the Kaarg stamps: 0 at construction)
        for k in ("birds", "trees"):
            if getattr(self.g, "druid_" + k) is None:
                setattr(self.g, "druid_" + k, self.rand(2000) + 2000)

    def _list(self, who, v):
        return "%s%s/a%d" % (self.spec.base, who, v + 1)

    def _frames(self, who, v):
        return self.count(self._list(who, v))

    def starters(self):
        n, g = self.now, self.g
        if self.stamp["bird"] is None or n - self.stamp["bird"] > g.druid_birds:                                 # `0x4d00de`
            self.sfx("dbird%d.wav" % (self.rand(3) + 1))
            g.druid_birds, self.stamp["bird"] = self.rand(2000) + 2000, n
        if self.stamp["tree"] is None or n - self.stamp["tree"] > g.druid_trees:
            self.sfx("dtree%d.wav" % (self.rand(4) + 1))
            g.druid_trees, self.stamp["tree"] = self.rand(2000) + 2000, n
        if self.stamp["wolf"] is None or n - self.stamp["wolf"] > 60000:
            self.sfx("dwolf1.wav")
            self.stamp["wolf"] = n
        if self.man_v == -1 and n - self.man_stamp > self.man_delay:                                           # the ambient man starter: variant 2 over its region, else rand(2)
            self.man_v = 2 if self.region == SHOP else self.rand(2)
            self.man_f, self.man_stamp, self.man_delay = 0, n, self.rand(5000) + 3500
            self.flags |= 1
            self.sfx("ddruid1.wav")
        if self.wom_v == -1 and n - self.wom_stamp > self.wom_delay:                                           # INFERRED symmetric
            self.wom_v = 2 if self.region == INN else self.rand(2)
            self.wom_f, self.wom_stamp, self.wom_delay = 0, n, self.rand(5000) + 3500
            self.flags |= 2
            self.sfx("ddruid2.wav")
        if self.bug_v == -1 and n - self.bug_stamp > self.bug_delay:                                           # `0x4cfc77`
            self.bug_v, self.bug_f = self.rand(3), 0
            self.bug_stamp, self.bug_delay = n, self.rand(10000) + 10000
            self.flags |= 0x80
            self.sfx("dbug%d.wav" % (self.bug_v + 1))
        if self.liz_seq == -1:                                                                                  # restarts at once whenever idle
            r = self.rand(15)
            self.liz_seq = r + 1 if r < 3 else 0
            self.liz_i = 0
            self.flags |= 0x100
            self.sfx("dlizard%d.wav" % (self.liz_seq + 1))

    def hover(self, region):
        prev, self.region = self.region, region
        if region == -1:
            self.latch.clear()
        elif region == SHOP:
            if prev != SHOP and self.man_v != 2:                                                               # entering: man variant 2, one step now
                self.man_v, self.man_f = 2, -1
                self.flags |= 1
                self._man_step()
                self.sfx("ddruid1.wav")
            if "shop" not in self.latch:
                self.latch.add("shop")
                self.sfx("denter2.wav")
        elif region == INN:
            if prev != INN and self.wom_v != 2:
                self.wom_v, self.wom_f = 2, -1
                self.flags |= 2
                self._wom_step()
                self.sfx("ddruid2.wav")
            if "inn" not in self.latch:
                self.latch.add("inn")
                self.sfx("denter1.wav")
        elif region == LEAVE:
            if "out" not in self.latch:
                self.latch.add("out")
                self.sfx("dout.wav")
        elif region in (4, 0x200, 0x1000):
            return
        else:
            self.flags |= region

    def _man_step(self):
        self.man_f += 1
        if self.man_f >= self._frames("man", self.man_v):
            self.man_v, self.man_f = -1, 0
            self.flags &= ~1

    def _wom_step(self):                                                                                        # body INFERRED by symmetry with the man's `0x4cfbf6`
        self.wom_f += 1
        if self.wom_f >= self._frames("woman", self.wom_v):
            self.wom_v, self.wom_f = -1, 0
            self.flags &= ~2

    def tick(self):
        if self.flags & 1:
            self._man_step()
        if self.flags & 2:
            self._wom_step()
        if self.flags & 0x80:
            self.bug_f += 1
            if self.bug_f >= 61:
                self.bug_v, self.flags = -1, self.flags & ~0x80
        if self.flags & 0x100:
            self.liz_i += 1
            if self.liz_i >= len(self.LIZARD[self.liz_seq]):                                                    # the -1 end marker
                self.liz_seq, self.flags = -1, self.flags & ~0x100

    def draw_ops(self):
        b = self.spec.base
        ops = [self.bmp(b + "townmain.bmp", 0, 0)]
        if self.region == SHOP or self.man_v != -1:
            ops.append(self.bmp(*self.spec.hover_patch[1]))
        v = self.man_v if self.man_v != -1 else (2 if self.region == SHOP else 0)
        f = max(self.man_f, 0) if self.man_v != -1 else 0
        ops.append(self.bmp("%sman/a%d%04d.bmp" % (b, v + 1, f + 1), *self.MAN_POS[v]))
        if self.region == INN or self.wom_v != -1:
            ops.append(self.bmp(*self.spec.hover_patch[2]))
        v = self.wom_v if self.wom_v != -1 else (2 if self.region == INN else 0)
        f = max(self.wom_f, 0) if self.wom_v != -1 else 0
        ops.append(self.bmp("%swoman/a%d%04d.bmp" % (b, v + 1, f + 1), *self.WOMAN_POS[v]))
        if self.liz_seq != -1:
            ops.append(self.spr(b + "lizard/sprites.16a", self.LIZARD[self.liz_seq][min(self.liz_i, len(self.LIZARD[self.liz_seq]) - 1)] - 1, *self.LIZARD_POS))
        if self.bug_v != -1:
            ops.append(self.spr(b + "bug/sprites.16a", self.bug_v * 61 + self.bug_f, *self.BUG_POS))
        return ops


class Kaarg(SceneState):
    """Town 2 (`0x4d09ee`).  The NPCs run only from timers: flags 0x200 girl 1, 4 girl 2, 0x800 guard, 0x400 dervish."""
    NPC = {   # name: (flag, first delay (base, spread), later delay (base, spread), count key)
        "girl1": (0x200, (2000, 2000), (3500, 5000)), "girl2": (4, (2000, 2000), (3500, 5000)),
        "guard": (0x800, (2000, 2000), (7500, 5000)), "dervish": (0x400, (4000, 500), (3700, 500))}
    GIRL1, GIRL2, GUARD_A, GUARD_B, DERVISH, GATES = (216, 284), (260, 284), (140, 152), (184, 156), (416, 328), (152, 256)
    FOOT = ({5, 13, 21, 47, 55, 63}, {9, 17, 23, 51, 59}, {31, 69})          # frame sets of the guard's footsteps (the frames >= 55 never trigger, INFERRED dead)

    def __init__(self, spec, rng, glob=None, var=None):
        super().__init__(spec, rng, glob, var)
        self.v = {k: -1 for k in self.NPC}                              # running variant, -1 idle
        self.f = {k: 0 for k in self.NPC}
        self.stamp = {k: 0 for k in self.NPC}
        self.delay = {k: self.rand(s) + b for k, (_, (b, s), _) in self.NPC.items()}
        self.gate, self.gate_snd = 0, 0
        self.foot = None
        self.vox_stamp = self.bird_stamp = 0
        self.man_stamp = None                                           # Kman1: the stamp is 0 at construction -> fires on the first draw (CONFIRMED)
        self.bird_first = True
        for k, a in (("kaarg_voices", 2000), ("kaarg_birds", 2000)):
            if getattr(self.g, k) is None:
                setattr(self.g, k, self.rand(a) + 2000)

    def _n(self, name, v):
        b = self.spec.base
        key = {"girl1": b + "girl1/g%d" % (v + 1), "girl2": b + "girl2/g%d" % (v + 1), "guard": b + "guard/g", "dervish": b + "dervish/d"}[name]
        return self.count(key)

    def starters(self):
        n, g = self.now, self.g
        for name, (flag, _, (b, s)) in self.NPC.items():                                                       # the timers `0x4d26a4`
            if self.v[name] == -1 and n - self.stamp[name] > self.delay[name]:
                self.v[name] = self.rand(2) if name.startswith("girl") else 0
                self.f[name], self.stamp[name], self.delay[name] = 0, n, self.rand(s) + b
                self.flags |= flag
        if n - self.vox_stamp > g.kaarg_voices:
            self.sfx("kvox%d.wav" % (self.rand(3) + 2))
            g.kaarg_voices, self.vox_stamp = self.rand(2000) + 2000, n
        if self.bird_first or n - self.bird_stamp > g.kaarg_birds:                                             # stamp 0 at construction: the first bird fires on the first draw
            self.sfx("kbird%d.wav" % (self.rand(4) + 1))
            g.kaarg_birds, self.bird_stamp, self.bird_first = self.rand(2000) + 2000, n, False
        if self.man_stamp is None or n - self.man_stamp > 45000:
            self.sfx("kman1.wav")
            self.man_stamp = n

    def hover(self, region):
        self.region = region
        if region == -1:
            self.latch.clear()
        elif region == SHOP:
            if "shop" not in self.latch:
                self.latch.add("shop")
                self.sfx("kenter2.wav")
        elif region == INN:
            if "inn" not in self.latch:
                self.latch.add("inn")
                self.sfx("kenter1.wav")

    def tick(self):
        for name, (flag, _, _) in self.NPC.items():
            if self.v[name] != -1:
                self.f[name] += 1
                if self.f[name] >= self._n(name, self.v[name]):
                    self.v[name], self.f[name] = -1, 0
                    self.flags &= ~flag
        if self.region == LEAVE:                                                                               # the main gates (`0x4d2c2c`)
            if self.gate < 10:
                if self.gate_snd != 1:
                    self.gate_snd = 1
                    self.sfx("kdoor1.wav")
                self.gate += 1
        elif self.gate > 0:
            if self.gate_snd != 2:
                self.gate_snd = 2
                self.sfx("kdoor2.wav")
            self.gate -= 1

    def after_draw(self):
        f = self.f["guard"]
        if self.v["guard"] == -1:
            self.foot = None
            return
        if f == self.foot:
            return
        self.foot = f
        if f in self.FOOT[0]:
            self.sfx("ksteps21.wav" if self.rand(4) == 0 else "ksteps2.wav")
        elif f in self.FOOT[1]:
            self.sfx("ksteps11.wav" if self.rand(4) == 0 else "ksteps1.wav")        # the second set's variant roll is INFERRED like the first's
        elif f in self.FOOT[2]:
            self.sfx("ksteps31.wav" if self.rand(4) == 0 else "ksteps3.wav")

    def draw_ops(self):
        b = self.spec.base
        ops = [self.bmp(b + "townmain.bmp", 0, 0)]
        if self.region in self.spec.hover_patch:
            ops.append(self.bmp(*self.spec.hover_patch[self.region]))
        for name, pos in (("girl1", self.GIRL1), ("girl2", self.GIRL2)):
            v = max(self.v[name], 0)
            ops.append(self.bmp("%s%s/g%d%03d.bmp" % (b, name, v + 1, self.f[name] + v), *pos))          # variant 2 starts at file 1
        f = self.f["guard"] if self.v["guard"] != -1 else 0
        ops.append(self.bmp("%sguard/g%04d.bmp" % (b, f), *(self.GUARD_A if 13 <= f <= 37 else self.GUARD_B)))
        ops.append(self.bmp("%sdervish/d%04d.bmp" % (b, self.f["dervish"]), *self.DERVISH))
        ops.append(self.bmp("%smaingates/m%04d.bmp" % (b, self.gate), *self.GATES))
        return ops
