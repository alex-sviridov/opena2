"""The Inn window's pure model (L7, docs/engine/town-inn.md, town-hero.md): the person strip, the four handlers behind the buttons, the hero arrows, the ambient
sound scheduler and the dialogue (story) window's page sequence.  No drawing, no pygame, no shell import: `engine/shell/inn.py` is the screen over it.

`InnState` = one opening of the window (`FUN_0048b885` runs `EnterInn` at every opening; the units for the words are made there: the story heroes among them join the
roster, as `CampaignGame.visit_towns` does).  The player's clicks are methods; each returns the effects it had (`Effect`s in the exe's order: text key, `TalkTo`, sound),
which the screen turns into the dialogue window, sounds and redraws.  `CampaignGame.visit_towns` stays as the headless oracle: a scripted click sequence through this
class gives the same `TalkTo` words and roster (`tests/test_engine_inn.py`).

Marks as in the spec: everything stated as CONFIRMED has its routine in the docs; INFERRED parts are marked in the comments."""

import re
from dataclasses import dataclass, field

from engine.sim import campaign as C
from engine.ui import story

# -- geometry (window-relative, O = (fx, fy); town-inn 3b, town-hero 2 / 3) ---------------------------------------------------------------------
PANELS = {"left": (0, 0, 160, 480), "buttons": (480, 0, 160, 238), "centre": (160, 0, 320, 480)}        # ids 0x44d / 0x44e / 0x450 (`0x49a65e`)
INFO_PANEL = (480, 238, 160, 242)                                          # the unit info panel, window 7, shifted by OffsetRect(640 - 160, 0)
BUTTONS = ((484, 44, 140, 46), (484, 91, 140, 46), (484, 138, 140, 46))     # Hire / Fire, Talk, Exit (`0x496172`, window coordinates)
ARROWS = ((481, 443, 32, 32), (599, 443, 32, 32))                          # ar1 / ar2 at (1, 0xcd) / (0x77, 0xcd) of the info panel
CELL_W, CELL_H, COLUMNS = 48, 64, 6                                         # figure cells (`0x497840`): 3 rows x 6 columns, row 0 at the bottom
LEFT_BITMAPS = (("graphics/interface/inn/leftstats.bmp", 0, 0), ("graphics/interface/inn/leftpicture.bmp", 0, 238))     # `0x495e81`: INFERRED which is which
MODE_BUTTON = (608, 238, 32, 36)                                            # the mode button's hit rect (0x80, 0)-(160, 36) of the info panel (`0x4aebc8`)
PORTRAIT_AT = (11, 240)
CENTRE_AT = (160, 0)
# the centre panel's edge strips (CONFIRMED `0x4983b9`, the common tail of `0x497adf`; each a keyed blit of the whole 16 px wide bitmap): LUOver (160, 0) 16x238, LDOver (160, 238) 16x242,
# RUOver (464, 0) 16x238, then HumanBackL (picture mode) / TextBackL (text mode) at (464, 238) 16x242 = the info panel's left strip
EDGE_STRIPS = (("graphics/interface/inn/luover.bmp", 160, 0), ("graphics/interface/inn/ldover.bmp", 160, 238), ("graphics/interface/inn/ruover.bmp", 464, 0),
               ("graphics/interface/HumanBackL.bmp", 464, 238))

# the caption lines of main.txt
MAIN_HIRE, MAIN_FIRE, MAIN_TALK, MAIN_EXIT, MAIN_HIRED = 0x102, 0x103, 0xF2, 0xE8, 0x101
MAIN_NO_UNITS, MAIN_SELECTED = 0x2F, 0x30
CAPTION_FONT = 0xA

# the word fields (town-inn 1)
TAKEN = 0x80000000
T_OFFER, T_REFUSE = 1, 2

# sounds: the slot -> the file under `sfx/` per town class (town-inn 3; lower case as the shell names its files)
SLOTS = {"add": "sfx/add.wav", "noadd": "sfx/noadd.wav", "talk": "sfx/talk.wav", "out": "sfx/out.wav", "nofit": "sfx/town/shop/nofit.wav", "helper": "sfx/town/inn/helper.wav"}
ENTER = {1: "sfx/town/inn/enter.wav", 2: "sfx/town_kaarg/inn/kin1.wav", 3: "sfx/town_druid/inn/din1.wav"}        # `+0xa4` (Kin1 is missing in the install: silent)
HUMAN_SLOTS = {"drink": "sfx/town/inn/drink.wav", "glotok": "sfx/town/inn/glotok.wav", "steam": "sfx/town/inn/steam.wav", "water": "sfx/town/inn/water.wav",
               "chair": "sfx/town/inn/chair.wav", "breath": "sfx/town/shop/breath.wav"}
