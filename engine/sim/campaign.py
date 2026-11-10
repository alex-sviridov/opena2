"""Scenario.dll's campaign state and the end-of-mission flow of the client (docs/engine/triggers.md section 11; CONFIRMED in the GOG
`allods2.exe` window procedure `FUN_004852d8` and in `Scenario.dll`, sha256 in docs/formats/README.md).  No windows: the state machine
and the choices a UI has to offer.  Layer 4: reads and writes `World` flags and the `Campaign` object only.

Window messages (all posted to the game window): `0x430` mission complete (client message `0xb5`, `0x486ddb`), `0x433` / `0xff` -> `0x431`
defeat dialog (client message `0xb4`, `0x486f7e`), `0x41d` end of the mission (`0x486a68`), `0x445` / `0x446` the defeat dialog's buttons.
Latches of the window object: `+0x3e4` (a mission ended with a result) and `+0x3e8` (the defeat dialog was opened); both are cleared at
every game start (`FUN_0048c8a3` `0x48d886`) and at the load of a save (`FUN_0048c2e9` `0x48c824` / `0x48c834`).
"""

from dataclasses import dataclass, field

# Scenario.dll variables read by the exe / the DLL (ScenarioGetVar = ordinal 1, array `0x10036028`, 1024 x i32)
SUBOBJECTIVE_BASE = 0x2F0       # 16 sub-objectives (script instant 36, check 24); ScenarioEnterLocation zeroes 0x2f0..0x2ff
CHAPTER = 0x300                 # starts at 10, +10 per finished main mission (the id % 10 == 0); >= 0x78 = the campaign is over
MERC_HIRED, MERC_MARK, MERC_TOWN, MERCENARIES = 0x200, 0x214, 0x228, 20     # + k (hero number k + 1): hired for the next mission / on offer / offering town
MERC_OFFERS = {20: ((1, 2),), 50: ((3, 3),), 60: ((6, 2),), 70: ((4, 3),), 100: ((7, 2),)}      # case n -> (mercenary number, town) put on offer (11.1)
RECRUIT = 0x305                 # hero server number (0x15..0x1e) a mission end recruits (FUN_004f312a); set to 0x17 by mission 40
MISSION_DONE_BASE = 0x380       # 1 + mission id: set to 1 when ScenarioLeaveLocation finishes that mission
HERO_DEAD_BASE = 0x213          # + server id of a hero below 0x15: set to 0 by the client when it dies (combat 12)
FINAL_CHAPTER = 0x78
VAR_COUNT = 1024
START_VARS = {CHAPTER: 10}      # ScenarioNewGame (0x100033be): memset(array, 0, 0x1000), then array[0x300] = 10

# the defeat dialog (FUN_0044d1e2): buttons by command id
BTN_MENU, BTN_LOAD, BTN_CONTINUE = 0x445, 0x446, 0x41D

MISSION, TOWN = 1, 2            # location types of the DLL


def new_game_vars():
    """A new campaign's variable array as the engine keeps it (a sparse dict, absent = 0)."""
    return dict(START_VARS)


@dataclass(frozen=True)
class Button:
    command: int
    label: str
    enabled: bool = True


@dataclass(frozen=True)
class Dialog:
    """What the client shows: `kind` "complete" (text entry 0x8c, one button) or "defeat" (text entry 0x8d, two buttons)."""
    kind: str
    buttons: tuple


@dataclass(frozen=True)
class Outcome:
    """What the flow asks the shell to do next.  `kind`: "main_menu" (end the game, window message 0x421), "load" (open the load-game
    window, 0x418), "ending" (the campaign is over: window message 0x428), "world_map" (a town is available: the town / world map
    screen), "mission" (no town available: ScenarioEnterLocation of the first available location and window message 0x468 = start it).
    `cutscene` is ScenarioLeaveLocation's code (-1 none; 48f919 plays it), `recruit` the hero number of Var(0x305) (0 none)."""
    kind: str
    cutscene: int = -1
    recruit: int = 0
    location: tuple = None


