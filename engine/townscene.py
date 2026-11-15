"""The three town scenes (L6, docs/engine/town-scenes.md): hit mask, click table, hover and the animation state machines, as pure code.

No pygame, no shell import.  `engine/shell/town.py` is the screen over it.  Everything the scenes read from the install is read here at run time (`Mask.load`,
`SceneSpec.measure`: frame counts of the sprite sets / bitmap lists); nothing derived from the game files is stored in the repository.

`SceneState` = one open scene: `advance(dt_ms)` is one *draw* of the exe (the starters run every draw, the step - hover, the human random rolls, the tick - runs
once the wall clock passed 67 ms human / 100 ms druid and Kaarg since the last step, `> period` as the exe tests it), `hover(region)` is the mouse-move / step hover,
`press(region)` the left press, `draw_ops()` the layers in the exe's draw order, `take_sounds()` the sounds started since the last call.  Randomness is an
injected `random.Random` (`rand(n)` = `randrange(n)`, `FUN_004a0fd0`); the process-global counters and delays live in `Globals`.

Marks as in the spec: INFERRED parts are marked in the comments (the woman's step body, the druid / Kaarg timer stamps, the baba idle draw, the once-per-frame horse sound,
the initial guard-sound latch)."""

import re
from dataclasses import dataclass, field

import numpy as np

from engine.ui import story

W, H = 640, 480
SHOP, INN, LEAVE, MENU = 1, 2, 8, 0x10                 # region flags (the other flags are the NPC regions)
LEAVE_GATE, CHAPTER = 0x301, 0x300                      # Scenario variables

REGION_OF_BYTE = {0x80: 2, 0x90: 1, 0xa0: 8, 0xb0: 0x10, 0xc0: 4, 0x20: 0x400, 0x40: 0x800, 0x50: 0x1000, 0x60: 0x200}      # `0x4cd8b7`; every other byte -> -1
BYTE_OF_REGION = {v: k for k, v in REGION_OF_BYTE.items()}

TOWN_DIR = {1: "graphics/interface/town/", 2: "graphics/interface/town_kaarg/", 3: "graphics/interface/town_druid/"}
BIRDS_DIR = "graphics/interface/townbirds/"
SFX = {1: "sfx/town/", 2: "sfx/town_kaarg/", 3: "sfx/town_druid/"}
STOP = "stop"                                                                                       # the second element of a stop event (a play has the loop flag)
SHOP_ENTER, SCHOOL_POINT = "sfx/town/shop/enter.wav", "sfx/town/school/point.wav"          # human slots `+0x94`, `+0x98`
ENTRY_LOOP = {1: "sfx/town/crowd.wav", 2: "sfx/town_kaarg/kvox1.wav", 3: "sfx/town_druid/dforest1.wav"}        # looped, priority 0x80
RACE = {1: "human", 2: "kaarg", 3: "druid"}
STEP_MS = {1: 67, 2: 100, 3: 100}


class Globals:
    """The exe's process globals (they survive visits, town-scenes 6): the stars play counter `0x628260`, the first-bird delay `0x628254`, the druid birds / trees
    delays `0x628234 / 0x628244`, the Kaarg voices / birds delays `0x628224 / 0x628240`.  None = not rolled yet (the first value is rolled once per process)."""

    def __init__(self):
        self.stars = 0
        self.bird_delay = self.druid_birds = self.druid_trees = self.kaarg_voices = self.kaarg_birds = None
        # Kaarg object fields that live for the session (the loader `0x4d0d46` and the ctor `0x4d09ee` never touch them): the voice / bird / Kman1 stamps
        # `+0xb8 / +0x25c / +0x260` (None = never written: heap garbage / 0, in both cases `now - stamp > delay` at the first draw) on a clock that only counts
        # the time spent in the scene (INFERRED: the exe's `timeGetTime` also counts the time away), and "the step clock `0x628248` was stamped" (first draw ever).
        self.kaarg_clock, self.kaarg_stamps, self.kaarg_step_seen = 0, {"vox": None, "bird": None, "man": None}, False


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
    sound_ms: dict = field(default_factory=dict)           # game path of a scene sound -> its length in ms (`measure`; missing = 0: it never counts as still playing)

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
        from engine.audio.wavlen import wav_duration_ms
        for d in (SFX[self.town], SFX[self.town] + "shop/"):
            try:
                names = fs.listdir(d.rstrip("/"))
            except (KeyError, OSError, ValueError):
                continue
            for name in names:
                if name.lower().endswith(".wav"):
                    try:
                        self.sound_ms[(d + name).lower()] = wav_duration_ms(fs.read(d + name)) or 0
                    except (KeyError, OSError, ValueError):
                        pass
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

