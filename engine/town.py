"""The town core (L4, docs/engine/town.md 1-2): the client's screen mask and the message flow between the world map, the town scene, the inn, the shop and
the missions, as pure code over the campaign's Scenario state (`engine.sim.campaign.Campaign`).  No drawing, no pygame, no shell import: the screens
(`engine/shell/town.py`) feed it clicks as messages and show whatever `view` says.

`TownCore.mask` = `client+0x404`.  `post(msg)` queues a client message, `pump()` runs the queue (the exe's own message loop: `0x445` -> `0x44c` -> `0x42e`
is a chain of posts); every outward effect is appended to `events` (autosave slots, music, speech, cutscene codes, party point), the test surface of the
state machine.  A move that the exe's guard refuses is dropped silently, as the exe drops it."""

from dataclasses import dataclass

from engine.sim.campaign import MISSION, TOWN

# the mode mask bits (town-hero 1)
M_MISSION, M_SHOP, M_INN, M_MODAL, M_MAP = 1, 2, 4, 8, 0x10
HERO_ARROWS = 0x226                 # the screens that show the info panel's hero arrows (0x200 chargen | 0x20 never set | inn 4 | shop 2)
FINAL_CHAPTER = 0x78                # Var(0x300) >= this = the ending (0x428)
LEAVE_GATE = 0x301                  # the human scene's leave click needs Var(0x301) != 0 (0x4cad3c)

# messages (town.md 1)
MSG_MISSION_OVER, MSG_SHOP, MSG_INN, MSG_LEAVE, MSG_SCENE = 0x41d, 0x42a, 0x42b, 0x42d, 0x42e
MSG_AUTOSAVE, MSG_WINDOW_OK, MSG_WINDOW_CLOSED, MSG_ENTER = 0x442, 0x445, 0x44c, 0x468

AUTOSAVE_MISSION, AUTOSAVE_TOWN = 9999, 9998        # game9999.sav at a mission start (0x48c8a3), game9998.sav on leaving a town (0x4884b9)
MAP_MUSIC = "map"                                   # music\map.wav


@dataclass(frozen=True)
class TownWindows:
    """What a town id selects (town-hero 1): the scene class, the inn and shop windows (client field offsets), the scene's playlist (`soundtable.MUSIC_SCREENS`: b14 / b16 / b15)."""
    town: int
    scene: int
    inn: int
    shop: int
    music: str
    race: str


TOWNS = {1: TownWindows(1, 0x110, 0x104, 0xf8, "town1", "human"),
         2: TownWindows(2, 0x118, 0x10c, 0x100, "town2", "kaarg"),
         3: TownWindows(3, 0x114, 0x108, 0xfc, "town3", "druid")}


class TownError(Exception):
    pass


