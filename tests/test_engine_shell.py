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
    assert GRAPH["startup"] == {"menu"} and GRAPH["menu"] == {"newgame", "load", "quit"} and "options" not in GRAPH
    assert GRAPH["newgame"] == {"menu", "chargen"} and GRAPH["chargen"] == {"newgame", "locations"}                    # L2: the campaign in one window
    assert GRAPH["locations"] == {"game", "menu"} and GRAPH["game"] == {"menu", "locations"}


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
    sh.start("locations")
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
def test_script_menu_new_game_cancel_exit_follows_the_graph():
    sh, rec = make_shell(GFS)
    to_menu(sh)
    click(sh, button_centre(sh, 0))
    assert sh.name == "newgame" and rec.music[-1] == "chrgen"
    click(sh, mask_centre(sh, sh.current.mask, 160))                 # Cancel
    assert sh.name == "menu" and rec.music[-1] == "menu"
    for k in ("o", "escape", "return", "n"):                          # the menu has no key handling: no options entry (`0x485cc4`)
        sh.handle(Key(k))
        assert sh.name == "menu"
    click(sh, button_centre(sh, 7))
    assert sh.done
    assert sh.history == ["startup", "menu", "newgame", "menu", "quit"]
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

def to_newgame(sh=None):
    sh, rec = (sh, None) if sh is not None else make_shell(GFS)
    to_menu(sh)
    click(sh, button_centre(sh, 0))
    assert sh.name == "newgame"
    return sh


def press(sh, value):
    p = mask_centre(sh, sh.current.mask, value)
    sh.handle(Move(*p))
    sh.handle(Press(*p))
    return p


@needs_graphics
def test_new_game_starts_with_hero_zero_and_the_original_defaults():
    sh, rec = make_shell(GFS)
    to_newgame(sh)
    rec.sounds.clear()                                                # the menu's own click
    ng = sh.current
    assert (ng.hero, ng.level, ng.name_text) == (0, 0, "Master Oberic")             # hero 0 selected by the show routine, level 0 (INFERRED), the ctor's name
    press(sh, 180)                                                    # OK acts on the PRESS (`0x436d48`)
    assert sh.name == "chargen" and rec.starts == []                  # OK goes on to the character generator (L2), not into a map
    assert sh.params == {"difficulty": 1, "hero": 0, "hero_code": 0, "name": "Master Oberic"}
    assert rec.sounds == ["sfx/chrgen/ok.wav"]


@needs_graphics
def test_press_selects_levels_and_heroes_with_their_sounds_and_a_drag_selects_too():
    sh, rec = make_shell(GFS)
    to_newgame(sh)
    rec.sounds.clear()
    ng = sh.current
    press(sh, 60)
    assert ng.level == 2 and rec.sounds[-1] == "sfx/chrgen/level3.wav"
    press(sh, 100)
    assert ng.hero == 1 and rec.sounds[-1] == "sfx/chrgen/char.wav"
    sh.handle(Move(*mask_centre(sh, ng.mask, 120)))                   # the button is still held: the move selects hero 2 (`0x434f15`)
    assert ng.hero == 2
    sh.handle(Release(*mask_centre(sh, ng.mask, 120)))
    sh.handle(Move(*mask_centre(sh, ng.mask, 140)))                   # not held: only hover
    assert ng.hero == 2
    press(sh, 40)
    assert ng.level == 1 and rec.sounds[-1] == "sfx/chrgen/level2.wav"


@needs_graphics
def test_hero_codes_and_names():
    from engine.shell.newgame import HERO_CODE, HERO_NAMES
    assert [c & 0x40 != 0 for c in HERO_CODE] == [False, False, True, True]          # bit 0x40 = mage: fighters, fighters, mages
    assert [c & 0x80 != 0 for c in HERO_CODE] == [False, True, True, False]          # bit 0x80 = female: Aldor m, Sagita f, Galinel f, Gildarius m
    sh, rec = make_shell(GFS)
    to_newgame(sh)
    ng = sh.current
    sh.handle(Key("x", char="x"))
    assert ng.name_text == "Master Oberic"                            # the initial text is 13 characters: nothing is added (the limit is 10, `0x4323e1`)
    # a typed (non-default) name is kept when the hero changes; a default name follows the hero
    press(sh, 140)
    assert ng.name_text == "Master Oberic"
    ng.name_text = "Sagita"
    press(sh, 120)
    assert ng.name_text == HERO_NAMES[2]
    press(sh, 120)
    ng.name_text = "Unnamed"
    press(sh, 140)
    assert ng.name_text == HERO_NAMES[3]


