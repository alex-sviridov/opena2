"""L10d: the Save / Load / Delete windows (docs/engine/save-ui.md): the dialogs' rules over synthetic slots (no install), and a scripted run through the real
screens (save in a town, back to the main menu, load, continue the campaign).  The scripted run needs the install."""

import os
import struct

import pytest

pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from engine import saveslots as SS  # noqa: E402
from engine import savegame  # noqa: E402
from engine.shell import GRAPH, Key, Move, Press, Release, Shell  # noqa: E402
from engine.shell import saveload as SL  # noqa: E402
from helpers import GFS, needs_graphics  # noqa: E402
from shell_scenarios import Recorder, button_centre, click, click_region, make_shell, map_walk, to_menu  # noqa: E402
from test_engine_saveslots import fake  # noqa: E402


def mid(rect):
    if hasattr(rect, "right"):                                                      # a `Rect`
        rect = (rect.x, rect.y, rect.w, rect.h)
    return rect[0] + rect[2] // 2, rect[1] + rect[3] // 2


def type_text(dlg, text):
    for ch in text:
        dlg.event(Key(ch, False, ch))


def press_button(dlg, i):
    pos = mid(dlg.abs(dlg.button_rects()[i]))
    for ev in (Move(*pos), Press(*pos), Release(*pos)):
        out = dlg.event(ev)
    return out


def click_row(dlg, i):
    x, y, w, h = dlg.abs(dlg.list.rect)
    pos = (x + 10, y + (i - dlg.list.top) * SL.ROW + 4)
    for ev in (Move(*pos), Press(*pos), Release(*pos)):
        dlg.event(ev)


@pytest.fixture
def shell(tmp_path):
    return Shell(None, (640, 480), slots=SS.SaveSlots(tmp_path)), tmp_path


def three(tmp_path):
    fake(tmp_path / "game0000.sav", "first", mtime=1000)
    fake(tmp_path / "game0001.sav", "second", mtime=2000)
    fake(tmp_path / "game9999.sav", "Restart last mission", mtime=3000)


# -- the Save window ---------------------------------------------------------------------------------------------------------------------------

def test_save_window_starts_on_the_empty_new_row_with_ok_disabled(shell):
    sh, tmp = shell
    three(tmp)
    d = SL.SaveDialog(sh, sh.slots)
    assert d.list.rows[0] == "" and len(d.list.rows) == 3 and d.list.sel == 0     # the new row + two listed saves; game9999 is hidden
    assert d.enabled() == (False, False, True)
    assert press_button(d, 0) is None                                             # a disabled Ok does nothing


def test_typing_enables_ok_and_ok_saves_to_the_smallest_free_name(shell):
    sh, tmp = shell
    three(tmp)
    d = SL.SaveDialog(sh, sh.slots)
    type_text(d, "My game")
    assert d.text == "My game" and d.enabled()[0]
    assert press_button(d, 0) == ("save", "game0002.sav", "My game")
    d.event(Key("backspace"))
    assert d.text == "My gam"


def test_selecting_a_row_copies_its_description_and_row_zero_clears_it(shell):
    sh, tmp = shell
    three(tmp)
    d = SL.SaveDialog(sh, sh.slots)
    click_row(d, 1)
    assert d.list.sel == 1 and d.text == "second" and d.enabled() == (True, True, True)      # newest first: game0001
    d.event(Key("down"))
    assert d.text == "first"
    click_row(d, 0)
    assert d.text == "" and d.enabled()[1] is False                                           # row 0 cannot be deleted


def test_ok_with_a_listed_description_overwrites_that_file_and_a_retyped_row_overwrites_its_own(shell):
    sh, tmp = shell
    three(tmp)
    d = SL.SaveDialog(sh, sh.slots)
    type_text(d, "first")
    assert press_button(d, 0) == ("save", "game0000.sav", "first") and d.list.sel == 2
    d = SL.SaveDialog(sh, sh.slots)
    click_row(d, 1)
    for _ in range(6):
        d.event(Key("backspace"))
    type_text(d, "renamed")
    assert press_button(d, 0) == ("save", "game0001.sav", "renamed")


def test_enter_is_ok_and_escape_cancels(shell):
    sh, tmp = shell
    d = SL.SaveDialog(sh, sh.slots)
    assert d.event(Key("return")) is None                                         # nothing typed
    type_text(d, "x")
    assert d.event(Key("return")) == ("save", "game0000.sav", "x")
    assert d.event(Key("escape")) == ("close",)
    assert press_button(d, 2) == ("close",)


def test_the_description_is_limited_to_the_buffer(shell):
    sh, _ = shell
    d = SL.SaveDialog(sh, sh.slots)
    type_text(d, "a" * 300)
    assert len(d.text) == SL.EDIT_MAX


