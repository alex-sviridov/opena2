"""The shell (docs/engine/shell.md): the state machine follows the screen graph from scripted input, the main menu behaves like the original's
(hit mask, hover / held / disabled, click on release, sound on press), the options persist, no World exists before a game starts, a golden
screenshot per screen.  Needs the install except the graph tests."""

import importlib.util
import json
import os

import numpy as np
import pytest

from helpers import GFS, needs_graphics

pygame = pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from engine.shell import GRAPH, Key, Move, Press, Release, Shell, ShellError, Services  # noqa: E402
from engine.shell.mainmenu import BUTTONS, DISABLED, mask_index  # noqa: E402
from engine.shell.screen import Screen  # noqa: E402
from shell_scenarios import Recorder, button_centre, click, make_shell, mask_centre, to_menu  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# -- the graph (no install) -------------------------------------------------------------------------------------------------------------

class Dummy(Screen):
    def __init__(self, shell, name):
        super().__init__(shell)
        self.name = name
        self.log = []

    def enter(self, **p):
        self.log.append(("enter", p))

    def exit(self):
        self.log.append("exit")

    def scene(self):
        raise AssertionError


def dummy_shell():
    sh = Shell(None, screens=())
    for n in GRAPH:
        if n != "quit":
            sh.screens[n] = Dummy(sh, n)
    return sh


def test_graph_edges_stay_inside_the_graph():
    for a, targets in GRAPH.items():
        assert a in GRAPH and targets <= set(GRAPH)
    assert GRAPH["startup"] == {"menu"} and GRAPH["menu"] == {"options", "newgame", "load", "quit"}


def test_every_legal_edge_works_and_every_other_raises():
    for a in GRAPH:
        if a == "quit":
            continue
        for b in GRAPH:
            sh = dummy_shell()
            sh.start(a)
            if b in GRAPH[a] or b == "quit":
                sh.go(b)
                assert sh.name == b
                assert sh.screens[a].log[-1] == "exit"
            else:
                with pytest.raises(ShellError):
                    sh.go(b)
                assert sh.name == a                          # a refused move changes nothing


def test_close_window_quits_from_every_screen():
    for a in GRAPH:
        if a == "quit":
            continue
        sh = dummy_shell()
        sh.start(a)
        sh.close_window()
        assert sh.done and sh.history[-1] == "quit"


def test_params_reach_enter():
    sh = dummy_shell()
    sh.start("newgame")
    sh.go("game", map="10", difficulty=2)
    assert sh.screens["game"].log == [("enter", {"map": "10", "difficulty": 2})]


# -- the main menu -----------------------------------------------------------------------------------------------------------------------

def test_mask_value_to_button():
    assert [mask_index(0x80 + 0x10 * n) for n in range(8)] == list(range(8))
    assert mask_index(0) == mask_index(0x10) == mask_index(0x1E) == mask_index(0x85) == mask_index(0x100) == -1


@needs_graphics
def test_startup_logs_the_skipped_videos_then_shows_the_menu():
    sh, rec = make_shell(GFS)
    sh.start()
    assert sh.name == "startup" and rec.lines == []
    sh.update(16)
    assert sh.name == "menu"
    assert rec.lines == ["video skipped: video/logos/publisher.smk", "video skipped: video/logos/nival.smk", "video skipped: video/intro/01.smk"]
    assert rec.music == ["menu"]


@needs_graphics
def test_script_menu_new_game_cancel_options_exit_follows_the_graph():
    sh, rec = make_shell(GFS)
    to_menu(sh)
    click(sh, button_centre(sh, 0))
    assert sh.name == "newgame" and rec.music[-1] == "chrgen"
    click(sh, mask_centre(sh, sh.current.mask, 160))                 # Cancel
    assert sh.name == "menu" and rec.music[-1] == "menu"
    sh.handle(Key("o"))
    assert sh.name == "options"
    sh.handle(Key("escape"))
    assert sh.name == "menu"
    click(sh, button_centre(sh, 7))
    assert sh.done
    assert sh.history == ["startup", "menu", "newgame", "menu", "options", "menu", "quit"]
    for a, b in zip(sh.history, sh.history[1:]):
        assert b in GRAPH[a] or b == "quit"


@needs_graphics
def test_disabled_buttons_do_nothing_and_make_no_sound():
    sh, rec = make_shell(GFS)
    to_menu(sh)
    for n in range(8):
        if (DISABLED >> n) & 1:
            click(sh, button_centre(sh, n))
            assert sh.name == "menu", BUTTONS[n]
    assert rec.sounds == []
    sh.handle(Move(*button_centre(sh, 4)))
    ops = [o.path for o in sh.scene().ops]
    assert not any("button5" in p for p in ops)                       # no highlight on a disabled button
    assert any(p.endswith("text5.bmp") for p in ops)                  # the caption still follows the pointer