@dataclass
class Campaign:
    """Scenario.dll's state: the variables, the current location `(type, id)` (None = no location) and the available list."""
    vars: dict = field(default_factory=new_game_vars)
    location: tuple = None
    available: list = field(default_factory=list)
    times: list = field(default_factory=list)       # FUN_00493b40: the mission times, in 16-tick blocks (win+0x598)

    def get(self, n):
        return self.vars.get(n, 0)

    def set(self, n, v):
        self.vars[n] = v

    # --- ScenarioNewGame / EnterLocation / LeaveLocation ---------------------------------------------------------------------

    @classmethod
    def new_game(cls):
        """`ScenarioNewGame`: variables zero except the chapter 10; the available list holds town 1 and the player stands in it."""
        c = cls()
        c.available = [(TOWN, 1)]
        c.enter((TOWN, 1))
        return c

    def enter(self, loc):
        """`ScenarioEnterLocation(loc)` (0x10001d22): the current location, and the 16 sub-objective variables are zeroed."""
        self.location = loc
        for k in range(16):
            self.vars.pop(SUBOBJECTIVE_BASE + k, None)

    def _unlock(self, kind, n):
        if (kind, n) not in self.available:
            self.available.append((kind, n))

    def leave(self):
        """`ScenarioLeaveLocation` (0x10002806): returns the cutscene code (-1 none).  A town: only the current location is cleared (town 1
        also leaves the available list).  A mission `n` (`0x10001da5`): the mission leaves the list, Var(0x380 + n) = 1, the unlocks of
        `UNLOCK`, the chapter +10 when n % 10 == 0, and the cutscene code of the missions 10 / 30 / 70 / 80 / 110."""
        loc, self.location = self.location, None
        if loc is None:
            return -1
        kind, n = loc
        if kind == TOWN:
            if n == 1 and loc in self.available:
                self.available.remove(loc)
            return -1
        self.recruit_clear()
        for k in range(MERCENARIES):                    # step 3: a marker that is set becomes 2 when the mercenary was hired, else 1; every hire flag goes
            if self.get(MERC_MARK + k):
                self.vars[MERC_MARK + k] = 2 if self.get(MERC_HIRED + k) else 1
            self.vars.pop(MERC_HIRED + k, None)
        if loc in self.available:
            self.available.remove(loc)
        self.vars[MISSION_DONE_BASE + n] = 1
        code = -1
        for k, i in UNLOCK.get(n, ()):
            self._unlock(k, i)
        for hero, town in MERC_OFFERS.get(n, ()):       # the markers a case creates are not promoted in the same call (the loop ran first)
            self.offer_mercenary(hero, town)
        if n == 20 and self.get(0x304):
            self._unlock(MISSION, 21)
        if n == 40:
            self.vars[RECRUIT] = 0x17
        if n == 50:
            self.vars[0x303] = 1
            if self.get(0x30C):
                self._unlock(MISSION, 52)
        if n == 60:
            self.vars[0x306] = 1
        if n == 70:
            self.vars[0x302] = 1
        if n == 10:
            code = 1
        elif n == 30:
            code = 2
        elif n == 70:
            code = 3 if self.get(0x309) == 0 and self.get(0x30A) != 0 else -1
            self.vars[0x309] = 1
        elif n == 80:
            code = 3 if self.get(0x30A) == 0 and self.get(0x309) != 0 else -1
            self.vars[0x30A] = 1
        elif n == 110:
            code = 4 if self.get(0x30B) == 0 else 5
        if n % 10 == 0:
            self.vars[CHAPTER] = self.get(CHAPTER) + 10
        return code

    def recruit_clear(self):
        """`0x10001da5` starts with Var(0x305) = 0."""
        self.vars.pop(RECRUIT, None)

    # --- Scenario.dll town dialogue (11.2: CONFIRMED by running ScenarioEnterInn / ScenarioTalkTo on every chapter, town and flag state) ---------

    def offer_mercenary(self, hero, town):
        """Mercenary `hero` (1..7) goes on offer in `town`: marker `Var(0x213 + hero)` := 1, town `Var(0x227 + hero)`."""
        self.vars[MERC_MARK + hero - 1] = 1
        self.vars[MERC_TOWN + hero - 1] = town

    def enter_inn_words(self, town, is_mage=False, is_female=False):
        """`ScenarioEnterInn` (`0x1000286b`): the dialogue words the inn of `town` (2 or 3; town 1 only has the chapter 10 words) offers at the
        current chapter, in the routine's order: the chapter's rows, the town-3 rows (chapters 60-110), the town-2 rows (62 and the class slot),
        then the mercenary offers (INFERRED: the order of the three blocks after the per-chapter jump table; only the order of the offered missions
        in the available list depends on it)."""
        c, d, w = self.get(CHAPTER), (lambda k: self.get(MISSION_DONE_BASE + k)), []

        def add(t, a, b, gate=True):
            if gate:
                w.append((t << 28) | (b << 16) | a)

        if c == 10:
            add(0, 0xCF, 9)
            add(0, 0x83C, 8)
            add(3, 0x205, 10)
        elif c == 30:
            add(3, 0x16, 30)
            add(3, 0x83C, 31, not d(31))
            add(0, 0x83E, 39)
        elif c == 40:
            add(3, 0x16, 40)
            add(0, 0x83C, 48)
            for a, b in ((0x7DF, 41), (0x83F, 42), (0x7D4, 43)):
                add(3, a, b, not d(b))
        elif c == 50:
            add(0, 0x17, 49)
            add(3, 0x7E3, 53, not d(53))
        elif town == 2 and c == 60:
            add(3, 0x7D6, 61, not d(61))
            add(3, 0x83D, 63, not d(63))
        elif town == 2 and c == 70:
            add(3, 0x7D4, 73, not d(73))
            add(3, 0x83C, 72, not d(72))
        elif town == 2 and c == 80:
            m = 81 if is_mage else 82
            add(3, 0x7DA if is_mage else 0x7D9, m, not d(m))
        elif c == 90:
            if town == 2:
                add(3, 0x7D4, 90, not d(90))
            elif town == 3:
                add(3, 0x2A9, 91, not d(91))
                add(3, 0x7D3, 92, not d(92))
        elif c == 100:
            if town == 2:
                add(3, 0x7D6, 100, not d(100))
                add(3, 0x83D, 102, not d(102))
                add(3, 0x7D5, 103, d(91) and not d(103))
            elif town == 3:
                add(3, 0x2A9, 101, not d(101))
        elif town == 2 and c == 110:
            add(3, 0x7D6, 110)
        if town == 3 and 60 <= c <= 110:
            if c <= 80 and self.get(0x303):
                add(3, 0x2A8, 70, not d(70))
                add(3, 0x2A9, 71, not d(71))
            add(0, 0x5, 79, c > 60 and self.get(0x306) == 1)
            add(0, 0x2A3, 78, c > 60 and self.get(0x302) == 1)
        if town == 2 and c >= 60:
            add(3, 0x16, 62, d(53) and not d(62))
            slot = (2 if is_female else 3) if is_mage else (1 if is_female else 0)
            if d(63):
                if not any(d(k) for k in range(74, 78)):
                    add(3, 0x7E6, 74 + slot)
                elif not any(d(k) for k in range(84, 88)):
                    add(3, 0x7E6, 84 + slot)
                elif not any(d(k) for k in range(93, 97)):
                    add(3, 0x7E6, 93 + slot)
        for k in range(MERCENARIES):
            if self.get(MERC_TOWN + k) == town and self.get(MERC_MARK + k) in (1, 2):
                w.append((k + 1) | (self.get(MERC_MARK + k) << 28) | ((self.get(MERC_HIRED + k) > 0) << 31))
        return w

    def talk_to(self, word):
        """`ScenarioTalkTo` (`0x100032c0`): the effect of picking a dialogue word.  Type 0: A = 5 puts the orc on offer (`0x218`, town 3,
        `0x306` := 2), A = 0x2a3 with B = 0x4e sets `0x302` := 2; type 1 toggles the hire flag of mercenary A; type 3: the offered mission B
        joins the available list (a known location), B = 10 sets `0x301`, (A = 0x16, B = 30) puts the knight on offer in town 2."""
        t, a, b = (word >> 28) & 7, word & 0xFFFF, (word >> 16) & 0xFFF
        if t == 0:
            if a == 5:
                self.vars[0x218], self.vars[0x22C], self.vars[0x306] = 1, 3, 2
            elif a == 0x2A3 and b == 0x4E:
                self.vars[0x302] = 2
        elif t == 1:
            if 1 <= a <= MERCENARIES:
                self.vars[MERC_HIRED + a - 1] = 0 if self.get(MERC_HIRED + a - 1) else 1
        elif t == 3:
            if b in KNOWN_MISSIONS:
                self._unlock(MISSION, b)
            if b == 10:
                self.vars[0x301] = 1
            if a == 0x16 and b == 30:
                self.vars[0x215], self.vars[0x229] = 1, 2

    def town_available(self):
        """`ScenarioIsTownAvailable(0)` (0x10003800): any town in the available list."""
        return any(k == TOWN for k, _ in self.available)