def test_delete_asks_and_yes_removes_the_file(shell):
    sh, tmp = shell
    three(tmp)
    d = SL.SaveDialog(sh, sh.slots)
    click_row(d, 2)                                                               # game0000 "first"
    assert press_button(d, 1) is None and d.box is not None and d.box.kind == "confirm"
    assert d.box.message == "Are you sure you want to delete game 'first' ?"
    yes, no = d.box.rects()
    for ev in (Press(*mid(no)), Release(*mid(no))):
        d.event(ev)
    assert d.box is None and (tmp / "game0000.sav").exists()                      # No
    click_row(d, 2)
    press_button(d, 1)
    d.event(Key("escape"))
    assert d.box is None and (tmp / "game0000.sav").exists()                      # ESC = No
    press_button(d, 1)
    for ev in (Press(*mid(yes)), Release(*mid(yes))):
        d.event(ev)
    assert d.box is None and not (tmp / "game0000.sav").exists()
    assert len(d.list.rows) == 2 and d.list.sel == 1 and d.text == "second"       # the selection moved on and its text is in the field


def test_the_window_is_modal_while_the_confirmation_is_up(shell):
    sh, tmp = shell
    three(tmp)
    d = SL.SaveDialog(sh, sh.slots)
    click_row(d, 1)
    press_button(d, 1)
    assert d.event(Key("escape")) is None and d.box is None                       # ESC closed the box, not the window
    press_button(d, 1)
    type_text(d, "zz")
    assert d.text == "second"                                                      # typing goes to the box (nothing)


# -- the Load window ---------------------------------------------------------------------------------------------------------------------------

def test_load_window_lists_the_autosaves_too_and_selects_the_newest(shell):
    sh, tmp = shell
    three(tmp)
    d = SL.LoadDialog(sh, sh.slots)
    assert [s.name for s in d.slots] == ["game9999.sav", "game0001.sav", "game0000.sav"] and d.list.sel == 0
    assert d.enabled() == (True, True, True)
    assert press_button(d, 0) == ("load", "game9999.sav")
    d.event(Key("down"))
    assert d.event(Key("return")) == ("load", "game0001.sav")


def test_load_window_with_no_saves_disables_ok_and_delete(shell):
    sh, _ = shell
    d = SL.LoadDialog(sh, sh.slots)
    assert d.enabled() == (False, False, True) and press_button(d, 0) is None and press_button(d, 1) is None
    assert press_button(d, 2) == ("close",)


def test_deleting_the_last_save_disables_the_buttons(shell):
    sh, tmp = shell
    fake(tmp / "game0000.sav", "only")
    d = SL.LoadDialog(sh, sh.slots)
    press_button(d, 1)
    yes = d.box.rects()[0]
    for ev in (Press(*mid(yes)), Release(*mid(yes))):
        d.event(ev)
    assert d.slots == [] and d.enabled() == (False, False, True)


def test_list_scrolls_by_wheel_and_keys(shell):
    sh, tmp = shell
    for i in range(30):
        fake(tmp / ("game%04d.sav" % i), "s%d" % i, mtime=1000 + i)
    d = SL.LoadDialog(sh, sh.slots)
    vis = d.list.visible
    assert vis == 0xC0 // SL.ROW and d.list.top == 0
    from engine.shell import Wheel
    d.event(Wheel(0, 0, -1))
    assert d.list.top == 1
    for _ in range(40):
        d.event(Key("down"))
    assert d.list.sel == 29 and d.list.top == 30 - vis                             # the selection stays in view
    for _ in range(40):
        d.event(Wheel(0, 0, 1))
    assert d.list.top == 0


def test_geometry_of_the_two_windows():
    """The rects of the build slots `0x43ece0` / `0x43df48` (relative to the 488x360 frame)."""
    class Sh:
        fs, size, slots = None, (640, 480), None
        play = lambda *a: None
    s, l = SL.SaveDialog(Sh, None), SL.LoadDialog(Sh, None)
    assert (s.fx, s.fy) == (76, 60)
    assert s.list.rect == (0x28, 0x80, 424 - 0x28, 0x90) and l.list.rect == (0x28, 0x5C, 424 - 0x28, 0xC0)
    assert s.button_rects() == [(73, 296, 97, 24), (195, 296, 97, 24), (317, 296, 97, 24)]
    assert l.button_rects()[0][1] == 0x134


# -- the main menu and the screens -------------------------------------------------------------------------------------------------------------

def test_graph_has_the_load_edges():
    assert {"town", "locations", "menu"} <= GRAPH["load"] and "town" in GRAPH["town"]


