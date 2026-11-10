"""The in-game screen: the only screen that owns a `World` (docs/engine/shell.md 4).  `enter` asks the backend's `services.start_game` for a
session (that builds the World and the simulation); the backend then hands its loop to `session.run()`, which plays until the mission ends and
returns why: `menu` (End Quest -> Exit to Main Menu, victory, defeat) or `quit` (Exit to Windows, the window's close box).  `exit` drops the
session and with it the World: menus never see one.

A **campaign mission** (`params["campaign"]` = the shell's `CampaignGame`, `params["mission"]`): the session is made from `CampaignGame.start_mission`; a
victory ends it with `leave_mission(world, "won")` (carry-over, Scenario.dll's completion, recruits, the town stand-in) and goes on to the `locations`
screen; a defeat or the menu is the main menu (`leave_mission` for anything else: no carry-over, as the original's `0x41e` / `0x431` end the game);
the last mission's ending also goes to the menu (the credits are not built)."""

from .scene import Scene
from .screen import Screen

BACK_TO_MENU = {"menu", "victory", "defeat", "complete"}
CAMPAIGN_ENDINGS = ("ending",)          # `sim.campaign.Outcome.kind` of the last mission: the credits are not built, the shell goes to the menu


class GameScreen(Screen):
    name = "game"
    driven = True
    music = None                    # the mission sets its own playlist (`Audio.start_mission`)

    def __init__(self, shell):
        super().__init__(shell)
        self.session = None
        self.campaign = None

    @property
    def world(self):
        return self.session.world if self.session is not None else None

    def enter(self, **params):
        start = self.shell.services.start_game
        if start is None:
            raise RuntimeError("no start_game service: the shell cannot start a game")
        self.campaign = params.get("campaign")
        self.session = start(params)

    def exit(self):
        self.session = None
        self.campaign = None

    def run(self):
        """Play the session to its end; the next screen's name."""
        reason = self.session.run()
        if self.campaign is None or reason not in BACK_TO_MENU:
            return "menu" if reason in BACK_TO_MENU else "quit"
        out = self.campaign.leave_mission(self.session.world, "won" if reason == "victory" else reason)
        self.shell.log("mission %s %s -> %s" % (self.campaign.mission if reason != "victory" else "done", reason, out.kind))
        return "locations" if reason == "victory" and out.kind not in CAMPAIGN_ENDINGS else "menu"

    def scene(self):
        return Scene([], cursor=False)
