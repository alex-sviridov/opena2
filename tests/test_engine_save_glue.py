"""L10f: the pygame backend glue of save / load, run for real but headless (SDL dummy driver, the real `python -m engine` shell loop with scripted pygame events): main menu LOAD
(a refused file = a notice, a town save, an original-style mission save), the mission's ESC menu Save and Load windows over the frozen frame (`fileview.py`, `window.py`, `PlaySession`), a
refused file in the mission's Load window (notice, the game goes on), a town save and load through the scene menu, and `famehall.dat` written at exit into the settings folder.
Needs the install."""

import os
import time

import pytest

pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from allods2.formats import saves as S  # noqa: E402
from engine import missionsave as M  # noqa: E402
from engine.campaign import CampaignGame, HeroChoice  # noqa: E402
from helpers import GFS, needs_data  # noqa: E402

pytestmark = needs_data


def ev(kind, **kw):
    import pygame
    return pygame.event.Event(kind, **kw)


def click(x, y):
    import pygame
    return [ev(pygame.MOUSEMOTION, pos=(x, y), rel=(0, 0), buttons=(0, 0, 0)), ev(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=1), ev(pygame.MOUSEBUTTONUP, pos=(x, y), button=1)]


def key(k, ch=""):
    import pygame
    return [ev(pygame.KEYDOWN, key=k, mod=0, unicode=ch)]


def centre(r):
    r = (r.x, r.y, r.w, r.h) if hasattr(r, "w") else r
    return r[0] + r[2] // 2, r[1] + r[3] // 2