DRUID_DROPS = tuple("sfx/town_druid/inn/dwater%d.wav" % k for k in range(1, 5))                    # `+0x140..+0x14c`
DRUID_EVENTS = {1: "sfx/town_druid/inn/ddruid4.wav", 2: "sfx/town_druid/inn/ddruid3.wav"}          # `+0x154`, `+0x150`: the sound at the start of event 1 / 2 (`0x49d1a9`, `0x49d1c7`)
DRUID_FRAME30 = "sfx/town_druid/inn/ddruid41.wav"                                                   # `+0x158`: event 1 at its object frame 30 (`0x49d23d`)
DRUID_VOICES = {1: "sfx/town_druid/inn/dbird4.wav", 2: "sfx/town_druid/inn/dbird41.wav", 3: "sfx/town_druid/inn/dbird42.wav"}   # `+0x160 / +0x164 / +0x168` (`0x49d9c7`-`0x49da33`)
DRUID_LOOP = "sfx/town_druid/inn/dforest2.wav"                                                      # `+0x15c`: `FUN_004a0ff0` at the end of the load (`0x49caaa`)
KAARG_DROPS = tuple("sfx/town_kaarg/inn/kdish%d.wav" % k for k in range(1, 5))                     # `+0x140..+0x14c`
KAARG_EVENTS = {1: "sfx/town_kaarg/inn/kman3.wav", 2: "sfx/town_kaarg/inn/kman2.wav"}              # `+0x154`, `+0x150` (`0x49f627`, `0x49f645`)
KAARG_VOICES = {1: "sfx/town_kaarg/inn/kvox6.wav", 2: "sfx/town_kaarg/inn/kvox7.wav", 3: "sfx/town_kaarg/inn/kvox8.wav"}      # `+0x15c / +0x160 / +0x164` (`0x49fec6`-`0x49ff32`)
KAARG_LOOP = "sfx/town_kaarg/inn/kvox5.wav"                                                         # `+0x158`: the load's `FUN_004a0ff0` (`0x49ec74`)

SOUND_OF = {"accept": "add", "reject": "add", "dismiss": "noadd", "talk": "talk", "about": "talk"}


def cell_rect(i):
    """Window-relative rect (x, y, w, h) of figure cell `i` (person order: mercenaries, then the NPCs): row `i / 6` from the bottom, column `i % 6`
    (CONFIRMED `0x497840`, `0x497f42`: `row = i / 6`, `col = i % 6`; the base `(panel.left + 16, panel.bottom)` INFERRED as in town-hero 3)."""
    row, col = divmod(i, COLUMNS)
    return 176 + CELL_W * col, 480 - CELL_H * (row + 1), CELL_W, CELL_H


def cell_at(x, y, count):
    """The person index under the window-relative point, None outside every cell of `count` persons (`0x499367`)."""
    for i in range(count):
        cx, cy, w, h = cell_rect(i)
        if cx <= x < cx + w and cy <= y < cy + h:
            return i
    return None


def rect_has(r, x, y):
    return r[0] <= x < r[0] + r[2] and r[1] <= y < r[1] + r[3]


def button_at(x, y):
    """`0x497123`: the first of the three rects holding the point, else None."""
    for i, r in enumerate(BUTTONS):
        if rect_has(r, x, y):
            return i
    return None


# -- the person strip -------------------------------------------------------------------------------------------------------------------------

@dataclass
class Person:
    """One person of the strip.  `a` = the word's low 16 bits (the unit's `+0x1dc`); `unit_type` = the units.reg type id (`unit+0x24`, the sprite folder `inn\\Unit<n>`);
    `hero` / `mage` = the client flags `+0x1b8 & 1` / `& 2` (the story heroes use `HeroFighter` / `HeroMage`); `template` = the data.bin `UnitType` (None without an install)."""
    kind: str                       # "merc" | "npc"
    a: int
    unit_type: int = 0
    hero: bool = False
    mage: bool = False
    template: object = None

    @property
    def sprite(self):
        """`FUN_00499783`: `graphics\\interface\\inn\\HeroMage|HeroFighter\\sprites.16a` for a hero, else `Unit<unit_type>`."""
        if self.hero:
            return "graphics/interface/inn/%s/sprites.16a" % ("heromage" if self.mage else "herofighter")
        return "graphics/interface/inn/unit%d/sprites.16a" % self.unit_type


def word_type(word):
    return (word >> 28) & 7


def word_a(word):
    return word & 0xFFFF


def word_b(word):
    return (word >> 16) & 0xFFF


def word_index(words, a):
    """`FUN_0049ab92`: the index of the first word whose low 16 bits equal `a` (the unit's `+0x1dc`), -1 when none."""
    for i, w in enumerate(words):
        if word_a(w) == a:
            return i
    return -1


