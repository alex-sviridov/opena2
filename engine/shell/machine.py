"""The shell state machine (docs/engine/shell.md 4): one current screen, a fixed graph of allowed moves, enter / exit on every move.

`GRAPH[a]` = the screens `a` may go to.  Every screen can also go to `quit` (the original's WM_CLOSE, `FUN_004a81a3` posts it directly from the
menu and the window's close box reaches it from everywhere).  A move outside the graph raises `ShellError`: the graph is the spec, a screen that
wants another edge is a bug in the graph, not a place for a shortcut.  `Shell.history` records every visited screen (tests)."""

from dataclasses import dataclass, field
from typing import Callable

from allods2.common import as_fs

from engine.ui import story

GRAPH = {
    "startup": {"menu"},
    "menu": {"newgame", "load", "quit"},
    "newgame": {"menu", "chargen"},
    "chargen": {"newgame", "locations"},
    "locations": {"game", "menu", "town"},
    "town": {"inn", "shop", "locations", "menu"},
    "inn": {"town"},
    "shop": {"town"},
    "load": {"menu", "game"},
    "game": {"menu", "locations"},
    "quit": set(),
}
START = "startup"


class ShellError(Exception):
    pass


def _nothing(*a, **k):
    return None


@dataclass
class Services:
    """What the shell needs from the outside world (the backend fills it in; tests pass fakes).  Every field has a harmless default."""
    sound: Callable = _nothing              # (path_or_id): a UI sound
    speech: Callable = _nothing             # (path): a voice line (the speech bus; a town NPC's page); the game path of an existing file
    stop: Callable = _nothing               # (path): cut the UI sound `path` when it still plays (a town scene's slot stop)
    loop: Callable = _nothing               # (path or None): the one looping UI sound (a town scene's entry loop); None stops it
    music: Callable = _nothing              # (playlist name)
    log: Callable = _nothing                # (line)
    start_game: Callable = None             # (params dict) -> a session object with `.world` and `.run() -> reason`; None = no game possible
    apply_settings: Callable = _nothing     # (Settings): the values take effect now (the sound sliders are live)
    save_settings: Callable = _nothing      # (Settings): persist (and apply)
    autosave: Callable = _nothing           # (slot number): the original's game%d.sav autosave (9999 mission start, 9998 leaving a town); saving is not built
    events: list = field(default_factory=list)


