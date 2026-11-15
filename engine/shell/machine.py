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
    "menu": {"newgame", "load", "cutlist", "quit"},
    "cutlist": {"menu", "cutlist"},                     # the Cut Scenes window: Cancel, or Ok -> the video -> the window again
    "newgame": {"menu", "chargen"},
    "chargen": {"newgame", "locations"},
    "locations": {"game", "menu", "town"},
    "town": {"inn", "shop", "locations", "menu", "town", "game"},            # `town -> town`: a game loaded from the scene's menu (L10d)
    "inn": {"town"},
    "shop": {"town"},
    "load": {"menu", "game", "town", "locations"},               # the main menu's Load window: back, or into the loaded game (a town save; a mission save is L10e / L10f)
    "game": {"menu", "locations", "game", "town"},                  # no town available after a mission: the head mission starts at once (`0x41d`)
    "cutscene": set(),                  # leaves for the `then` screen it was given (checked when it was entered)
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
    pcm: Callable = _nothing                # (samples int16 (n, 2) | None, rate): queue video audio; None only keeps the queue fed (a cutscene screen, every update)
    pcm_stop: Callable = _nothing           # (): cut the video audio
    video: bool = False                     # True: the backend can show a video (`Video` scene op + `pcm`); False = the old placeholders (`video skipped: ...` logged, tests)
    autosave: Callable = _nothing           # (slot number): the original's game%d.sav autosave (9999 mission start, 9998 leaving a town); saving is not built
    events: list = field(default_factory=list)