def person_of(a, kind, types, chapter):
    """The person for word number `a`: a mercenary (`mercenary_template`: the chapter variant) or an NPC (the data.bin record of server id `a`; the story heroes 0x15..0x1e are
    created by the by-name constructor with the hero flag: `HeroMage` when the template has mana).  Without `types` (no install) the numbers stay 0."""
    from engine.campaign import mercenary_template
    tpl, hero, mage = None, False, False
    if types is not None:
        if kind == "merc":
            t = mercenary_template(types, a, chapter)
            tpl = None if t is None else types.lookup(t[1], t[0])
        elif a in C.STORY_HEROES:
            tpl = next((t for t in types if t.kind == "human" and t.server_id > 10000 and (t.server_id // 10) % 1000 == a), None)
            hero, mage = True, bool(tpl is not None and tpl.fields.get("mana_max", -1) > 0)
        else:
            tpl = types.lookup(True, a) or types.lookup(False, a)
    return Person(kind, a, tpl.unit_type if tpl is not None else 0, hero, mage, tpl)


@dataclass(frozen=True)
class Effect:
    """What a handler did, in order: `("text", key)` (the dialogue window opens on the `town.txt` section `#<key>`), `("talk_to", word)`, `("sound", slot)`."""
    kind: str
    value: object


class InnState:
    """The window after its load (`0x49abfe` ...): the words (`+0xfc`), the mercenary list (`+0xc0`, words of type 1 / 2), the NPC list (`+0xe8`, the others), the selected
    person `+0xb8` (0 when the lists are not empty, else -1), the hero list and its index (`+0xbc`)."""

    def __init__(self, game, town, types="auto"):
        self.game, self.town = game, town
        camp = self.camp = game.camp
        self.chapter = camp.get(C.CHAPTER)
        self.words = list(camp.enter_inn_words(town, game.is_mage, game.is_female))
        for w in self.words:                                       # `FUN_004f312a`: the story heroes among the words join the party (the stand-in of visit_towns)
            if word_type(w) in (0, 3) and word_a(w) in C.STORY_HEROES:
                game.recruit(word_a(w))
        if types == "auto":
            types = game.assets.unit_stats() if game.install is not None or game._assets is not None else None
        self.persons = [person_of(word_a(w), "merc", types, self.chapter) for w in self.words if word_type(w) in (T_OFFER, T_REFUSE)]
        self.mercs = len(self.persons)
        self.persons += [person_of(word_a(w), "npc", types, self.chapter) for w in self.words if word_type(w) not in (T_OFFER, T_REFUSE)]
        self.sel = 0 if self.persons else -1
        self.heroes = [e.number for e in game.roster if e.human and e.number in C.STORY_HEROES]       # the living heroes in creation order (town-hero 5)
        self.hero = 0                                              # `FUN_004725f0`: the first entry with `+0x1b8 & 0x20` = the main hero (word 0x15)
        self.log = []                                              # every Effect, in order (the test surface)

    # -- the strip ---------------------------------------------------------------------------------------------------------------------
    @property
    def count(self):
        return len(self.persons)

    def person(self, i=None):
        i = self.sel if i is None else i
        return self.persons[i] if 0 <= i < len(self.persons) else None

    def word_of(self, i=None):
        """`(index, word)` of person `i`'s word through `FUN_0049ab92` (the first word with the person's number), None for nobody."""
        p = self.person(i)
        if p is None:
            return None
        k = word_index(self.words, p.a)
        return (k, self.words[k]) if k >= 0 else None

    def taken(self, i):
        """Bit 31 of person `i`'s word: the "HIRED" label and the Fire caption."""
        w = self.word_of(i)
        return bool(w is not None and w[1] & TAKEN and self.person(i).kind == "merc")

    def caption(self, button):
        """The caption line id of a button (`0x497223`): Hire / Fire (empty when nobody or a non-mercenary is selected), Talk, Exit."""
        if button == 0:
            p = self.person()
            if p is None or p.kind != "merc":
                return None
            return MAIN_FIRE if self.taken(self.sel) else MAIN_HIRE
        return MAIN_TALK if button == 1 else MAIN_EXIT

    def select(self, i):
        """The press on a figure (`0x4946b6`): `+0xb8 := i`."""
        if 0 <= i < self.count:
            self.sel = i

    # -- the four handlers (town-inn 1, CONFIRMED) -----------------------------------------------------------------------------------------
    def _do(self, *effects):
        self.log += effects
        for e in effects:
            if e.kind == "talk_to":
                self.camp.talk_to(e.value)
        return list(effects)

    def accept(self):
        """`0x49b812` (button 0 with bit 31 clear): the key `npc<A>accept<C>` for a type-1 offer, `npc<A>reject<C>` for anything else (C = `Var(0x300)`), the word gets bit 31
        and `TalkTo` follows (type 1 only), then the Add sound for **both** branches."""
        k, word = self.word_of()
        a = word_a(word)
        if word & 0x70000000 == 0x10000000:
            self.words[k] = word | TAKEN
            return self._do(Effect("text", "npc%daccept%d" % (a, self.chapter)), Effect("talk_to", self.words[k]), Effect("sound", "add"))
        return self._do(Effect("text", "npc%dreject%d" % (a, self.chapter)), Effect("sound", "add"))

    def dismiss(self):
        """`0x49b989` (button 0 with bit 31 set): no text, bit 31 cleared, `TalkTo(word)` with it clear, the NoAdd sound."""
        k, word = self.word_of()
        self.words[k] = word & ~TAKEN & 0xFFFFFFFF
        return self._do(Effect("talk_to", self.words[k]), Effect("sound", "noadd"))

    def talk(self):
        """`0x49ba28` (an NPC): the key `npc<A>talk<B>` (B = the word's own), `TalkTo(word)` unmodified, the Talk sound."""
        k, word = self.word_of()
        return self._do(Effect("text", "npc%dtalk%d" % (word_a(word), word_b(word))), Effect("talk_to", word), Effect("sound", "talk"))

    def about(self):
        """The inline About of `0x496bba` (a mercenary): the key `npc<A>about` with A the unit's own number, no `TalkTo`, the Talk sound."""
        return self._do(Effect("text", "npc%dabout" % self.person().a), Effect("sound", "talk"))

    def hire_button(self):
        """Button 0 (and a mercenary figure's release): only for a mercenary with a word; Dismiss when bit 31 is set, else Accept."""
        p = self.person()
        w = self.word_of()
        if p is None or p.kind != "merc" or w is None:
            return []
        return self.dismiss() if w[1] & TAKEN else self.accept()

    def talk_button(self):
        """Button 1: Talk for an NPC (`+0xb8 >= count(+0xc0)`), About for a mercenary, nothing for nobody (INFERRED: the handler needs a unit)."""
        p = self.person()
        if p is None or self.word_of() is None and p.kind == "npc":
            return []
        return self.talk() if p.kind == "npc" else self.about()

    def figure_release(self, i):
        """The release on figure `i` (`0x49a197` calls the press again and acts at once): select, then Hire / Fire for a mercenary, Talk for an NPC."""
        self.select(i)
        p = self.person()
        if p is None:
            return []
        return self.hire_button() if p.kind == "merc" else (self.talk() if self.word_of() is not None else [])

    def button_release(self, b):
        """Button `b` released over itself: 0 / 1 as above, 2 = Exit (the caller closes through `TownCore.close_window`)."""
        return self.hire_button() if b == 0 else self.talk_button() if b == 1 else []

    # -- the hero arrows (town-hero 3: `0x49b6e5` next, `0x49b77c` previous; wrap in both directions) ------------------------------------------------
    def hero_next(self):
        if self.heroes:
            self.hero = 0 if self.hero + 1 >= len(self.heroes) else self.hero + 1
        return self.hero

    def hero_prev(self):
        if self.heroes:
            self.hero = len(self.heroes) - 1 if self.hero == 0 else self.hero - 1
        return self.hero

    def shown_hero(self):
        """The roster entry of the hero shown in the info panel, None without heroes."""
        if not self.heroes:
            return None
        n = self.heroes[self.hero]
        return next((e for e in self.game.roster if e.number == n), None)


# -- the dialogue (story) window's pages -------------------------------------------------------------------------------------------------------

def voice_folder(key):
    """The speech folder of the dialogue player `FUN_004dc84c` (sound.md 4.3): `talk` / `accept` / `reject` / `about` for the `npc<A>...` keys, `town` for the keeper / man / guard keys."""
    k = key.lower()
    if k.startswith("npc"):
        for f in ("talk", "accept", "reject", "about"):
            if f in k:
                return f
    if "keeper" in k or "man" in k or "guard" in k:
        return "town"
    return None


def voice_path(key, pg, n, flags, exists=None):
    """`speech/<folder>/NNNNLCCCpPP.wav` of page `n` (`about`: `NNNNt000pPP`, no class letter), None when the key has no voice folder or the file is missing (the exe plays only existing files)."""
    from engine.townscene import voice_letter
    folder = voice_folder(key)
    if folder is None or pg is None:
        return None
    letter = voice_letter(flags) if pg.iam or pg.npc == 21 else "t"
    if folder == "about":
        path = "speech/about/%04dt000p%02d.wav" % (pg.npc, n)
    else:
        digits = re.search(r"\d*$", key).group()[:5].rjust(3, "0")
        path = "speech/%s/%04d%s%sp%02d.wav" % (folder, pg.npc, letter, digits, n)
    return path if exists is None or exists(path) else None


class Dialogue:
    """The story window on a `town.txt` section (`FUN_0041d15e`; ui-layout 11.5): page 1 is made at once, Ok shows the next page, the window closes when no page qualifies.  `flags` =
    `story.hero_flags(female, mage)`; `exists(path)` the speech file test.  A section without a qualifying page 1 shows "Nothing to say" (and Ok then looks for page 2)."""

    def __init__(self, text, key, flags, exists=None):
        self.key, self.flags, self.exists = key, flags, exists
        self.sec = story.section(text, key)
        self.wide = story.has_speaker_layout(self.sec)
        self.n = 0
        self.page = None
        self.text = story.NOTHING_TO_SAY
        self.voice = None                      # the speech file of the page now shown (the screen plays it)
        self.tips = 0
        self.advance()

    def advance(self):
        """Message `0x470` (Ok): the page counter grows and the page's text replaces the widget's; False when no page qualifies (the window closes)."""
        self.n += 1
        pg = story.page(self.sec, self.n, self.flags)
        if pg is None:
            return False
        self.page = pg
        self.text = pg.text.replace("\r\n", "\n").rstrip("\n")
        self.voice = voice_path(self.key, pg, self.n, self.flags, self.exists)
        if pg.tips:
            self.tips = pg.tips
        return True

    @property
    def npc(self):
        """The speaker of the page shown (the picture changes only with a page that has `npc=`)."""
        return self.page.npc if self.page is not None else 0


# -- the ambient scheduler (town-inn 3c) ---------------------------------------------------------------------------------------------------------

DEFAULT_FRAMES = {"candle": 10, "cauldron": 21, "drink": 40, "breath": 24,
                  "waterdrop": 10, "druid1": 40, "druid2": 30, "kaarg1": 15, "kaarg2": 25, "kaarg3": 3, "kaarg4": 7}     # the druid / Kaarg counts are the load loops of `0x49c359` / `0x49e451` (CONFIRMED)

DRUID_DIR = "graphics/interface/inn_druid/"
KAARG_DIR = "graphics/interface/inn_kaarg/"
# the Kaarg "a5" event: the frame index drawn at each 100 ms step (`0x5f3d08`, ends at -1), run-length (value, count): 0..3, then the long holds
KAARG_A5 = ((0, 1), (1, 1), (2, 1), (3, 1), (4, 9), (5, 1), (6, 1), (7, 1), (8, 12), (5, 1), (6, 1), (7, 1), (8, 1), (9, 1), (10, 1), (11, 1), (12, 1), (13, 10), (14, 1), (15, 1),
            (16, 1), (17, 1), (18, 1), (19, 1), (20, 11), (21, 1), (22, 1), (23, 1), (24, 10), (5, 1), (6, 1), (7, 1), (24, 11), (25, 1), (26, 1), (27, 1), (28, 1))
KAARG_A5_FRAMES = tuple(v for v, n in KAARG_A5 for _ in range(n))


class Ambient:
    """The centre panel's draw-time scheduler, one `advance(dt_ms)` per draw (the statics are the exe's; `rand()` = `randrange(32768)`, the CRT).

    Human class (CONFIRMED `0x497adf`): the steam sound every draw after more than 10 s; the candle and cauldron objects advance one frame per draw after more than 100 ms; the
    idle event after `D = rand / 16 + 3000` ms since the last one: D odd = the "drink" tender animation (object forward to its end, then backward to frame 0, the drink sound at
    frame 30, glotok when it ends), D even = the "breath" animation (forward once, chair + Breath at the start); the event steps every more than 83 ms.  The ambient loop is
    `water.wav` (re-armed every draw).

    Druid (CONFIRMED `0x49cf22`, draw of the class `0x49ce4f`; town-inn 3c): a water-drop object (10 frames) steps every > 100 ms and plays one of `DWater1..4` at its frame 0;
    the event timer `D = rand / 16 + 3200` picks the state `(D & 3) + 1` (4 -> 3): 1 = the 40-frame taverner object `a1` (sound `Ddruid4` at the start, `Ddruid41` at its frame
    30), 2 = the 30-frame `a2` (`DDruid3` at the start), 3 = the static `a30001` for one step, then `D = rand / 16 + 1000` and a 4th step of the same picture before the pause; `a1` /
    `a2` end at their last frame (D = rand / 16 + 3200); the objects step every > 100 ms of the event stamp.  A second timer (`2000 + rand(2000)` ms, set at the load) plays one of the bird voices
    `Dbird4 / 41 / 42`.  The ambient loop is `Dforest2` (started at the load).

    Kaarg (CONFIRMED `0x49f467`, class `0x49f353`): no idle delay: whenever no event runs one starts at once, `r = rand(20) + 1` (`FUN_0051fa25`): 1, 2, 5 = state r, 3 / 4 / 6 = state 3,
    7..21 = state 4; state 1 plays `Kman3`, 2 plays `Kman2`; states 1..4 step the objects `a1` (15 frames), `a2` (25), `a3` (3), `a4` (7) every > 100 ms to their last frame, state 5 walks
    the frame table `KAARG_A5`.  Two independent `2000 + rand(2000)` ms timers: `Kdish1..4` (the drop) and `Kvox6..8`.  The loop is `Kvox5`."""

    def __init__(self, town, rng, frames=None):
        self.town, self.rng = town, rng
        self.frames = dict(DEFAULT_FRAMES, **(frames or {}))
        self.now = 0
        self.steam_at = self.event_at = self.cand_at = self.drop_at = 0          # the stamps `0x627608`, `0x6275c4` (druid `0x6275d0`), `0x6275f4`; the druid water stamp `0x6275e8`
        self.delay = self._delay(3200 if town == 3 else 3000)                    # `0x627604` (druid `0x6275dc`)
        self.kind = 0                                                            # human `0x62760c`: 0 idle, 1 drink, 2 breath
        self.dir = 0                                                             # human `0x627610`: 1 forward, -1 backward
        self.candle = self.cauldron = self.tender = self.drop = 0                # the objects' frames (`drop`: the druid water object)
        self.state = -1                                                          # druid `0x5f3e88` / Kaarg `0x5f3e8c`: -1 none, 1..5 the running event
        self.obj = 0                                                             # the running event object's frame
        self.idx = 0                                                             # Kaarg `+0x4bc`: the a5 table index
        self.step_at = 0                                                         # Kaarg `0x6275e0`
        self.voice_at = self.timer_at = 0                                        # `+0x460` / `+0x4c8` and Kaarg `+0x4c0` (set at construction)
        self.voice_delay = self.timer_delay = 2000 + self._r(2000)
        if town == 2:
            self.timer_delay = 2000 + self._r(2000)
        self.events = []                                                         # (path,) one-shots since the last take
        self._drunk = False

    @property
    def loop(self):
        return {1: HUMAN_SLOTS["water"], 2: KAARG_LOOP, 3: DRUID_LOOP}.get(self.town)

    def _delay(self, base=3000):
        return self.rng.randrange(32768) // 16 + base

    def _r(self, n):
        """`FUN_004a0fd0(n)`: `((rand * n) / 0x7fff) % n`."""
        return ((self.rng.randrange(32768) * n) // 0x7FFF) % n

    def _rk(self, n):
        """`FUN_0051fa25(n)`: `rand * (n + 1) >> 15` (0..n)."""
        return (self.rng.randrange(32768) * (n + 1)) >> 15

    def take_events(self):
        out, self.events = self.events, []
        return out

    def tender_ops(self):
        """The tender object drawn this frame (path, frame) or None (idle: the background shows him)."""
        if self.town != 1 or self.kind == 0:
            return None
        if self.kind == 1:
            return "graphics/interface/inn/tender/drink/dr%04d.bmp" % (self.tender + 1)
        return "graphics/interface/inn/tender/breath/br%04d.bmp" % (self.tender + 1)

    def objects(self):
        """The druid / Kaarg objects drawn over the background this frame: `(path, x, y)` relative to the centre panel, in the exe's order (CONFIRMED positions: druid water `0x49d0a1`
        (0xa8, 0x90), a1 / a2 `0x49d22a` / `0x49d281` (0x28, 0x80), a3 `0x49d2bf` (0x68, 0x98); Kaarg a1 / a2 (0x48, 0x58), a3 (0x70, 0x70), a4 (0xc8, 0x88), a5 (0x58, 0x54))."""
        if self.town == 3:
            out = [(DRUID_DIR + "waterdrop/d%04d.bmp" % (self.drop + 1), 0xA8, 0x90)]
            if self.state == 1:
                out.append((DRUID_DIR + "taverner/a1%04d.bmp" % (self.obj + 1), 0x28, 0x80))
            elif self.state == 2:
                out.append((DRUID_DIR + "taverner/a2%04d.bmp" % (self.obj + 1), 0x28, 0x80))
            elif self.state in (3, 4):
                out.append((DRUID_DIR + "taverner/a30001.bmp", 0x68, 0x98))
            return out
        if self.town == 2:
            d = KAARG_DIR + "taverner/"
            return {1: [(d + "a1%04d.bmp" % (self.obj + 1), 0x48, 0x58)], 2: [(d + "a2%04d.bmp" % (self.obj + 1), 0x48, 0x58)],
                    3: [(d + "a3%04d.bmp" % (self.obj + 1), 0x70, 0x70)], 4: [(d + "a4%04d.bmp" % self.obj, 0xC8, 0x88)],
                    5: [(d + "a5%04d.bmp" % KAARG_A5_FRAMES[self.idx], 0x58, 0x54)]}.get(self.state, [])
        return []

    def advance(self, dt_ms):
        self.now += dt_ms
        {1: self._human, 2: self._kaarg, 3: self._druid}[self.town]()

    def _human(self):
        now, f = self.now, self.frames
        if now - self.steam_at > 10000:
            self.events.append(HUMAN_SLOTS["steam"])
            self.steam_at = now
        if now - self.cand_at > 100:
            self.candle = (self.candle + 1) % f["candle"]
            self.cauldron = (self.cauldron + 1) % f["cauldron"]
            self.cand_at = now
        if now - self.event_at > self.delay:
            if self.delay & 1:
                self.kind = self.dir = 1
                self.tender = 0
            else:
                self.kind = 2
                self.tender = 0
                self.events += [HUMAN_SLOTS["chair"], HUMAN_SLOTS["breath"]]
        if self.kind == 1 and self.tender == 30 and not self._drunk:
            # the exe plays the slot on every draw at frame 30 (`FUN_00438570`: `FUN_0045a964` = "an instance of this sound is still playing" suppresses it); drink.wav (1277 ms)
            # outlasts one hold of the frame and the two visits are 1.5 s apart, so one play per visit of the frame is the same
            self.events.append(HUMAN_SLOTS["drink"])
            self._drunk = True
        if self.kind and now - self.event_at > 83:
            if self.kind == 2:
                if self.tender + 1 < f["breath"]:
                    self.tender += 1
                else:
                    self.kind = 0
                    self.tender = 0
                    self.delay = self._delay()
            elif self.dir == 1:
                if self.tender + 1 < f["drink"]:
                    self.tender += 1
                    self._drunk = False
                else:
                    self.dir = -1
            else:
                if self.tender > 0:
                    self.tender -= 1
                    self._drunk = False
                else:
                    self.kind = self.dir = 0
                    self.delay = self._delay()
                    self.events.append(HUMAN_SLOTS["glotok"])
            self.event_at = now

    def _druid(self):
        now, f = self.now, self.frames
        if now - self.drop_at > 100:                                             # `0x49d0a9`: the water object steps; at frame 0 one of four sounds
            if self.drop == 0:
                self.events.append(DRUID_DROPS[self._r(4)])
            self.drop = (self.drop + 1) % f["waterdrop"]
            self.drop_at = now
        if now - self.event_at > self.delay:                                     # `0x49d16c`
            self.state = (self.delay & 3) + 1
            if self.state == 4:
                self.state = 3
            self.obj = 0
            self._drunk = False
            if self.state in DRUID_EVENTS:
                self.events.append(DRUID_EVENTS[self.state])
        if self.state == 1 and self.obj == 30 and not self._drunk:              # `0x49d23d`; the slot plays 853 ms, the frame is held ~100 ms: once per visit
            self.events.append(DRUID_FRAME30)
            self._drunk = True
        if self.state != -1 and now - self.event_at > 100:                       # `0x49d2c4`: the step
            if self.state in (1, 2):
                if self.obj == f["druid%d" % self.state] - 1:                    # `FUN_004015c5` = "already at the last frame"
                    self.state, self.obj = -1, 0
                    self.delay = self._delay(3200)
                else:
                    self.obj += 1
                    self._drunk = False
                self.event_at = now
            elif self.state == 3:
                self.state = 4
                self.delay = self._delay(1000)
                self.event_at = now
            else:
                self.state = -1
        self._tail(DRUID_VOICES)

    def _kaarg(self):
        now, f = self.now, self.frames
        if self.state == -1:                                                     # `0x49f5b5`: no pause between events
            self.idx = 0
            r = self._rk(20) + 1
            self.state = r if r in (1, 2, 5) else 3 if r in (3, 4, 6) else 4
            if self.state in KAARG_EVENTS:
                self.events.append(KAARG_EVENTS[self.state])
        if self.state != -1 and now - self.step_at > 100:                        # `0x49f777`
            if self.state == 5:
                self.idx += 1
                if self.idx >= len(KAARG_A5_FRAMES):                             # the table's -1
                    self.state, self.idx = -1, 0
            elif self.obj == f["kaarg%d" % self.state] - 1:
                self.state, self.obj = -1, 0
            else:
                self.obj += 1
            self.step_at = now
        self._tail(KAARG_VOICES)

    def _tail(self, voices):
        """The common tail: the bird / voice timer and (Kaarg) the drop timer, `2000 + rand(2000)` ms each."""
        now = self.now
        if now - self.voice_at > self.voice_delay:
            self.events.append(voices[self._r(3) + 1])
            self.voice_delay = 2000 + self._r(2000)
            self.voice_at = now
        if self.town == 2 and now - self.timer_at > self.timer_delay:
            self.events.append(KAARG_DROPS[self._r(4)])
            self.timer_delay = 2000 + self._r(2000)
            self.timer_at = now


# -- what the left sheet and the info panel show (town-hero 2; reduced, see the marks) ---------------------------------------------------------------

def _unit_of(t, entry=None):
    """A stand-in client unit for `engine.ui.info` (the doll builder reads: human flag, template, face, equipment)."""
    from types import SimpleNamespace
    st = entry.state if entry is not None else None
    return SimpleNamespace(human=True, stats=st.stats if st is not None else t, face=st.face if st is not None else t.fields.get("face", 1), type_id=t.unit_type,
                           equipment=st.equipment if st is not None else (), name=getattr(entry, "name", ""))


def hero_portrait(assets, entry):
    """The paper doll of a party hero (`("doll", paths)`: the carried equipment, or the template's own for a hero never in a world); None without data."""
    t = assets.unit_stats().lookup(True, entry.server_id)
    if t is None:
        return None
    from types import SimpleNamespace
    from engine.ui import info
    return ("doll", tuple(info.doll_layers(SimpleNamespace(item_table=assets.items()), _unit_of(t, entry))))


def person_portrait(assets, p):
    """The left sheet's picture of a person (`0x494832`): every human-class unit (heroes, mercenaries, peasants: `+0x1b8 & 0x11`) the paper doll from the template's gear, every monster `graphics\\infowindow\\<InfoPicture><face if > 1>.bmp`."""
    t = p.template
    if t is None:
        return None
    if p.hero or t.kind == "human":
        from types import SimpleNamespace
        from engine.ui import info
        return ("doll", tuple(info.doll_layers(SimpleNamespace(item_table=assets.items()), _unit_of(t))))
    rec = assets.unit_types().get(t.unit_type)
    name = rec.values.get("InfoPicture") if rec is not None else None
    if not name:
        return None
    face = t.fields.get("face", 1)
    return ("bmp", "graphics/infowindow/%s%s.bmp" % (name, face if face > 1 else ""))


def person_unit(p):
    """A world-free client unit of the person (owner 0): what `World._load_units` builds for a fresh template (human: the recomputed HP / mana / skills of `progression`, level 1,
    no equipment beyond the template's strings; monster: the template's HP, mana for a mage).  Players need no world: `info.text_rows` reads only this unit and a stub world."""
    from engine.world import Unit
    from allods2.formats import progression as prog
    t = p.template
    human = t.kind == "human"
    hp, mana = prog.derived_vitals(t) if human else (t.hp_max, max(0, t.get("mana_max", -1) or 0))
    u = Unit(0x6000, t.unit_type, 0, 0, 0, hp=hp, hp_max=hp, human=human, server_id=t.server_id, move_type=t.movement_type, face=t.face, stats=t, known=True)
    if human:
        u.skills = prog.skills_of(t)
        u.mana = u.mana_max = mana
        u.xp, u.xp_total = prog.start_pools(u.skills)
    else:
        u.mana = u.mana_max = mana
    return u


def person_rows(p, main, unit_names, items=None, spells=None):
    """Text rows `(text, x, y, flags, table)` of the left sheet, panel-relative (the exe draws `FUN_0046aa1d` at (12, 0), detail 7: the owner is player 0): **every** row of
    `info.text_rows` (ui-layout 11.1) for `person_unit` over a stub world (`items` / `spells` = the item and spell tables for the gear numbers and a mage's Dmg; without them
    the template strings give no armour).  The Mercenary line is the mercenary list's only (INFERRED: the exe's war test of player 0 is run-time state)."""
    from types import SimpleNamespace
    from engine.ui import info
    t = p.template
    if t is None:
        return []
    u = person_unit(p)
    world = SimpleNamespace(item_table=items, spell_table=spells, players={}, units={})
    merc_line = main.line(info.MERCENARY)
    out = []
    for r in info.text_rows(world, u, main, unit_names.lines, 1, know_all=True):
        if r.text == merc_line and r.y == 0x12 and p.kind != "merc":
            continue
        out.append((r.text, r.x, r.y, r.flags, r.table))
    if p.kind == "merc" and not any(r[2] == 0x12 and r[1] == 0x48 for r in out):       # a monster-class mercenary too (`0x46ab2c`: `+0x1b8 & 0x11`)
        out.insert(0, (merc_line, 0x48, 0x12, info.CENTRE, info.GOLD))
    return out
    if unit_names.line(t.unit_type):
        rows.append((unit_names.line(t.unit_type), 0x48, 0x1C, CENTRE, GOLD))
    if p.kind == "merc":
        rows.append((main.line(0x54), 0x48, 0x12, CENTRE, GOLD))
    f = t.fields
    for k, key in enumerate(("body", "reaction", "mind", "spirit")):
        y = 0x2C + 10 * k
        rows.append((main.line(0x0F + k), 6, y, LEFT, GOLD))
        rows.append(("%d" % max(0, f.get(key, 0)), 0x50, y, RIGHT, SAGE))
    hp = f.get("hp_max", -1)
    if hp > 0:
        rows += [(main.line(0x13), 0x73, 0x2C, CENTRE, GOLD), ("%d/%d" % (hp, hp), 0x73, 0x36, CENTRE, SAGE)]
    mana = f.get("mana_max", -1)
    if mana > 0:
        rows += [(main.line(0x14), 0x73, 0x40, CENTRE, GOLD), ("%d/%d" % (mana, mana), 0x73, 0x4A, CENTRE, SAGE)]
    if f.get("defence", -1) >= 0:
        rows += [(main.line(0x1A), 0x4A, 0x62, LEFT, GOLD), ("%d" % f["defence"], 0x8C, 0x62, RIGHT, SAGE)]
    return rows


def hero_unit(assets, entry, owner=1):
    """A world-free client unit of a party hero for the info panel's text mode (town-hero 8): the template's unit, then the carried `state` (`party.restore`: gear recompute, HP / mana
    at the maxima) or the creation `spec` (`party.apply_spec`) over a stub world with the item / spell tables.  None without data."""
    from types import SimpleNamespace
    from allods2.formats import progression as prog
    from engine import party
    from engine.world import Unit
    t = assets.unit_stats().lookup(entry.human, entry.server_id)
    if t is None:
        return None
    human = t.kind == "human"
    world = SimpleNamespace(item_table=assets.items(), spell_table=assets.spells(), players={}, units={}, tick=0)
    hp, mana = prog.derived_vitals(t) if human else (t.hp_max, max(0, t.get("mana_max", -1) or 0))
    u = Unit(0x6000, t.unit_type, owner, 0, 0, hp=hp, hp_max=hp, human=human, server_id=t.server_id, move_type=t.movement_type, face=t.face, stats=t, known=True)
    if human:
        u.skills = prog.skills_of(t)
        u.mana = u.mana_max = mana
        u.xp, u.xp_total = prog.start_pools(u.skills)
    if entry.state is not None:
        party.restore(world, u, entry.state)
    elif entry.spec is not None:
        party.apply_spec(world, u, entry.spec)
    return u


def hero_rows(assets, entry, main, unit_names, hero_name="Hero"):
    """The text mode of the info panel (`FUN_004af3bf` -> `FUN_0046aa1d`, ui-layout 11.1; the viewer owns the hero: detail 7, the name row, Weight / XP)."""
    from types import SimpleNamespace
    from engine.ui import info
    u = hero_unit(assets, entry)
    if u is None:
        return []
    world = SimpleNamespace(item_table=assets.items(), spell_table=assets.spells(), players={}, units={}, tick=0)
    return [(r.text, r.x, r.y, r.flags, r.table) for r in info.text_rows(world, u, main, unit_names.lines, 1, hero_name, know_all=True)]
