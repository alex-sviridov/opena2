"""The shell state machine (docs/engine/shell.md 4): one current screen, a fixed graph of allowed moves, enter / exit on every move.

`GRAPH[a]` = the screens `a` may go to.  Every screen can also go to `quit` (the original's WM_CLOSE, `FUN_004a81a3` posts it directly from the
menu and the window's close box reaches it from everywhere).  A move outside the graph raises `ShellError`: the graph is the spec, a screen that
wants another edge is a bug in the graph, not a place for a shortcut.  `Shell.history` records every visited screen (tests)."""

from dataclasses import dataclass, field
from typing import Callable

from allods2.common import as_fs

GRAPH = {
    "startup": {"menu"},
    "menu": {"options", "newgame", "load", "quit"},
    "options": {"menu"},
    "newgame": {"menu", "game"},
    "load": {"menu", "game"},
    "game": {"menu"},
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
    music: Callable = _nothing              # (playlist name)
    log: Callable = _nothing                # (line)
    start_game: Callable = None             # (params dict) -> a session object with `.world` and `.run() -> reason`; None = no game possible
    apply_settings: Callable = _nothing     # (Settings): the values take effect now (the sound sliders are live)
    save_settings: Callable = _nothing      # (Settings): persist (and apply)
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
        if screens is None:
            from .game import GameScreen
            from .loadgame import LoadGame
            from .mainmenu import MainMenu
            from .newgame import NewGame
            from .options import Options
            from .startup import Startup
            screens = (Startup, MainMenu, Options, NewGame, LoadGame, GameScreen)
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

    # -- services shortcuts (screens use these) ------------------------------------------------------------------------------------
    def play(self, sound):
        self.services.sound(sound)

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