@needs_graphics
def test_name_field_rules():
    sh, rec = make_shell(GFS)
    to_newgame(sh)
    rec.sounds.clear()
    ng = sh.current
    for _ in range(len("Master Oberic")):
        sh.handle(Key("backspace"))
    assert ng.name_text == "" and rec.sounds.count("sfx/letter2.wav") == 13
    sh.handle(Key("return"))                                          # an empty name does nothing: no sound, no OK
    press(sh, 180)
    assert sh.name == "newgame" and rec.starts == [] and "sfx/chrgen/ok.wav" not in rec.sounds
    sh.handle(Key("backspace"))                                       # nothing to delete: no sound
    n = rec.sounds.count("sfx/letter2.wav")
    assert n == 13
    for ch in "Elfric the Brave and more":                            # printable only, ten at most, spaces and punctuation allowed
        sh.handle(Key(ch.lower() if ch != " " else "space", char=ch))
    assert ng.name_text == "Elfric the"
    sh.handle(Key("x", char="\x07"))                                  # a control character is not text (the backend drops it; the screen would too)
    assert ng.name_text == "Elfric the"
    sh.handle(Key("return"))
    assert sh.name == "chargen" and sh.params["name"] == "Elfric the"


@needs_graphics
def test_escape_and_cancel_leave_with_the_ok_sound():
    sh, rec = make_shell(GFS)
    to_newgame(sh)
    rec.sounds.clear()
    sh.handle(Key("escape"))
    assert sh.name == "menu" and rec.sounds == ["sfx/chrgen/ok.wav"]
    to_newgame(sh)
    press(sh, 160)
    assert sh.name == "menu" and rec.starts == []


@needs_graphics
def test_name_caret_blinks_every_500_ms_and_typing_restarts_it():
    sh, _ = make_shell(GFS)
    to_newgame(sh)
    ng = sh.current
    ng.name_text = "Elf"
    shown = lambda: [o for o in sh.scene().ops if hasattr(o, "text")][0].text
    assert shown().endswith("|")
    sh.update(300)
    assert shown().endswith("|")
    sh.update(300)                                                    # 600 ms > 500: off
    assert not shown().endswith("|")
    sh.handle(Key("a", char="a"))
    assert shown().endswith("|") and ng.blink_ms == 0


@needs_graphics
def test_torches_burn_on_the_two_braziers_at_15_frames_per_67_ms():
    sh, _ = make_shell(GFS)
    to_newgame(sh)
    torches = lambda: [(o.path.rsplit("/", 1)[1], o.x, o.y) for o in sh.scene().ops if "torch" in getattr(o, "path", "")]
    assert torches() == [("t10000.bmp", 4, 200), ("t20007.bmp", 589, 200)]
    sh.update(66)
    assert torches()[0][0] == "t10000.bmp"
    sh.update(1)
    assert torches() == [("t10001.bmp", 4, 200), ("t20008.bmp", 589, 200)]
    sh.update(67 * 14)
    assert torches()[0][0] == "t10000.bmp" and torches()[1][0] == "t20007.bmp"          # 15 frames wrap


@needs_graphics
def test_torch_position_is_exact_in_the_art():
    """The frames' static pixels equal MainArea at the torch positions (the evidence of the CONFIRMED position)."""
    import numpy as np
    from allods2.common import as_fs
    from allods2.graphics import load_bmp
    from engine.shell.newgame import DIR, TORCH_AT
    fs = as_fs(GFS)
    base = load_bmp(DIR + "mainarea.bmp", fs).rgb.astype(int)
    for t, (x, y) in enumerate(TORCH_AT):
        ims = [load_bmp(DIR + "torch%d/t%d%04d.bmp" % (t + 1, t + 1, i), fs).rgb.astype(int) for i in range(15)]
        med = np.median(np.stack(ims), axis=0)
        static = np.stack([np.abs(i - med).sum(axis=2) for i in ims]).max(axis=0) < 20
        assert static.sum() > 1500 and np.abs(base[y:y + 72, x:x + 48] - med)[static].mean() < 0.01


@needs_graphics
def test_tablet_and_portrait_states():
    sh, _ = make_shell(GFS)
    to_newgame(sh)
    ng = sh.current
    names = lambda: [o.path.rsplit("/", 1)[1] for o in sh.scene().ops if hasattr(o, "path")]
    assert "h1sel.bmp" in names() and "level0on.bmp" in names()       # selected: the big portrait and the `on` tablet
    sh.handle(Move(*mask_centre(sh, ng.mask, 20)))
    assert "level0lon.bmp" in names()                                 # selected and hovered
    sh.handle(Move(*mask_centre(sh, ng.mask, 40)))
    assert "level1l.bmp" in names() and "level0on.bmp" in names()     # hover only: `l`
    sh.handle(Move(*mask_centre(sh, ng.mask, 100)))                   # the partner pane is lit: the variant with it
    assert "h1sel2.bmp" in names() and "h1sel.bmp" not in names()
    sh.handle(Move(*mask_centre(sh, ng.mask, 120)))
    assert "h3on.bmp" in names() and "h1sel.bmp" in names()


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
    sh.go("chargen", hero_code=0, name="Aldor", difficulty=2)
    sh.screens["locations"].enter = lambda **k: None                  # no campaign here: only the game screen's World ownership is tested
    sh.go("locations")
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