@needs_graphics
def test_main_menu_load_is_enabled_by_any_game_sav(tmp_path):
    sh, _ = make_shell(GFS)
    sh.slots = SS.SaveSlots(tmp_path)
    to_menu(sh)
    assert not sh.current.enabled(4)
    (tmp_path / "game0000.sav").write_bytes(b"junk")                               # any file counts (`FindFirstFile`), valid or not
    sh.go("newgame")
    sh.go("menu")                                                                   # the menu is entered again: the folder is looked at again
    assert sh.current.enabled(4) and sh.current.enabled(0) and not sh.current.enabled(1)
    sh2, _ = make_shell(GFS)
    to_menu(sh2)
    assert not sh2.current.enabled(4)                                              # no folder: disabled


@needs_graphics
def test_load_screen_cancel_returns_to_the_menu_and_an_invalid_file_shows_a_notice(tmp_path):
    sh, _ = make_shell(GFS)
    sh.slots = SS.SaveSlots(tmp_path)
    fake(tmp_path / "game0000.sav", "broken")                                       # a header that passes the list but is no real save
    to_menu(sh)
    sh.go("load")
    d = sh.current.dialog
    assert [s.name for s in d.slots if s.name != "game9999.sav"] == ["game0000.sav"]            # the mission's auto-save is listed too (L10e-B)
    sh.handle(Press(*mid(d.abs(d.button_rects()[0]))))
    sh.handle(Release(*mid(d.abs(d.button_rects()[0]))))
    assert sh.name == "load" and d.box is not None and d.box.kind == "notice" and "Invalid save file" in d.box.message
    sh.handle(Key("return"))
    assert d.box is None
    sh.handle(Key("escape"))
    assert sh.name == "menu"


def test_a_mission_kind_file_needs_the_codec_and_a_readable_stream(tmp_path):
    """A shell without a codec shows the "not supported" notice; with the codec (the default since L10e-B) a mission file whose stream is no mission save is
    refused with the reader's message."""
    from allods2.formats import saves as S
    sh = Shell(None, (640, 480), slots=SS.SaveSlots(tmp_path))
    tail = S.ClientTail.new("mission save", S.ClientState(in_battle=1))
    sh.slots.write("game9999.sav", S.SaveGame(b"\0" * 8, tail).pack())
    assert savegame.kind(sh.slots.read("game9999.sav")) == "mission"
    status, text = SL.load_file(sh, "game9999.sav")
    assert status == "error" and text.startswith("Invalid save file")
    assert isinstance(sh.mission_codec, savegame.MissionSaveCodec)
    sh.mission_codec = None
    assert SL.load_file(sh, "game9999.sav") == ("error", SL.NOT_SUPPORTED)


def test_a_multiplayer_or_outdated_file_is_refused_with_the_readers_message(tmp_path):
    sh = Shell(None, (640, 480), slots=SS.SaveSlots(tmp_path))
    sh.slots.write("game0000.sav", struct.pack("<III", SS.MAGIC, 8, 1) + b"\0" * 12)
    status, text = SL.load_file(sh, "game0000.sav")
    assert status == "error" and text
    sh.slots.write("game0001.sav", b"\0" * 32)
    assert SL.load_file(sh, "game0001.sav")[0] == "error"


# -- the campaign through the real screens -----------------------------------------------------------------------------------------------------

class OracleSession:
    def __init__(self, params, shell, log):
        camp = params["campaign"]
        self.world, _ = camp.start_mission(params["mission"])
        self.mission = params["mission"]
        log.append(self.mission)

    def run(self):
        from engine import objective
        r = objective.run(str(self.mission), GFS, seed=1, world=self.world, side=())
        return "victory" if r["result"] == "won" else "defeat"


def play_to_a_town(sh):
    """From the intro map: win the head missions (no town is open yet: the next one starts at once) until the map shows a town, then walk into it."""
    from engine.sim import campaign as C
    map_walk(sh)
    for _ in range(12):
        sh.apply(sh.current.run())
        if sh.name == "locations":
            break
    assert sh.name == "locations"
    town = next(loc for loc in sh.campaign.camp.available if loc[0] == C.TOWN)
    map_walk(sh, town)
    assert sh.name == "town"


def menu_button(sh, i):
    return mid(sh.current.menu.rects()[i])