class Shell:
    def __init__(self, fs, size=(640, 480), settings=None, services=None, screens=None, slots=None, hall_file=None):
        from engine.audio.settings import Settings
        self.fs = as_fs(fs) if fs is not None else None
        self.size = size
        self.settings = settings or Settings()
        self.services = services or Services()
        self.current = None
        self.pending_cuts = []                  # chapter video codes the town core asked for (`ScenarioLeaveLocation`), played before the next screen
        self.history = []
        self.screens = {}
        self.params = {}
        self._town = None                       # the town core of `campaign` (`town_core`)
        self._worldmap = None                   # `engine.worldmap.WorldData` (the map's install data, `worldmap()`)
        import random
        self.rng = random.Random()              # the town scenes' dice (tests assign a seeded one)
        self._scene_globals = None              # `engine.townscene.Globals`: the exe's process-global scene counters (`scene_globals`)
        self.mouse = None                       # the last pointer position the shell saw (the map starts its hover from it)
        self.mission_session = None             # the running mission's session (set by the game screen: the mission menu's Save writes its world)
        self.view = (0, 0)                      # the mission camera at the last Save click (the backend sets it; `View/X`, `View/Y` of the client state)
        self.campaign = None                    # the running single-player campaign (`engine.campaign.CampaignGame`), made by `chargen`
        self.slots = slots                      # `engine.saveslots.SaveSlots` (the saved-game folder; None = no saves: the Load button stays disabled, Save writes nothing)
        self.hall_file = hall_file              # the settings-side `famehall.dat` (`engine.famehall`): read at start, written at exit; None = none (tests)
        self.hall = None                        # `famehall.Hall`, loaded lazily
        from engine import savegame
        self.mission_codec = savegame.MissionSaveCodec()    # mission-kind saves (`engine/missionsave.py`); None = "not supported" notice (tests)
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
            from .cutscene import Cutscene
            from .cutlist import CutList
            screens = (Startup, MainMenu, NewGame, CharGen, Locations, LoadGame, GameScreen, TownScene, Inn, Shop, Cutscene, CutList)
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
        if here != "cutscene" and target not in ("quit", "cutscene") and target not in GRAPH.get(here, ()):
            raise ShellError("no edge %s -> %s" % (here, target))
        if here != "cutscene" and target not in ("quit", "cutscene") and self.pending_cuts:
            codes, self.pending_cuts = self.pending_cuts, []
            if self.services.video:                 # the exe plays them before the next screen is built (`0x41d`, `0x42d`); the screen then goes on to `target`
                params = {"codes": codes, "then": target, "then_params": params}
                target = "cutscene"
        if target == "cutscene" and here != "cutscene" and params.get("then") not in GRAPH.get(here, ()) and params.get("then") != "quit":
            raise ShellError("no edge %s -> %s" % (here, params.get("then")))
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

    def load_hall(self):
        """The hall of fame as the exe loads it at start (`FUN_004a91d5`): the settings-side file, else the install's."""
        from engine import famehall
        if self.hall is None:
            self.hall = famehall.load(self.hall_file, self.fs)
        return self.hall

    def record_ending(self, campaign):
        """The campaign's end (`0x486ce2`, `FUN_004a8d28`): the main hero enters the hall of fame with the exe's score (`famehall.score`).  Returns the position or None (no hero)."""
        from engine import famehall
        entry = next((e for e in campaign.roster if getattr(e, "state", None) is not None), None) if campaign.roster else None
        if entry is None:
            return None
        st = entry.state
        score = famehall.score(getattr(st, "xp_total", 0), sum(campaign.camp.times), campaign.kills_monsters)
        return self.load_hall().add(getattr(st, "name", "") or "", score)

    def shutdown(self):
        """The exe's exit write (`FUN_004a90c9` in the client destructor): `famehall.dat` is rewritten at every shutdown, into the settings-side folder (never the install).  Returns the path or None."""
        from engine import famehall
        if self.hall_file is None:
            return None
        return famehall.write(self.load_hall(), self.hall_file)

    def close_window(self):
        """The window's close box: from anywhere to `quit`."""
        if not self.done:
            self.go("quit")

    def scene(self):
        return self.current.scene()

    # -- saved games (docs/engine/save-ui.md) ---------------------------------------------------------------------------------------
    def save_game(self, filename, description):
        """The Save dialog's Ok (`FUN_0048dc9f` for a town save): the campaign as `game%d.sav` in the slot folder.  Returns None or an error text (nothing written)."""
        if self.slots is None or self.campaign is None:
            return "No folder for saved games."
        try:
            data = self.campaign.to_save(description).pack()
            self.slots.write(filename, data)
        except OSError as e:
            return "%s: %s" % (filename, e.strerror or e)
        self.log("save: %s '%s'" % (filename, description))
        return None

    def description_text(self, number, fallback):
        """`patch.txt` line `number` (the auto-save descriptions: 0x37 "Restart last mission", 0x5f "Abort mission and return to town")."""
        if self.fs is not None:
            try:
                from .saveload import Texts
                return Texts(self.fs)("p", number) or fallback
            except Exception:                       # noqa: BLE001  a text table that cannot be read: the exe's English text
                pass
        return fallback

    def autosave(self, slot):
        """The core's `0x442` (saves.md 6, ui-layout 11.4): `services.autosave(slot)` is the observer hook; slot 9998 (the town scene's leave click) writes
        `game9998.sav` now, a town save (the campaign still stands in the town: loading it returns there); slot 9999 (the mission entry) is written by
        `mission_start_save` once the world exists."""
        self.services.autosave(slot)
        if slot == 9998 and self.slots is not None and self.campaign is not None:
            from engine import saveslots
            text = self.description_text(0x5F, "Abort mission and return to town")
            try:
                self.slots.write(saveslots.autosave_name(1), self.campaign.to_save(text).pack())
            except OSError as e:
                self.log("autosave %s: %s" % (slot, e))

    def mission_start_save(self, session):
        """`FUN_0048c8a3(0)` ends with `0x442(0)`: `game9999.sav`, "Restart last mission", the world as the mission starts (none after a load: `FUN_0048c8a3(1)`)."""
        if self.slots is None or self.mission_codec is None or getattr(session, "world", None) is None:
            return None
        from engine import saveslots
        text = self.description_text(0x37, "Restart last mission")
        try:
            self.slots.write(saveslots.autosave_name(0), self.mission_codec.save(session, text, campaign=self.campaign).pack())
        except OSError as e:
            self.log("autosave mission start: %s" % e)
            return str(e)
        self.log("autosave: game9999.sav '%s'" % text)
        return None

    def mission_state(self):
        """The `ClientState` of a mission save the UI contributes: the camera view (`Shell.view`)."""
        from allods2.formats import saves as S
        return S.ClientState(view_x=int(self.view[0]), view_y=int(self.view[1]))

    def save_mission(self, session, filename, description, state=None):
        """The mission menu's Save dialog (`FUN_0048dc9f` with the running mission): the world as `game%d.sav` in the slot folder.  Returns None or an error text."""
        if self.slots is None or self.mission_codec is None:
            return "No folder for saved games."
        try:
            self.slots.write(filename, self.mission_codec.save(session, description, state, campaign=self.campaign).pack())
        except OSError as e:
            return "%s: %s" % (filename, e.strerror or e)
        self.log("save: %s '%s'" % (filename, description))
        return None

    def resume_mission(self, params):
        """A mission-kind file was loaded (`0x419` -> `FUN_0048db37` -> `FUN_0048c8a3(1)`: the mission resumes, no new auto-save): the loaded campaign takes over and
        the game screen plays the loaded world.  Returns `("game", params)` for `Shell.apply`."""
        self.campaign = params.get("campaign") or self.campaign
        self._town = None
        self.log("load: mission %s, tick %d" % (params.get("mission"), params["loaded"].world.tick))
        return ("game", params)

    def resume(self, game):
        """The loaded campaign takes over (`0x419` -> `FUN_0048db37`, a town save: the server is rebuilt, `FUN_0041aaa5(0, 0)` = the town scene of the saved location, `0x42e`): a new
        town core, the scene of the saved town (the available list's saved position); a save with no town there (cannot be written by the menus) rests on the map.  Returns the screen name."""
        from engine import town as T
        self.campaign = game
        self._town = None
        core = self.town_core()
        loc = game.camp.location
        self.log("load: location %s, %d heroes" % (loc, len(game.roster)))
        if loc is not None and loc[0] == T.TOWN and loc[1] in T.TOWNS:
            core.send(T.MSG_ENTER)
        else:
            game.camp.location = None
            core.open_map()
        self.drain_town()
        return "town" if core.view == "scene" else "locations"

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
            if kind == "cutscene":
                self.pending_cuts.append(ev[1])
            elif kind == "autosave":
                self.autosave(ev[1])
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