class Shell:
    def __init__(self, fs, size=(640, 480), settings=None, services=None, screens=None):
        from engine.audio.settings import Settings
        self.fs = as_fs(fs) if fs is not None else None
        self.size = size
        self.settings = settings or Settings()
        self.services = services or Services()
        self.current = None
        self.history = []
        self.screens = {}
        self.params = {}
        self._town = None                       # the town core of `campaign` (`town_core`)
        self._worldmap = None                   # `engine.worldmap.WorldData` (the map's install data, `worldmap()`)
        import random
        self.rng = random.Random()              # the town scenes' dice (tests assign a seeded one)
        self._scene_globals = None              # `engine.townscene.Globals`: the exe's process-global scene counters (`scene_globals`)
        self.mouse = None                       # the last pointer position the shell saw (the map starts its hover from it)
        self.campaign = None                    # the running single-player campaign (`engine.campaign.CampaignGame`), made by `chargen`
        if screens is None:
            from .chargen import CharGen
            from .game import GameScreen
            from .loadgame import LoadGame
            from .locations import Locations
            from .mainmenu import MainMenu
            from .newgame import NewGame
            from .startup import Startup
            from .inn import Inn
            from .shop import Shop
            from .town import TownScene
            screens = (Startup, MainMenu, NewGame, CharGen, Locations, LoadGame, GameScreen, TownScene, Inn, Shop)
        for cls in screens:
            self.screens[cls.name] = cls(self)

    # -- state ---------------------------------------------------------------------------------------------------------------------
    @property
    def name(self):
        return self.current.name if self.current is not None else None

    @property
    def done(self):
        return self.name == "quit"

    def start(self, first=START, **params):
        """Enter the first screen (any screen: `python -m engine play` style entries start elsewhere)."""
        self._enter(first, params)

    def go(self, target, **params):
        """Leave the current screen for `target`; `ShellError` when the graph has no such edge."""
        here = self.name
        if target not in GRAPH:
            raise ShellError("unknown screen %r" % target)
        if target != "quit" and target not in GRAPH.get(here, ()):
            raise ShellError("no edge %s -> %s" % (here, target))
        self.current.exit()
        self._enter(target, params)

    def _enter(self, name, params):
        self.current = self.screens.get(name) or _Quit(self)
        self.params = params
        self.history.append(name)
        if self.current.music:
            self.services.music(self.current.music)
        self.current.enter(**params)

    def apply(self, result):
        """Follow a screen's answer: None, a screen name or `(name, params)`."""
        if result is None:
            return
        name, params = result if isinstance(result, tuple) else (result, {})
        self.go(name, **params)

    # -- input / time --------------------------------------------------------------------------------------------------------------
    def handle(self, ev):
        """Feed one input event to the current screen and follow the move it asks for."""
        if hasattr(ev, "x") and hasattr(ev, "y"):
            self.mouse = (ev.x, ev.y)
        if self.current is not None and not self.done:
            self.apply(self.current.event(ev))

    def update(self, dt_ms):
        if self.current is not None and not self.done:
            self.apply(self.current.update(dt_ms))

    def close_window(self):
        """The window's close box: from anywhere to `quit`."""
        if not self.done:
            self.go("quit")

    def scene(self):
        return self.current.scene()

    # -- the town (docs/engine/town.md) ---------------------------------------------------------------------------------------------
    def town_core(self):
        """The `engine.town.TownCore` of the running campaign (made on first use; a new campaign gets a new core)."""
        from engine.town import TownCore
        if self._town is None or self._town.camp is not self.campaign.camp:
            self._town = TownCore(self.campaign.camp)
        return self._town

    @property
    def scene_globals(self):
        if self._scene_globals is None:
            from engine.townscene import Globals
            self._scene_globals = Globals()
        return self._scene_globals

    def worldmap(self):
        """The map's data (`engine.worldmap.WorldData`: location points from `Scenario.dll`, path graphs, texts), loaded on first use; tests may assign `_worldmap`."""
        if self._worldmap is None:
            from engine.worldmap import WorldData
            self._worldmap = WorldData.load(self.fs)
        return self._worldmap

    def drain_town(self):
        """Turn the core's events into services (autosave slot, playlist, speech, cutscene note); returns them."""
        events = self.town_core().take_events()
        for ev in events:
            kind = ev[0]
            if kind == "autosave":
                self.services.autosave(ev[1])
            elif kind == "music":
                self.services.music(ev[1])
            elif kind == "speech":
                self.speak_town(ev[1])
            self.log("town: " + " ".join(str(x) for x in ev))
        return events

    def speak_town(self, key):
        """Voice the first page of the `town.txt` section `#<key>` (an NPC click / the human gate guard; `FUN_0041d15e` opens the story window whose page 1 `FUN_004dc84c` voices):
        the file `townscene.town_voice` names for the main hero's class, played on the speech bus if it exists in the install.  The window and its text are not built (the Ok pages 2.. are
        not voiced).  Returns the game path played, or None."""
        from engine import townscene as TS
        from allods2.text import decode_text
        if self.fs is None:
            return None
        try:
            text = decode_text(self.fs.read(TS.TOWN_TEXT))
        except (KeyError, OSError):
            return None
        camp = self.campaign
        flags = story.hero_flags(camp.is_female, camp.is_mage) if camp is not None else 0
        path = TS.town_voice(text, key, flags, 1, self.fs.exists)
        if path:
            self.services.speech(path)
        self.log("town: speech %s -> %s" % (key, path))
        return path

    def town_screen(self):
        """The screen the core's `view` asks for, `(name, params)` or None to stay (screens return this from `event`)."""
        self.drain_town()
        view = self.town_core().view
        want = {"scene": "town", "inn": "inn", "shop": "shop", "map": "locations", "menu": "menu"}.get(view)
        return None if want is None or want == self.name else want

    # -- services shortcuts (screens use these) ------------------------------------------------------------------------------------
    def play(self, sound):
        self.services.sound(sound)

    def stop(self, sound):
        self.services.stop(sound)

    def log(self, line):
        self.services.log(line)


class _Quit:
    name = "quit"
    music = None
    driven = False

    def __init__(self, shell):
        self.shell = shell

    def enter(self, **params):
        pass

    def exit(self):
        pass

    def event(self, ev):
        return None

    def update(self, dt):
        return None

    def scene(self):
        from .scene import Scene
        return Scene([], cursor=False)