@needs_graphics
def test_save_in_a_town_back_to_the_menu_load_and_continue_the_campaign(tmp_path):
    rec, played = Recorder(), []
    rec.services.start_game = lambda params: OracleSession(params, sh, played)
    sh, _ = make_shell(GFS, rec=rec)
    sh.slots = SS.SaveSlots(tmp_path)
    to_menu(sh)
    click(sh, button_centre(sh, 4))                                                 # LOAD GAME: disabled, nothing saved yet
    assert sh.name == "menu"
    click(sh, button_centre(sh, 0))
    sh.handle(Key("return"))
    sh.handle(Key("return"))
    assert sh.name == "locations"
    play_to_a_town(sh)                                                               # the oracle wins the head missions
    before = savegame.comparable(sh.campaign)
    location = sh.campaign.camp.location

    # the scene's menu: Save and Load are enabled (Load by any file: the missions' game9999 auto-saves exist by now, L10e-B)
    sh.handle(Key("escape"))
    menu = sh.current.menu
    assert [e[2] for e in menu.entries()[:2]] == [True, True]
    click(sh, menu_button(sh, 0))                                                    # Save Game
    d = sh.current.dialog
    assert isinstance(d, SL.SaveDialog) and sh.current.menu is None
    type_text(d, "Before the inn")
    pos = mid(d.abs(d.button_rects()[0]))
    click(sh, pos)                                                                   # Ok
    assert sh.current.dialog is None and sh.name == "town"
    assert [(s.name, s.description) for s in sh.slots.scan()] == [("game0000.sav", "Before the inn")]
    assert savegame.kind(sh.slots.read("game0000.sav")) == "town"

    # Abort Game -> Exit to Main Menu, then LOAD is enabled
    sh.handle(Key("escape"))
    click(sh, menu_button(sh, 3))
    click(sh, menu_button(sh, 0))
    assert sh.name == "menu" and sh.current.enabled(4)
    click(sh, button_centre(sh, 4))
    assert sh.name == "load"
    d = sh.current.dialog
    assert [s.name for s in d.slots if s.name != "game9999.sav"] == ["game0000.sav"]            # the mission's auto-save is listed too (L10e-B)
    click(sh, mid(d.abs(d.button_rects()[0])))                                       # Ok
    assert sh.name == "town" and sh.campaign.camp.location == location
    assert savegame.comparable(sh.campaign) == before                                # the same party, gold, variables, shop table, available list
    assert sh.town_core().view == "scene" and sh.town_core().town == location[1]

    # the loaded campaign goes on through the real screens: the inn, the leave region, the map, the next mission
    from shell_scenarios import visit_current_town
    visit_current_town(sh, shop=True)
    assert sh.name == "locations"
    while not any(k == 1 for k, _ in sh.campaign.camp.available):
        from shell_scenarios import visit_town_as_player
        visit_town_as_player(sh, shop=True)
    n = next(m for k, m in sh.campaign.camp.available if k == 1)
    map_walk(sh, (1, n))
    assert sh.name == "game" and sh.params["mission"] == n
    sh.apply(sh.current.run())
    assert n in played and sh.campaign.camp.get(0x380 + n) == 1 and sh.name in ("locations", "game")
    assert rec.lines and any(l.startswith("load: location") for l in rec.lines) and any(l.startswith("save: game0000.sav") for l in rec.lines)


@needs_graphics
def test_load_from_the_scene_menu_replaces_the_running_game(tmp_path):
    """A save, then a load from the scene's own menu: `town -> town` with the saved campaign state; Delete and Cancel in the Load window."""
    rec, played = Recorder(), []
    rec.services.start_game = lambda params: OracleSession(params, sh, played)
    sh, _ = make_shell(GFS, rec=rec)
    sh.slots = SS.SaveSlots(tmp_path)
    to_menu(sh)
    click(sh, button_centre(sh, 0))
    sh.handle(Key("return"))
    sh.handle(Key("return"))
    play_to_a_town(sh)
    sh.handle(Key("escape"))
    click(sh, menu_button(sh, 0))
    type_text(sh.current.dialog, "A")
    click(sh, mid(sh.current.dialog.abs(sh.current.dialog.button_rects()[0])))
    gold = sh.campaign.gold
    sh.campaign.gold += 777                                                          # the running game moves on after the save
    sh.handle(Key("escape"))
    assert sh.current.menu.entries()[1][2] is True                                   # Load is enabled now
    click(sh, menu_button(sh, 1))
    d = sh.current.dialog
    assert isinstance(d, SL.LoadDialog) and [s.description for s in d.slots if s.name != "game9999.sav"] == ["A"]
    click(sh, mid(d.abs(d.button_rects()[0])))
    assert sh.name == "town" and sh.history[-2:] == ["town", "town"] and sh.campaign.gold == gold
    sh.handle(Key("escape"))
    click(sh, menu_button(sh, 1))
    d = sh.current.dialog
    click(sh, mid(d.abs(d.button_rects()[1])))                                        # Delete
    assert d.box is not None
    click(sh, mid(d.box.rects()[0]))                                                  # Yes
    assert [x.name for x in sh.slots.scan(include_hidden=True)] == ["game9999.sav"]
    click(sh, mid(d.abs(d.button_rects()[2])))                                        # Cancel
    assert sh.current.dialog is None and sh.name == "town"