class TownCore:
    """The state of the screens.  `view`: None (no screen yet), "map", "scene", "inn", "shop", "mission", "ending"; `town` = the id of the town being
    visited (None on the map / in a mission); `intro` = the world map's intro-walk flag (`window+0x1b0`, set when town 1 is left); `party_point` =
    the location the party stands on (`SetPartyPoint`, a `(type, id)` pair until the map exists)."""

    def __init__(self, camp):
        self.camp = camp
        self.mask = 0
        self.view = None
        self.town = None
        self.intro = False
        self.party_point = None
        self.events = []
        self.queue = []
        self.visit = 0                      # arrivals in a town (`0x468` -> `0x48bbc0`; the exe's message `0x3f` regenerates the shop stock then, town-shop 5)
        self.stock, self.stock_visit = None, -1    # the shop object of the current visit (`engine.shop.open_stock`)

    # -- plumbing ----------------------------------------------------------------------------------------------------------------
    def post(self, msg, *args):
        self.queue.append((msg, args))

    def send(self, msg, *args):
        """Post and run to quiescence (a click = one message)."""
        self.post(msg, *args)
        self.pump()

    def pump(self):
        while self.queue:
            msg, args = self.queue.pop(0)
            h = self.HANDLERS.get(msg)
            if h is not None:
                h(self, *args)

    def _emit(self, *event):
        self.events.append(event)

    def take_events(self):
        out, self.events = self.events, []
        return out

    @property
    def windows(self):
        return TOWNS.get(self.town)

    @property
    def shows_hero_arrows(self):
        return bool(self.mask & HERO_ARROWS)

    # -- the world map (0x48b419) ------------------------------------------------------------------------------------------------
    def open_map(self):
        """`FUN_0048b419`: the map window opens, bit `0x10`, the map music."""
        self.view, self.town = "map", None
        self.mask |= M_MAP
        self._emit("music", MAP_MUSIC)

    def walk_to(self, loc):
        """The map's walk ended at `loc` (town-worldmap 4): own `0x445` -> `0x44c` (bit `0x10` cleared), post `0x468`, `ScenarioEnterLocation`.  Only
        the available locations can be walked to (the hover picks among them); a walk outside the map is dropped."""
        if not self.mask & M_MAP or loc not in self.camp.available:
            return False
        self.party_point = loc
        self.intro = False
        self.mask &= ~M_MAP                         # 0x445 -> 0x44c
        self.camp.enter(loc)
        self.post(MSG_ENTER)
        self.pump()
        return True

    # -- message handlers ------------------------------------------------------------------------------------------------------
    def _enter_location(self):
        """`0x468` (`0x487dea`): `GetCurrentLocation`; a mission starts (autosave 9999, mask bit 1), a town builds its scene (`0x48bbc0`, mask 0)."""
        loc = self.camp.location
        if loc is None:
            raise TownError("0x468 without a current location")
        kind, n = loc
        if kind == MISSION:
            self.town, self.view = None, "mission"
            self.mask |= M_MISSION
            self._emit("autosave", AUTOSAVE_MISSION)
            self._emit("mission", n)
        elif kind == TOWN and n in TOWNS:
            self.visit += 1
            self.stock = None
            self._scene()
        else:
            raise TownError("no screen for location %r" % (loc,))

    def _scene(self):
        """`0x42e` / the entry to a town (`0x48bbc0`): the scene of the current town, its music; the mask is 0 in a scene."""
        loc = self.camp.location
        if loc is None or loc[0] != TOWN or loc[1] not in TOWNS:
            raise TownError("no town to show a scene for: %r" % (loc,))
        self.town, self.view = loc[1], "scene"
        self.mask = 0
        self._emit("music", TOWNS[self.town].music)

    def _open_inn(self):
        """`0x42b` (`0x4877f9`): guard `mask == 0` (the scene is up); `EnterInn` + the units for the words run at every opening (`0x48b885`)."""
        if self.mask != 0 or self.view != "scene":
            return
        self.view = "inn"
        self.mask |= M_INN
        self._emit("inn", self.town)

    def _open_shop(self):
        """`0x42a`: same guard; `EnterShop` (always 0 in the campaign, town-shop 1) and the shop load."""
        if self.mask != 0 or self.view != "scene":
            return
        self.view = "shop"
        self.mask |= M_SHOP
        self._emit("shop", self.town)

    def close_window(self):
        """ESC / the Exit button of the inn or the shop (`0x49b69b`, `0x4b956e`): the window sends itself `0x445` (unload, `0x44c` posted); `0x42e` is
        posted only when the mask is **exactly** the window's own bit at the click.  A click with no inn / shop window open does nothing."""
        own = {"inn": M_INN, "shop": M_SHOP}.get(self.view)
        if own is None or not self.mask & own:
            return
        exact = self.mask == own
        self.post(MSG_WINDOW_CLOSED, own)
        if exact:
            self.post(MSG_SCENE)
        self.pump()

    def _window_closed(self, bit):
        """`0x44c` (`FUN_004891d8`): the window is removed, its bit cleared."""
        self.mask &= ~bit

    def leave_town(self):
        """The scene's leave click (`0x4cad5d` ...): posts `0x442` (autosave `game9998.sav`, "Abort mission and return to town") then `0x42d`.  The human
        scene leaves only when `Var(0x301) != 0`, else it plays the speech `plagatguard` and nothing else happens (`0x4cad3c`).  DECISION (the druid /
        Kaarg scenes: CONFIRMED, the druid click handler `0x4d06cc` posts `0x442` + `0x42d` for region 8 with no `Var` test, the Kaarg one `0x4d3058` likewise;
        their `Var` reads are `Var(0x300)` texts); a refused leave posts no `0x442` (`0x4cad85`: the speech only)."""
        if self.view != "scene" or self.mask != 0:
            return
        if self.town == 1 and not self.camp.get(LEAVE_GATE):
            self._emit("speech", "plagatguard")
            return
        self.post(MSG_AUTOSAVE, 1)
        self.post(MSG_LEAVE)
        self.pump()

    def _autosave(self, wparam=0):
        if wparam == 1:
            self._emit("autosave", AUTOSAVE_TOWN)

    def _leave(self):
        """`0x42d` (`0x487d34`): the party point is the town's, `ScenarioLeaveLocation` (a cutscene when its code is `>= 0`), town 1 starts the intro walk, the
        map opens."""
        loc = self.camp.location
        if loc is not None and loc[0] == TOWN:
            self.party_point = loc
            code = self.camp.leave()
            if code >= 0:
                self._emit("cutscene", code)
            if loc[1] == 1:
                self.intro = True
        self.open_map()

    # -- the end of a mission (0x41d) --------------------------------------------------------------------------------------------
    def mission_over(self, outcome):
        """`0x41d` (`0x486a68`; order CONFIRMED: mission time, `mask & 1` -> teardown `0x48da92` clears bit 1, carry-over, `SetPartyPoint` of the location the party stood on, leave, recruit, cutscene, ending test, town test) after the roster carry-over and `ScenarioLeaveLocation` (`engine.sim.campaign.complete` = `outcome`): the party point, the cutscene,
        then the ending (`Var(0x300) >= 0x78`), the head of the available list entered at once when no town is available (the map is never shown) or
        the map.  `main_menu` (defeat, left by the menu) ends the game."""
        self.mask &= ~M_MISSION
        self.town = None
        if outcome.kind == "main_menu":
            self.view = "menu"
            return
        if self.party_point is None and self.camp.available:
            self.party_point = self.camp.available[0]
        if outcome.cutscene >= 0:
            self._emit("cutscene", outcome.cutscene)
        if outcome.kind != "mission":
            self.intro = False                      # the map branch writes `window+0x1b0 := 0` (`0x486d91`)
        if outcome.kind == "ending":
            self.view = "ending"
        elif outcome.kind == "mission":
            self.send(MSG_ENTER)
        else:
            self.open_map()

    HANDLERS = {MSG_INN: _open_inn, MSG_SHOP: _open_shop, MSG_SCENE: _scene, MSG_WINDOW_CLOSED: _window_closed,
                MSG_AUTOSAVE: _autosave, MSG_LEAVE: _leave, MSG_ENTER: _enter_location}


# -- the transition table (town.md 2) -------------------------------------------------------------------------------------------------

EDGES = {
    ("map", "walk"): {"scene", "mission"},
    ("scene", "inn"): {"inn"},
    ("scene", "shop"): {"shop"},
    ("scene", "leave"): {"map"},
    ("inn", "close"): {"scene"},
    ("shop", "close"): {"scene"},
    ("mission", "over"): {"map", "scene", "mission", "ending", "menu"},
}