def test_the_real_shell_loop_saves_and_loads_headless(tmp_path, monkeypatch):
    import pygame
    from engine import __main__ as E
    from engine.shell import Shell
    from engine.shell.mainmenu import BUTTONS

    monkeypatch.setenv("ALLODS2_SETTINGS", str(tmp_path / "cfg" / "settings.json"))
    saves = tmp_path / "cfg" / "saves"
    saves.mkdir(parents=True)
    g = CampaignGame(GFS, seed=4)
    g.new_game(HeroChoice("MF"))
    from engine.sim import campaign as C
    g.camp.available = [(C.TOWN, 2), (C.MISSION, 10)]
    g.camp.location = (C.TOWN, 2)                                         # saved from a town scene
    town_data = g.to_save("town save").pack()
    world, _ = g.start_mission(10)
    save = M.world_to_save(world, g, description="orig-like mission")
    st = save.tail.state
    st.engine = b""                                                       # what the original writes: no engine extension, no RNG marker is needed
    original = S.SaveGame(save.stream, save.tail.with_state(st)).pack()
    now = time.time()
    for name, data, age in (("game0001.sav", town_data, 300), ("game0002.sav", original, 200), ("game0003.sav", original[:60] + b"\xff" * 400 + original[460:], 100)):
        (saves / name).write_bytes(data)
        os.utime(saves / name, (now - age, now - age))

    holder = {}
    real_init = Shell.__init__

    def init(self, *a, **k):
        real_init(self, *a, **k)
        holder["shell"] = self
    monkeypatch.setattr(Shell, "__init__", init)
    log = []

    def sh():
        return holder["shell"]

    def sim():
        return sh().mission_session.play.rec.sim

    def script():
        s = None
        for _ in range(900):
            s = holder.get("shell")
            if s is not None and s.name == "menu":
                break
            yield []
        assert s.name == "menu"
        yield []
        x, y, w, h = BUTTONS[4][1]
        yield click(x + w // 2, y + h // 2)                                   # LOAD GAME
        assert s.name == "load", s.name
        yield key(pygame.K_RETURN)                                            # the newest file is the damaged one: a notice, the window stays
        d = s.current.dialog
        assert s.name == "load" and d.box is not None and "Invalid save file" in d.box.message, getattr(d.box, "message", None)
        log.append(d.box.message)
        yield key(pygame.K_RETURN)                                            # close the notice
        assert d.box is None
        yield key(pygame.K_DOWN)
        yield key(pygame.K_RETURN)                                            # game0002: the original-style mission save
        for _ in range(900):                                                  # the real game loop starts
            if s.name == "game" and getattr(s.mission_session, "play", None) is not None and getattr(s.mission_session.play.rec, "sim", None) is not None:
                break
            yield []
        assert s.name == "game" and sim().world.tick == 0
        for _ in range(30):
            yield []
        for _ in range(6):                                                    # the mission's own story window (script message at tick 0) first
            if not sim().ui.frozen:
                break
            yield key(pygame.K_ESCAPE)
            yield []
        assert not sim().ui.frozen
        first_world = sim().world
        yield key(pygame.K_ESCAPE)
        yield []
        yield []
        top = sim().ui.modals.top
        assert top is not None and top.kind == "menu" and top.buttons[0].enabled and top.buttons[1].enabled
        yield click(*centre(top.buttons[0].rect))                            # Save Game
        yield []
        for ch in "mid game":
            yield key(ord(ch), ch)
        yield key(pygame.K_RETURN)
        for _ in range(5):
            yield []
        assert any(x.description == "mid game" for x in s.slots.scan()), [x.description for x in s.slots.scan()]
        assert not sim().ui.frozen
        log.append("saved")
        yield key(pygame.K_ESCAPE)
        yield []
        yield []
        top = sim().ui.modals.top
        yield click(*centre(top.buttons[1].rect))                            # Load Game: rows = mid game (newest), the damaged file, the original, the town save
        yield []
        yield key(pygame.K_DOWN)
        yield key(pygame.K_RETURN)                                            # the damaged file: a notice over the frozen game, nothing replaced
        for _ in range(3):
            yield []
        assert s.mission_session.play.rec.sim.world is first_world and s.name == "game"
        yield key(pygame.K_RETURN)                                            # close the notice
        yield key(pygame.K_UP)
        yield key(pygame.K_RETURN)                                            # mid game: the loop ends with "load" and the game screen plays the new world
        for _ in range(900):
            if s.name == "game" and getattr(s.mission_session.play.rec, "sim", None) is not None and s.mission_session.play.rec.sim.world is not first_world:
                break
            yield []
        assert s.mission_session.play.rec.sim.world is not first_world
        log.append("reloaded")
        for _ in range(20):
            yield []
        yield key(pygame.K_ESCAPE)
        yield []
        yield []                                                              # End Quest -> Exit to Main Menu
        top = sim().ui.modals.top
        yield click(*centre(top.buttons[5].rect))
        top = sim().ui.modals.top
        yield click(*centre(top.buttons[1].rect))
        for _ in range(900):
            if s.name == "menu":
                break
            yield []
        assert s.name == "menu"
        yield click(x + w // 2, y + h // 2)
        yield key(pygame.K_DOWN)
        yield key(pygame.K_DOWN)
        yield key(pygame.K_DOWN)                                              # the town save (oldest)
        yield key(pygame.K_RETURN)
        assert s.name == "town", s.name
        for _ in range(5):
            yield []
        yield key(pygame.K_ESCAPE)                                            # scene menu -> Save
        yield click(*centre(s.current.menu.rects()[0]))
        for ch in "in town":
            yield key(ord(ch), ch)
        yield key(pygame.K_RETURN)
        for _ in range(3):
            yield []
        assert any(x.description == "in town" for x in s.slots.scan())
        log.append("town saved")
        yield [ev(pygame.QUIT)]
        for _ in range(5):
            yield []

    gen = script()
    state = {"n": 0}

    def fake_get(*a, **k):
        state["n"] += 1
        try:
            return next(gen)
        except StopIteration:
            return [ev(pygame.QUIT)]
    monkeypatch.setattr(pygame.event, "get", fake_get)
    rc = E.main(["shell", "--start", "menu", "--no-audio", "--out", str(tmp_path / "sessions"), "--size", "640x480"])
    assert rc == 0 and log == [log[0], "saved", "reloaded", "town saved"] and "Invalid save file" in log[0]
    assert (tmp_path / "cfg" / "famehall.dat").is_file()                      # written at exit, settings side