SPEECH = {1: {},                                         # the format strings at `0x5f7148`, `0x5f715c`, `0x5f752c`, `0x5f753c`, `0x5f754c`, `0x5f755c` (no underscore; `%d` = `Var(0x300)`)
          2: {4: "kaargwoman%d", 0x200: "kaargwoman%d", 0x400: "kaargman%d", 0x800: "kaargguard%d"},
          3: {0x200: "druidinnkeeper%d", 0x1000: "druidshopkeeper%d"}}
TOWN_TEXT = "main/text/town.txt"
SPEECH_DIR = "speech/town/"


def voice_letter(flags):
    """The hero-class letter of `FUN_004dc84c` (CONFIRMED): flags bit 4 = female, bit 2 = mage; male fighter `f`, male mage `m`, female fighter `a`, female mage `s`."""
    return ("s" if flags & 2 else "a") if flags & 4 else ("m" if flags & 2 else "f")


def town_voice(text, key, flags, part=1, exists=None):
    """The voice file of page `part` of the `town.txt` section `#<key>` (`FUN_004dc84c`, the `keeper` / `man` / `guard` branch, CONFIRMED): `speech/town/NNNNLCCCpPP.wav` with `N` = the page tag's
    `npc=` (4 digits), `L` = `t`, or the hero letter when the tag has an `iam*` condition or `npc == 21`, `C` = the digits at the end of the key zero-padded to 3 (`plagatguard`: `000`),
    `P` = the page (`part`).  None when the section has no such page or `exists(path)` says the file is missing (the exe plays only existing files)."""
    pg = story.page(story.section(text, key), part, flags)
    if pg is None:
        return None
    letter = voice_letter(flags) if pg.iam or pg.npc == 21 else "t"
    digits = re.search(r"\d*$", key).group()[:5].rjust(3, "0")
    path = "%s%04d%s%sp%02d.wav" % (SPEECH_DIR, pg.npc, letter, digits, part)
    return path if exists is None or exists(path) else None


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
        self.events = []                                # the sound events since the last take: (path, loop) = a play, (path, STOP) = a stop
        self.latch = set()                              # the entry-sound latches
        self.busy = {}                                  # sound path -> ms on our clock until which it still plays
        self.slot = {}                                  # the slots whose file changes at play time (gate `+0x78`, human guards `+0x7c`): name -> path of the loaded file
        self.heard = []                                 # every path started in this visit (order of first play): what the release-all has to cut
        if spec.entry_loop:
            self.heard.append(spec.entry_loop)
            self.events.append((spec.entry_loop, True))

    @staticmethod
    def build(spec, rng, glob=None, var=None):
        return {1: Human, 2: Kaarg, 3: Druid}[spec.town](spec, rng, glob, var)

    # -- helpers
    def rand(self, n):
        return self.rng.randrange(n)

    def play(self, path, loop=False, restart=False):
        """The exe's slot play `0x438570` (CONFIRMED): a sound whose buffer still plays is not started again (`FUN_0045a964` finds the playing channel); `restart` = the `stop` (`0x4385b0`)
        that precedes the play of the same slot (the figures' Ddruid1 / Ddruid2).  The length comes from `spec.sound_ms` (unknown = 0)."""
        if restart:
            self.stop(path)
        if not loop:
            if self.busy.get(path, 0) > self.now:
                return
            self.busy[path] = self.now + self.spec.sound_ms.get(path, 0)
        self._heard(path)
        self.events.append((path, loop))

    def sfx(self, name, restart=False):
        self.play(SFX[self.spec.town] + name, restart=restart)

    def stop(self, path):
        """The exe's slot stop `0x4385b0` (CONFIRMED): the sound of the slot is cut when its buffer plays (the backend knows; an ended or empty slot does nothing there)."""
        self.busy.pop(path, None)
        self.events.append((path, STOP))

    def stop_sfx(self, name):
        self.stop(SFX[self.spec.town] + name)

    def reload(self, slot, name):
        """`FUN_004384f0` + `0x438570` on a slot whose file is chosen at play time (CONFIRMED `0x4cd0ea` gate, `0x4cce81` guards, `0x4d2c2c` Kaarg gate): the reload first releases
        the old buffer (`FUN_00438480` = stop + free), so the other file of the slot is cut, and the new buffer always plays."""
        if self.slot.get(slot):
            self.stop(self.slot[slot])
        path = self.slot[slot] = SFX[self.spec.town] + name
        self.busy[path] = self.now + self.spec.sound_ms.get(path, 0)
        self._heard(path)
        self.events.append((path, False))

    def release(self, slot):
        """`FUN_00438480` on the slot (CONFIRMED `0x4cce81`): stop + free; an empty slot does nothing."""
        if self.slot.get(slot):
            self.stop(self.slot.pop(slot))

    def _heard(self, path):
        if path not in self.heard:
            self.heard.append(path)

    def release_all(self):
        """The scene's close (CONFIRMED `0x4caaed`, vtable `+0x84`, reached by the click's `0x445`): vtable `+0x8c` = the release-all (`0x4ce00b` / `0x4cf4dc` / `0x4d1e36`)
        stops and frees **every** sound slot, the looped entry sound included.  Yields one stop per path started since the load (a slot never played is empty in the exe, an
        ended one is a no-op in the backend); the model forgets them (the next load starts afresh)."""
        for path in self.heard:
            self.stop(path)
        self.heard = []
        self.slot.clear()
        self.busy.clear()

    def take_events(self):
        out, self.events = self.events, []
        return out

    def take_sounds(self):
        """The plays of `take_events` (a stop is not a sound)."""
        return [(p, k) for p, k in self.take_events() if k is not STOP]

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
        self.guard_snd = 0                                              # `+0xf0` = 0 at the load (CONFIRMED `0x4ca7e2`): the first step (dir +1) plays Guard2
        self.dervish = 0
        self.horse = self.baba = -1                                     # frame counters, -1 = idle
        self.horse_set = self.baba_set = 0
        self.horse_base = self.baba_base = 0
        self.baba_delay = self.rand(2000) + 2000                        # first deadlines after the load (`0x4ca7e2`, CONFIRMED order: baba `+0x118/+0x11c`, then horse `+0x148/+0x14c`)
        self.horse_delay = self.rand(2000) + 2000
        self.bird_base = 0
        self.bird_group = self.bird_count = 0
        self.bird_f = [0, 0, 0]
        if self.g.bird_delay is None:
            self.g.bird_delay = self.rand(2000) + 1000

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
                self.stop(SCHOOL_POINT)                                                                # `0x4cdbea`: stop `+0x98` (School\Point), play `+0x94`
                self.play(SHOP_ENTER)
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
    def _run(self, counter, n, flag, sound=None, stops=()):
        """One step of a counted animation: at counter 0 the `stops` (the tavern cuts the shop-enter and School/Point sounds, `0x4ccfbf`) and the sound, then ++, at `n` -> 0 and the flag clears."""
        if counter == 0:
            for path in stops:
                self.stop(path)
            if sound:
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
            self.tav = self._run(self.tav, self.count(BIRDS_DIR + "tavern/sprites.16a"), 2, "point.wav", (SHOP_ENTER, SCHOOL_POINT))
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
                    self.reload("gate", "gateup.wav")
                self.gate -= 1
        elif self.gate < 8:
            if self.gate_snd != 2:
                self.gate_snd = 2
                self.reload("gate", "gatedn.wav")
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
        """`0x4cce81` (CONFIRMED, REA): frame += dir; Guard2 when dir is +1 and the latch is 0, Guard1 when dir is -1 and the latch is set; clamp at 0 and n-1 (dir reset) and free the slot (`FUN_00438480`: stops the guard sound)."""
        n = self.count(BIRDS_DIR + "guards/sprites.16a")
        self.guard_f += self.guard_dir
        if self.guard_dir == 1 and self.guard_snd == 0:
            self.reload("guard", "guard2.wav")
            self.guard_snd = 1
        elif self.guard_dir == -1 and self.guard_snd != 0:
            self.reload("guard", "guard1.wav")
            self.guard_snd = 0
        if self.guard_f < 0:
            self.guard_dir = self.guard_f = 0
            self.release("guard")                                                                      # the clamp frees the slot: the guard sound is cut (also one started in this very step)
        elif self.guard_f >= n:
            self.guard_dir = 0
            self.guard_f = n - 1
            self.release("guard")

    def after_draw(self):
        """The parts of the exe's draw that are not the step: the bird flyers end and stamp (`0x4caf00`), the horse sounds (INFERRED: once per frame, the exe fires
        on every draw the frame matches)."""
        if self.flags & 0x80:
            n = self.count("%sbirds%d/sprites.16a" % (BIRDS_DIR, self.bird_group * 3 + 1))
            if all(self.bird_f[k] >= n for k in range(self.bird_count)):
                self.flags &= ~0x80
            self.bird_base = self.now
        if self.horse >= 0:                                                                            # `0x4cb05d`: every draw while the frame matches; `play` skips a slot still playing
            k, f = self.horse_set, self.horse
            if f == 14 and k in (0, 1, 2) or (k == 1 and f == 8):
                self.sfx("horse2.wav")
            elif k == 2 and f == 1:
                self.sfx("horse1.wav")

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
        ops.append(self.spr(self.baba_path(), max(self.baba, 0), *self.BABA_POS[self.baba_kind]))     # idle (-1) = frame 0, like the horse (CONFIRMED `0x4cb05d`)
        if self.dervish >= 0:
            ops.append(self.spr(self.dervish_path(), self.dervish, *self.DERVISH_POS[self.dervish_kind]))
        return ops