# Missions a type-3 word can offer (11.2: the union over every chapter, town and flag state) and the ones the completion cases add
KNOWN_MISSIONS = frozenset((10, 20, 21, 30, 31, 32, 40, 41, 42, 43, 50, 52, 53, 60, 61, 62, 63) + tuple(range(70, 78)) + (80, 81, 82)
                           + (84, 85, 86, 87) + tuple(range(90, 97)) + (100, 101, 102, 103, 110))
STORY_HEROES = range(0x15, 0x1F)

# Missions (and towns) a finished mission makes available (the switch of 0x10001da5; FUN_1000192f = mission, FUN_1000199f = town)
UNLOCK = {10: ((MISSION, 20),), 20: ((TOWN, 2),), 31: ((MISSION, 32),), 40: ((MISSION, 50), (MISSION, 60)), 50: ((TOWN, 3),),
          60: ((MISSION, 80),)}


# --- the client flow ------------------------------------------------------------------------------------------------------------

def start_game(world):
    """`FUN_0048c8a3`: both latches are cleared (also at a save load)."""
    world.mission_ended = False
    world.defeat_latch = False


def _human(world):
    return next((p for _, p in sorted(world.players.items()) if p.human), None)


def poll(world, camp, saves_exist=False):
    """What the client does with the messages the server has sent since the last poll.  Returns a `Dialog` to show, an `Outcome` when the
    flow goes on without one (the final chapter), or None.  Mutates the window latches like the window procedure does.

    * message `0xb5` (`World.mission_complete`, window message `0x430`): the mission-ended latch is set; with Var(0x300) >= 0x78 the flow
      posts `0x41d` at once, otherwise the modal "complete" dialog opens (one button, command `0x41d`).
    * message `0xb4` (`Player.defeat_dialog`, `0x433` -> `0x431`): opens the "defeat" dialog once (latch `+0x3e8`; game mode 2 only):
      buttons `0x445` (main menu) and `0x446` (load a game; disabled when no `game*.sav` exists)."""
    if world.dialog is not None:
        return world.dialog
    if world.mission_complete and not world.mission_ended:
        world.mission_ended = True
        if camp.get(CHAPTER) >= FINAL_CHAPTER:
            return press(world, camp, BTN_CONTINUE)
        world.dialog = Dialog("complete", (Button(BTN_CONTINUE, "continue"),))
        return world.dialog
    p = _human(world)
    if p is not None and p.defeat_dialog and not world.defeat_latch:
        world.defeat_latch = True
        world.dialog = Dialog("defeat", (Button(BTN_MENU, "main menu"), Button(BTN_LOAD, "load game", bool(saves_exist))))
        return world.dialog
    return None


