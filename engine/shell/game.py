"""The in-game screen: the only screen that owns a `World` (docs/engine/shell.md 4).  `enter` asks the backend's `services.start_game` for a
session (that builds the World and the simulation); the backend then hands its loop to `session.run()`, which plays until the mission ends and
returns why: `menu` (End Quest -> Exit to Main Menu, victory, defeat) or `quit` (Exit to Windows, the window's close box).  `exit` drops the
session and with it the World: menus never see one."""

from .scene import Scene
from .screen import Screen

BACK_TO_MENU = {"menu", "victory", "defeat", "complete"}


class GameScreen(Screen):
    name = "game"
    driven = True
    music = None                    # the mission sets its own playlist (`Audio.start_mission`)

    def __init__(self, shell):
        super().__init__(shell)
        self.session = None

    @property
    def world(self):
        return self.session.world if self.session is not None else None

    def enter(self, **params):
        start = self.shell.services.start_game
        if start is None:
            raise RuntimeError("no start_game service: the shell cannot start a game")
        self.session = start(params)

    def exit(self):
        self.session = None

    def run(self):
        """Play the session to its end; the next screen's name."""
        reason = self.session.run()
        return "menu" if reason in BACK_TO_MENU else "quit"

    def scene(self):
        return Scene([], cursor=False)