class Druid(SceneState):
    """Town 3 (`0x4ce2b9`).  Flags: 1 shop figure (graphics `woman`), 2 inn figure (graphics `man`), 0x80 bug, 0x100 lizard.  CONFIRMED (`0x4ce914`, `0x4cf65a`, `0x4cfd58`,
    `0x4d00de`): the figure on the **shop** side (state `+0x2ec`, frame `+0x1e0`, region 1, hili_shop, Ddruid1) is loaded from `woman\\a%d%04d.bmp` (list `+0x2b0`), the figure on the
    **inn** side (state `+0x2a4`, frame `+0x168`, region 2, hili_tavern, Ddruid2) from `man\\...` (list `+0x268`)."""
    SHOP_POS = {0: (0x150, 0xf4), 1: (0x150, 0xf4), 2: (0x154, 0xe0)}          # `0x150 + (v / 2) * 4`, `0xf4 - (v / 2) * 0x14`
    INN_POS = {0: (0xa4, 0xc8), 1: (0xa4, 0xc8), 2: (0x98, 0xb8)}              # `0xa4 - (v / 2) * 0xc`, `0xc8 - (v / 2) * 0x10`
    GRAPHICS = {SHOP: "woman", INN: "man"}
    SOUND = {SHOP: "ddruid1.wav", INN: "ddruid2.wav"}
    FLAG = {SHOP: 1, INN: 2}
    BUG_POS, LIZARD_POS = (0, 0xd4), (0, 0x12c)
    LIZARD = (                                                                                       # `0x5f68c8`, animation 4.11, frames 1-based, -1 ends
        (39, 40, 41, 42, 41, 40, 39, 38),
        tuple(range(28, 39)),
        (2, 3, 4, 5, 6, 7) + (8,) * 13 + (22, 23, 24, 25, 26, 27),
        (2, 3, 4, 5, 6, 7) + (8,) * 13 + tuple(range(9, 19)) + (19,) * 10 + tuple(range(20, 28)))

    def __init__(self, spec, rng, glob=None, var=None):
        super().__init__(spec, rng, glob, var)
        # the load `0x4ce641` (CONFIRMED): rolls in this order, every stamp = the load time (0 on our clock), states -1, flags 0, latches 0
        self.v = {SHOP: -1, INN: -1}                                    # the variant of the running figure animation (`+0x2ec` / `+0x2a4`), -1 idle
        self.f = {SHOP: -1, INN: -1}                                    # its frame (`+0x1e0` / `+0x168`, the loader sets -1)
        self.stamp = {SHOP: 0, INN: 0}                                  # `+0x2f0` / `+0x2a8`
        self.delay = {SHOP: self.rand(2000) + 2000, INN: self.rand(2000) + 2000}
        self.bug_stamp, self.bug_delay = 0, self.rand(5000) + 7000      # `+0x304 / +0x308` (the later delays are `rand(10000) + 10000`)
        self.bug_v, self.bug_f = -1, -1                                 # `+0x30c`, `+0x310`
        self.liz_seq, self.liz_i = -1, -1                               # `+0x318`, `+0x31c`
        self.bird_stamp = self.tree_stamp = self.wolf_stamp = 0         # `+0xb8`, `+0x2f8`, `+0x2fc`, all stamped at the load

    def _frames(self, who, v):
        return self.count("%s%s/a%d" % (self.spec.base, self.GRAPHICS[who], v + 1))

    def _path(self, who, v, f):
        return "%s%s/a%d%04d.bmp" % (self.spec.base, self.GRAPHICS[who], v + 1, f + 1)

    def starters(self):
        n, g = self.now, self.g
        if g.druid_birds is None:                                                                               # `0x4d00de`: the process-global first delays, once
            g.druid_birds = self.rand(2000) + 2000
        if g.druid_trees is None:
            g.druid_trees = self.rand(2000) + 2000
        for who in (SHOP, INN):                                                                                 # the figures: the timer is re-armed whether or not it starts
            if n - self.stamp[who] > self.delay[who]:
                self.delay[who] = self.rand(5000) + 3500
                self.stamp[who] = n
                if self.v[who] == -1:
                    self.f[who] = 0
                    self.v[who] = 2 if self.region == who else self.rand(2)
                    self.flags |= self.FLAG[who]
                    self.sfx(self.SOUND[who], True)                                                             # stop + play of the same slot
        if n - self.bird_stamp > g.druid_birds:
            self.sfx("dbird%d.wav" % (self.rand(3) + 1))
            g.druid_birds, self.bird_stamp = self.rand(2000) + 2000, n
        if n - self.tree_stamp > g.druid_trees:
            self.sfx("dtree%d.wav" % (self.rand(4) + 1))
            g.druid_trees, self.tree_stamp = self.rand(2000) + 2000, n
        if n - self.wolf_stamp > 60000:
            self.sfx("dwolf1.wav")
            self.wolf_stamp = n
        if n - self.bug_stamp > self.bug_delay:                                                                 # no idle test: the delay (>= 10 s) outlasts the run (6.1 s)
            self.bug_v = self.rand(3)
            self.sfx("dbug%d.wav" % (self.bug_v + 1))
            self.flags |= 0x80
            self.bug_delay, self.bug_stamp = self.rand(10000) + 10000, n
        if self.liz_seq == -1:                                                                                  # restarts at once whenever idle
            r = self.rand(15)
            self.liz_seq = r + 1 if r < 3 else 0
            self.sfx("dlizard%d.wav" % (self.liz_seq + 1))
            self.flags |= 0x100
            self.liz_i = 0

    def hover(self, region):
        """`0x4cfd58`.  The entry-sound latches (`+0xac` shop, `+0x260` inn, `+0x264` out): entering a region plays its sound once and clears the other two; regions 4 / `0x200` /
        `0x1000` return at once (the region is stored, latches kept); every other region value clears all three."""
        prev, self.region = self.region, region
        if region in (SHOP, INN):
            if prev != region and self.v[region] != 2:                                                          # entering: variant 2, the timer re-stamped, one step now
                self.stamp[region] = self.now
                self.v[region], self.f[region] = 2, -1
                self.flags |= self.FLAG[region]
                self._step(region)
                self.sfx(self.SOUND[region], True)
            name = "shop" if region == SHOP else "inn"
            if name not in self.latch:                                                                          # stop the other two enter sounds, play this one
                for other in (("denter1.wav", "dout.wav") if region == SHOP else ("denter2.wav", "dout.wav")):
                    self.stop_sfx(other)
                self.sfx("denter2.wav" if region == SHOP else "denter1.wav")
            self.latch = {name}
        elif region == LEAVE:
            if "out" not in self.latch:
                self.stop_sfx("denter2.wav")
                self.stop_sfx("denter1.wav")
                self.sfx("dout.wav")
            self.latch = {"out"}
        elif region in (4, 0x200, 0x1000):
            return
        else:                                                                                                   # -1 and the other flags
            if region != -1:
                self.flags |= region
            self.latch.clear()

    def _step(self, who):
        """`0x4cfbf6` (shop) / `0x4cfb45` (inn, CONFIRMED: the same body; its frame-0 sound calls `+0x94 / +0x90` hit slots the druid never loads = no-ops)."""
        if self.v[who] > -1:
            self.f[who] += 1
            if self.f[who] == self._frames(who, self.v[who]):
                self.f[who], self.v[who] = 0, -1
                self.flags &= ~self.FLAG[who]

    def tick(self):                                                                                             # `0x4d065b`
        if self.flags & 1:
            self._step(SHOP)
        if self.flags & 2:
            self._step(INN)
        if self.flags & 0x80 and self.bug_v > -1:                                                               # `0x4cfc77`
            self.bug_f += 1
            if self.bug_f == 61:
                self.bug_f, self.bug_v = 0, -1
                self.flags &= ~0x80
        if self.flags & 0x100 and self.liz_seq > -1:                                                            # `0x4cfcde`
            self.liz_i += 1
            if self.liz_i >= len(self.LIZARD[self.liz_seq]):                                                    # the -1 end marker
                self.liz_i, self.liz_seq = -1, -1
                self.flags &= ~0x100

    def _figure(self, who, pos):
        """The patch (only for the hover or variant 2) and the figure; idle = frame 0 of variant 2 at the hovered place when the pointer is on the region, else of variant 0."""
        ops = []
        if self.region == who or self.v[who] == 2:
            ops.append(self.bmp(*self.spec.hover_patch[who]))
        if self.v[who] < 0:
            v, f = (2 if self.region == who else 0), 0
        else:
            v, f = self.v[who], self.f[who]
        ops.append(self.bmp(self._path(who, v, max(f, 0)), *pos[v]))
        return ops

    def draw_ops(self):
        b = self.spec.base
        ops = [self.bmp(b + "townmain.bmp", 0, 0)]
        ops += self._figure(SHOP, self.SHOP_POS)
        ops += self._figure(INN, self.INN_POS)
        if self.liz_seq < 0 or self.liz_i < 0:                                                                  # idle: frame 0
            ops.append(self.spr(b + "lizard/sprites.16a", 0, *self.LIZARD_POS))
        else:
            ops.append(self.spr(b + "lizard/sprites.16a", self.LIZARD[self.liz_seq][min(self.liz_i, len(self.LIZARD[self.liz_seq]) - 1)] - 1, *self.LIZARD_POS))
        if self.bug_v >= 0 and self.bug_f >= 0:
            ops.append(self.spr(b + "bug/sprites.16a", self.bug_v * 61 + self.bug_f, *self.BUG_POS))
        return ops