def press(world, camp, command):
    """A button (or the posted window message `0x41d`).  Closes the dialog (the modal bit is cleared by `0x44c`) and returns the `Outcome`.

    * `0x445`: end the running game (`0x41e`) and back to the main menu (`0x421`).  `0x446`: the load-game window (`0x418`); a disabled button
      does nothing (returns None).
    * `0x41d`: with the mission-ended latch clear (the player left a mission by the menu) it is `0x445`.  Otherwise the mission time is recorded
      (`tick >> 4`), the server keeps the roster (`FUN_004ebd5f`: the carry-over of saves section 4, not modelled here), the hero Var(0x305)
      is recruited (`FUN_004f312a`: `Outcome.recruit`), `ScenarioLeaveLocation` runs, and the next screen follows: chapter >= 0x78 the ending,
      else the world map when a town is available, else the first available location is entered and started."""
    dlg, world.dialog = world.dialog, None
    if command == BTN_LOAD:
        if dlg is not None and not next((b.enabled for b in dlg.buttons if b.command == BTN_LOAD), True):
            world.dialog = dlg
            return None
        return Outcome("load")
    if command == BTN_MENU or (command == BTN_CONTINUE and not world.mission_ended):
        return Outcome("main_menu")
    return complete(camp, world.tick)


def complete(camp, tick):
    """The part of `0x41d` after the roster carry-over (which belongs to the caller): the mission time, `ScenarioLeaveLocation`, the recruit number
    (`Outcome.recruit`) and the next screen."""
    camp.times.append(tick >> 4)
    code = camp.leave()
    recruit = camp.get(RECRUIT)            # read after the leave: a mission's leave zeroes it first (0x10001da5), mission 40 sets 0x17
    if camp.get(CHAPTER) >= FINAL_CHAPTER:
        return Outcome("ending", code, recruit)
    if camp.town_available():
        return Outcome("world_map", code, recruit)
    if camp.available:
        loc = camp.available[0]
        camp.enter(loc)
        return Outcome("mission", code, recruit, loc)
    return Outcome("world_map", code, recruit)


def message_action(n, modal=False):
    """Window message `0x433` with wParam `n` (client message `0xb6` = script instant 2 / sub-objective messages; `0xb4` posts `0xff`;
    CONFIRMED `0x485f73`-`0x48615f`).  Returns the actions: `0xff` opens the defeat dialog (`0x431`); `0xfe` plays sound `0xdc` on UI slot
    `0x10`; `0xfd` the same on slot `0xe`; `0xfa` sound `0xdc` on slot `0xe` and shows `patch.txt` line `0x61` ("You've got a new mission!") for 30 s in the message
    line (the "line" action's id is a patch.txt index); any other value shows the mission text section `#event<n>` of `main\\text\\mission<id>.txt` in a story window (`FUN_0041d15e`
    with the key `"event%d"`), or, while a modal dialog is open (window bit 8), queues the number (list `0x627170`)."""
    if n == 0xFF:
        return (("defeat",),)
    if n == 0xFE:
        return (("sound", 0x10, 0xDC),)
    if n == 0xFD:
        return (("sound", 0xE, 0xDC),)
    if n == 0xFA:
        return (("sound", 0xE, 0xDC), ("line", 0x61, 30000))
    return (("queue", n),) if modal else (("text", "event%d" % n),)
