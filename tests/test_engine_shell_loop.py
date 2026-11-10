"""The shell's window loop end to end, headless (SDL dummy drivers): scripted pygame events walk menu -> new game -> a real mission (the in-game
screen's loop) -> ESC menu -> End Quest -> Exit to Main Menu -> Exit.  Proves that the display, the fonts and the loop survive the hand-over both ways,
and that the session of the game is written."""

import json
import os

import pytest

from helpers import GFS, needs_graphics

pygame = pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from engine.ui import Layout  # noqa: E402
from engine.ui.widgets import button_rect, widget_rect  # noqa: E402
from shell_scenarios import button_centre, make_shell, mask_centre  # noqa: E402

pytestmark = needs_graphics


def mouse(kind, pos, button=1):
    t = {"move": pygame.MOUSEMOTION, "down": pygame.MOUSEBUTTONDOWN, "up": pygame.MOUSEBUTTONUP}[kind]
    if kind == "move":
        return pygame.event.Event(t, pos=pos, rel=(0, 0), buttons=(0, 0, 0))
    return pygame.event.Event(t, pos=pos, button=button)


def click(pos):
    return [mouse("move", pos), mouse("down", pos), mouse("up", pos)]


def key(k):
    return [pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="")]


def test_script_through_a_real_mission_and_back(tmp_path, monkeypatch):
    from engine import __main__ as cli
    from engine.audio import settings as S
    monkeypatch.setenv(S.ENV, str(tmp_path / "settings.json"))
    sh, _ = make_shell(GFS)
    sh.start("menu")
    new_game = button_centre(sh, 0)
    exit_btn = button_centre(sh, 7)
    sh.go("newgame")
    mask = sh.current.mask
    hero, ok = mask_centre(sh, mask, 80), mask_centre(sh, mask, 180)
    lay = Layout.for_size(640, 480)
    menu = widget_rect(lay, "menu.frame")
    end_quest, endq = button_rect(menu, 5), widget_rect(lay, "endquest.frame")
    exit_to_menu = button_rect(endq, 1)
    centre = lambda r: (r.x + r.w // 2, r.y + r.h // 2)
    script = [[], click(new_game), click(hero), click(ok)]       # frames 0..3 of the shell; the game's loop takes over after the OK
    script += [[]] * 3 + [key(pygame.K_ESCAPE), [], click(centre(end_quest)), [], click(centre(exit_to_menu)), [], click(exit_btn)]
    feed = iter(script)

    fallback = []

    def get():
        batch = next(feed, None)
        if batch is None:
            fallback.append(1)                                     # the script ran out: the window "closes"
            return [pygame.event.Event(pygame.QUIT)]
        return batch
    monkeypatch.setattr(pygame.event, "get", get)
    p = cli.build_parser()
    a = p.parse_args(["shell", "--no-audio", "--start", "menu", "--out", str(tmp_path / "session"), "--seed", "7", "--speed", "4"])
    seen = []
    orig = cli.PlaySession.run

    def run(self):
        seen.append(self.world is not None and self.world.name)
        return orig(self)
    monkeypatch.setattr(cli.PlaySession, "run", run)
    from engine.shell import Shell
    went, go = [], Shell.go
    monkeypatch.setattr(Shell, "go", lambda self, t, **k: (went.append(t), go(self, t, **k))[1])
    assert cli.shell_cmd(a, p) == 0
    assert went == ["newgame", "game", "menu", "quit"] and fallback == []     # left through the in-game menu and the Exit button, not by closing the window
    assert seen and seen[0]                                        # the world existed while the game screen ran
    final = json.load(open(tmp_path / "session" / "final.json"))
    assert final["result"] is None or final["result"] in ("won", "lost") or "tick" in final
    assert os.path.exists(tmp_path / "session" / "session.json")