@needs_graphics
def test_hover_held_and_click_on_release():
    sh, rec = make_shell(GFS)
    to_menu(sh)
    pos, other = button_centre(sh, 0), button_centre(sh, 7)
    sh.handle(Move(*pos))
    names = [o.path.rsplit("/", 1)[1] for o in sh.scene().ops]
    assert names == ["menu_.bmp", "button1p.bmp", "text1.bmp"]
    sh.handle(Press(*pos))
    assert rec.sounds == ["sfx/chrgen/ok.wav"]                        # on the press
    assert [o.path.rsplit("/", 1)[1] for o in sh.scene().ops][1] == "button1.bmp"
    sh.handle(Move(*other))                                           # dragged off: no highlight at all while another is under the pointer
    assert not any(o.path.rsplit("/", 1)[1].startswith("button") for o in sh.scene().ops)
    sh.handle(Release(*other))
    assert sh.name == "menu"                                          # a release over another button is no click
    sh.handle(Press(*pos))
    sh.handle(Release(*pos))
    assert sh.name == "newgame"


@needs_graphics
def test_outline_and_background_pixels_do_nothing():
    sh, rec = make_shell(GFS)
    to_menu(sh)
    click(sh, (5, 5))
    assert sh.name == "menu" and rec.sounds == []


@needs_graphics
def test_menu_is_centred_in_a_bigger_screen():
    sh, _ = make_shell(GFS, (800, 600))
    to_menu(sh)
    assert sh.current.origin == (80, 60)
    click(sh, button_centre(sh, 0))
    assert sh.name == "newgame"
    sh.handle(Move(0, 0))
    assert sh.current.under == 0                                      # the black border is outside the mask


# -- new game and the game screen ---------------------------------------------------------------------------------------------------------

@needs_graphics
def test_new_game_needs_a_hero_then_starts_the_game_screen():
    sh, rec = make_shell(GFS)
    to_menu(sh)
    click(sh, button_centre(sh, 0))
    ok, mask = None, sh.current.mask
    click(sh, mask_centre(sh, mask, 180))
    assert sh.name == "newgame" and rec.starts == []                  # OK is dead until a hero is chosen
    click(sh, mask_centre(sh, mask, 100))                             # hero 2
    click(sh, mask_centre(sh, mask, 60))                              # Hard
    click(sh, mask_centre(sh, mask, 180))
    assert sh.name == "game" and rec.starts == [{"map": "10", "difficulty": 3, "hero": 1, "name": "Master Oberic"}]
    assert sh.current.driven
    assert sh.apply(sh.current.run()) is None and sh.name == "menu"    # the session ended "menu"
    assert sh.screens["game"].session is None


@needs_graphics
def test_no_world_exists_before_a_game_starts(monkeypatch):
    from engine import world as world_mod
    made = []
    orig = world_mod.World.__init__
    monkeypatch.setattr(world_mod.World, "__init__", lambda self, *a, **k: (made.append(1), orig(self, *a, **k))[1])
    sh, rec = make_shell(GFS)
    to_menu(sh)
    click(sh, button_centre(sh, 0))
    click(sh, mask_centre(sh, sh.current.mask, 160))
    sh.handle(Key("o"))
    sh.handle(Key("escape"))
    assert made == [] and sh.screens["game"].world is None
    for s in sh.screens.values():
        assert not any(isinstance(v, world_mod.World) for v in vars(s).values())


@needs_graphics
def test_game_screen_owns_the_world_only_while_playing():
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.world import World
    rec = Recorder()

    class Game:
        def __init__(self, params):
            self.world = World.from_map(open_map(params["map"], GFS), AssetCache(GFS))

        def run(self):
            return "quit"
    rec.services.start_game = Game
    sh, _ = make_shell(GFS, rec=rec)
    to_menu(sh)
    sh.go("newgame")
    sh.go("game", map="10", difficulty=2)
    assert isinstance(sh.screens["game"].world, World)
    sh.apply(sh.current.run())
    assert sh.done and sh.screens["game"].world is None


# -- the golden screenshots ----------------------------------------------------------------------------------------------------------------

@needs_graphics
def test_shell_golden():
    from engine.backend_pygame import shell as backend
    spec = importlib.util.spec_from_file_location("update_golden", os.path.join(ROOT, "tools", "update_golden.py"))
    ug = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ug)
    gold = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["shell"]
    got = ug.shell_hashes(GFS)
    assert got == gold, "shell screens changed: %s; run tools/update_golden.py --only shell" % [k for k in gold if got.get(k) != gold[k]]
