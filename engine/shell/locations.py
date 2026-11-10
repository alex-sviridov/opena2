"""Between the missions (L2 stand-in for the town / world map, docs/engine/shell.md 3.4): a plain dialog with the party's heroes and one button per available
mission of the campaign (`CampaignGame.camp.available`, unlock order), plus Main Menu.  The original shows its town and the world map here; those are the `town`
step (L3 / L4), this screen only lets the player choose the next mission, which is all the world map does for the campaign.

DECISIONs: all texts are literals (the original's town strings belong to the town spec); a mission is labelled "Mission N" with the map's own name when the map
header can be read; a dialog text button acts on the **release** over the same button (the common dialog's rule, ui-layout 11.4); ESC = Main Menu, Enter = the first
mission; the dialog is centred on the screen.  The screen owns no World."""

from allods2.formats import Map

from .events import Key, Move, Press, Release
from .scene import Button, Frame, Scene, Text
from .screen import Screen

W, H = 480, 392                         # the frame including the 8 px drop shadow
PAD, ROW, GAP = 40, 24, 6
MAX_ROWS = 8
MISSION = 1                             # the location type of a mission in Scenario.dll's available list (`sim.campaign.MISSION`; the shell never imports the sim)
MENU_LABEL = "Main Menu"
CLICK = "sfx/chrgen/ok.wav"


def mission_label(fs, n):
    """"Mission N: <map name>" (the name of the map file's header), "Mission N" when it cannot be read."""
    try:
        from allods2.cli import resolve_map
        path, mfs = resolve_map(str(n), fs)
        name = Map.load(path, mfs).header.name.strip()
    except Exception:                       # noqa: BLE001  a label is decoration, never a reason to fail
        name = ""
    return "Mission %d: %s" % (n, name) if name else "Mission %d" % n


class Locations(Screen):
    name = "locations"
    music = "chrgen"

    def __init__(self, shell):
        super().__init__(shell)
        self.rows = []                          # [(button label, mission number or None for Main Menu)]
        self.hot = self.pressed = None

    @property
    def campaign(self):
        return self.shell.campaign

    def enter(self, **params):
        camp = self.campaign
        self.missions = [n for kind, n in camp.camp.available if kind == MISSION][:MAX_ROWS]
        self.labels = [mission_label(self.shell.fs, n) for n in self.missions]
        self.party = [l.split(":", 1)[-1] for l in camp.summary().split("; ")] if camp.roster else []      # "0x15:Aldor L1 ..." -> "Aldor L1 ..."
        self.hot = self.pressed = None

    # -- geometry (screen coordinates) ---------------------------------------------------------------------------------------------
    def frame_at(self):
        ox, oy = self.origin
        return ox + (640 - W) // 2, oy + (480 - H) // 2

    def buttons(self):
        """`[(x, y, w, h, label, mission)]`: the mission buttons, then Main Menu at the bottom."""
        fx, fy = self.frame_at()
        top = fy + 130
        out = [(fx + PAD, top + i * (ROW + GAP), W - 8 - 2 * PAD, ROW, label, n) for i, (label, n) in enumerate(zip(self.labels, self.missions))]
        out.append((fx + PAD, fy + H - 8 - PAD - ROW, W - 8 - 2 * PAD, ROW, MENU_LABEL, None))
        return out

    def _at(self, x, y):
        for i, (bx, by, bw, bh, _, _) in enumerate(self.buttons()):
            if bx <= x < bx + bw and by <= y < by + bh:
                return i
        return None

    # -- input ---------------------------------------------------------------------------------------------------------------------
    def _go(self, mission):
        self.shell.play(CLICK)
        if mission is None:
            return "menu"
        return "game", {"campaign": self.campaign, "mission": mission}

    def event(self, ev):
        if isinstance(ev, Move):
            self.hot = self._at(ev.x, ev.y)
        elif isinstance(ev, Press) and ev.button == 1:
            self.hot = self.pressed = self._at(ev.x, ev.y)
        elif isinstance(ev, Release) and ev.button == 1:
            hit, down, self.pressed = self._at(ev.x, ev.y), self.pressed, None
            self.hot = hit
            if hit is not None and hit == down:                       # the release over the pressed button acts
                return self._go(self.buttons()[hit][5])
        elif isinstance(ev, Key) and not ev.ctrl:
            if ev.name == "escape":
                return self._go(None)
            if ev.name == "return" and self.missions:
                return self._go(self.missions[0])
        return None

    def scene(self):
        fx, fy = self.frame_at()
        camp = self.campaign
        ops = [Frame(fx, fy, W, H),
               Text("Campaign - chapter %d" % camp.camp.get(0x300), fx + PAD, fy + 24, 2, "normal", 0, 1),
               Text("Party", fx + PAD, fy + 46, 2, "normal", 0, 1)]
        for i, line in enumerate(self.party[:4]):
            ops.append(Text(line, fx + PAD + 8, fy + 58 + 16 * i, 1, "normal", 0, 1))
        ops.append(Text("Gold: %d" % camp.gold, fx + PAD + 8, fy + 58 + 16 * min(4, len(self.party)), 1, "normal", 0, 1))
        ops.append(Text("Choose the next mission" if self.missions else "No mission is available", fx + PAD, fy + 110, 2, "normal", 0, 1))
        for i, (x, y, w, h, label, _) in enumerate(self.buttons()):
            ops.append(Button(x, y, w, h, label, True, self.hot == i, self.pressed == i))
        return Scene(ops)