class Kaarg(SceneState):
    """Town 2 (`0x4d09ee`).  The NPCs run only from timers: flags 0x200 girl 1, 4 girl 2, 0x800 guard, 0x400 dervish."""
    NPC = {   # name: (flag, first delay (base, spread), later delay (base, spread), count key)
        "girl1": (0x200, (2000, 2000), (3500, 5000)), "girl2": (4, (2000, 2000), (3500, 5000)),
        "guard": (0x800, (2000, 2000), (7500, 5000)), "dervish": (0x400, (4000, 500), (3700, 500))}
    GIRL1, GIRL2, GUARD_A, GUARD_B, DERVISH, GATES = (216, 284), (260, 284), (140, 152), (184, 156), (416, 328), (152, 256)
    FOOT = ({5, 13, 21, 47}, {9, 17, 23, 51}, {31})          # frame sets of the guard's footsteps (`0x4d26a4`: the exe's table also lists 55, 59, 63, 69, never seen: the counter wraps at 55 in the step, before the starters)

    def __init__(self, spec, rng, glob=None, var=None):
        super().__init__(spec, rng, glob, var)
        self.v = {k: -1 for k in self.NPC}                              # running variant, -1 idle
        self.f = {k: 0 for k in self.NPC}
        self.stamp = {k: 0 for k in self.NPC}
        self.delay = {k: self.rand(s) + b for k, (_, (b, s), _) in self.NPC.items()}
        self.gate, self.gate_snd = 0, 0
        self.foot_latch = 0                                             # `+0x258`
        if self.g.kaarg_step_seen:                                      # the step clock `0x628248` survives visits: after the first opening the first draw runs a step (INFERRED: the player was away > 100 ms)
            self.last_step = -1000
        self.g.kaarg_step_seen = True
        for k, a in (("kaarg_voices", 2000), ("kaarg_birds", 2000)):
            if getattr(self.g, k) is None:
                setattr(self.g, k, self.rand(a) + 2000)

    def _n(self, name, v):
        b = self.spec.base
        key = {"girl1": b + "girl1/g%d" % (v + 1), "girl2": b + "girl2/g%d" % (v + 1), "guard": b + "guard/g", "dervish": b + "dervish/d"}[name]
        return self.count(key)

    def advance(self, dt_ms):
        self.g.kaarg_clock += dt_ms
        super().advance(dt_ms)

    def starters(self):
        n, g, c, st = self.now, self.g, self.g.kaarg_clock, self.g.kaarg_stamps
        for name, (flag, _, (b, s)) in self.NPC.items():                                                       # the timers `0x4d26a4` (no idle test: a due timer restarts a running animation)
            if n - self.stamp[name] > self.delay[name]:
                self.v[name] = self.rand(2) if name.startswith("girl") else 0
                self.f[name], self.stamp[name], self.delay[name] = 0, n, self.rand(s) + b
                self.flags |= flag
        if st["vox"] is None or c - st["vox"] > g.kaarg_voices:                                                # stamps never written before the first fire: voice, bird and Kman1 all fire on the very first draw
            self.sfx("kvox%d.wav" % (self.rand(3) + 2))
            g.kaarg_voices, st["vox"] = self.rand(2000) + 2000, c
        if st["bird"] is None or c - st["bird"] > g.kaarg_birds:
            self.sfx("kbird%d.wav" % (self.rand(4) + 1))
            g.kaarg_birds, st["bird"] = self.rand(2000) + 2000, c
        if st["man"] is None or c - st["man"] > 45000:
            self.sfx("kman1.wav")
            st["man"] = c

    def hover(self, region):
        """`0x4d244e` (CONFIRMED): the latches `+0xac` shop, `+0x250` inn, `+0x254` out; entering shop / inn plays its Kenter once and clears the other two; the gate region clears
        shop / inn and latches out (stopping both enter sounds); 4 / `0x200` / `0x400` / `0x800` return at once; any other region ORs its flag and clears all three."""
        self.region = region
        if region in (SHOP, INN):
            name = "shop" if region == SHOP else "inn"
            if name not in self.latch:                                                                          # stop the other enter sound, play this one
                self.stop_sfx("kenter1.wav" if region == SHOP else "kenter2.wav")
                self.sfx("kenter2.wav" if region == SHOP else "kenter1.wav")
            self.latch = {name}
        elif region == LEAVE:
            if "out" not in self.latch:                                                                         # latches out and stops both enter sounds
                self.stop_sfx("kenter2.wav")
                self.stop_sfx("kenter1.wav")
            self.latch = {"out"}
        elif region in (4, 0x200, 0x400, 0x800):
            return
        else:
            if region != -1:
                self.flags |= region
            self.latch.clear()

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
                    self.reload("gate", "kdoor1.wav")
                self.gate += 1
        elif self.gate > 0:
            if self.gate_snd != 2:
                self.gate_snd = 2
                self.reload("gate", "kdoor2.wav")
            self.gate -= 1

    def after_draw(self):
        """The footstep switch of the starters (`0x4d26a4`, CONFIRMED): only while the guard flag is set; a frame in a set plays once when the latch `+0x258` is clear and sets it;
        any other frame clears it (so a frame that stays across draws fires once; the latch is untouched while the guard is idle).  All three sets roll `rand(4) == 0` for the variant."""
        if self.v["guard"] == -1:
            return
        f = self.f["guard"]
        for k, (plain, alt) in enumerate((("ksteps2", "ksteps21"), ("ksteps1", "ksteps11"), ("ksteps3", "ksteps31"))):
            if f in self.FOOT[k]:
                if not self.foot_latch:
                    self.sfx((alt if self.rand(4) == 0 else plain) + ".wav")
                    self.foot_latch = 1
                return
        self.foot_latch = 0

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
