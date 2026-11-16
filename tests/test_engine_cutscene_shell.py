"""m1: the cutscene screen in the shell (docs/engine/cutscenes.md 4): redirect rules, abort keys, seen mask, picture position, audio feed, the start-up chain."""

import pytest

from engine.audio.settings import Settings
from engine.shell import Key, Move, Press, Release, Services, Shell, Video

from allods2.common import INSTALL, as_fs
from helpers import GFS, needs

needs_videos = needs("video", "teleport", "01.smk")


def shell(video=True):
    saved, pcm, music, logs = [], [], [], []
    svc = Services(video=video, save_settings=lambda s: saved.append(s.videos_seen), pcm=lambda a, r=22050: pcm.append(a),
                   music=music.append, log=logs.append)
    sh = Shell(as_fs(INSTALL), (640, 480), Settings(), svc)
    sh.rec = dict(saved=saved, pcm=pcm, music=music, logs=logs)
    return sh


@needs_videos
def test_codes_play_set_the_seen_bit_and_stop_the_music():
    sh = shell()
    sh.start("startup")
    sh.go("cutscene", codes=[1], then="menu")
    assert sh.name == "cutscene" and sh.rec["music"][-1] is None                 # the hard stop of step 1
    assert sh.settings.videos_seen == 0b11 and sh.rec["saved"] == [0b11]         # bit set and saved before the first frame
    sh.update(10)
    sc = sh.scene()
    vid = [op for op in sc.ops if isinstance(op, Video)]
    assert len(vid) == 1 and vid[0].pixels.shape == (360, 640) and vid[0].y == 60 and vid[0].x == 0 and not sc.cursor
    assert sh.rec["pcm"] and sh.rec["pcm"][0].shape[1] == 2


@needs_videos
@pytest.mark.parametrize("ev", [Key("a", False, "a"), Press(5, 5, 1), Press(5, 5, 3)])
def test_key_or_button_press_aborts_to_then(ev):
    sh = shell()
    sh.start("startup")
    sh.go("cutscene", codes=[1], then="menu")
    sh.update(100)
    sh.handle(ev)
    assert sh.name == "menu"


@needs_videos
@pytest.mark.parametrize("ev", [Move(5, 5), Release(5, 5, 1)])
def test_moves_and_releases_do_not_abort(ev):
    sh = shell()
    sh.start("startup")
    sh.go("cutscene", codes=[1], then="menu")
    sh.update(100)
    sh.handle(ev)
    assert sh.name == "cutscene"


@needs_videos
def test_plays_to_the_end_and_goes_on():
    sh = shell()
    sh.start("startup")
    sh.go("cutscene", codes=[1], then="menu")
    for _ in range(400):
        sh.update(70)
        if sh.name != "cutscene":
            break
    assert sh.name == "menu"
    assert any("video: video/teleport/01.smk" in ln for ln in sh.rec["logs"])


@needs_videos
def test_pending_code_plays_before_the_next_screen_and_then_continues():
    sh = shell()
    sh.start("startup")
    sh.pending_cuts.append(1)
    sh.go("menu")                                           # startup -> menu is a legal edge; the video goes first
    assert sh.name == "cutscene" and sh.params["then"] == "menu"
    sh.handle(Key("x", False, "x"))
    assert sh.name == "menu" and sh.pending_cuts == []


def test_without_a_video_backend_nothing_is_redirected():
    sh = Shell(as_fs(INSTALL), (640, 480), Settings(), Services())
    sh.start("startup")
    sh.pending_cuts.append(1)
    sh.go("menu")
    assert sh.name == "menu" and sh.pending_cuts == []


def test_an_illegal_then_is_refused():
    from engine.shell import ShellError
    sh = Shell(as_fs(INSTALL), (640, 480), Settings(), Services(video=True))
    sh.start("startup")
    with pytest.raises(ShellError):
        sh.go("cutscene", codes=[], then="game")


@needs_videos
def test_startup_plays_the_chain_and_an_abort_skips_all_of_it():
    sh = shell()
    sh.start()
    sh.update(10)
    assert sh.name == "cutscene" and sh.params["paths"][-1] == "video/intro/01.smk" and sh.settings.videos_seen & 1
    sh.update(10)
    sh.handle(Press(5, 5, 1))
    assert sh.name == "menu"                                # abort in the publisher logo: no nival, no intro


def test_startup_without_video_logs_skips_as_before():
    logs = []
    sh = Shell(as_fs(INSTALL), (640, 480), Settings(), Services(log=logs.append))
    sh.start()
    sh.update(10)
    assert sh.name == "menu" and logs[:3] == ["video skipped: video/logos/publisher.smk", "video skipped: video/logos/nival.smk", "video skipped: video/intro/01.smk"]


def test_town_core_cutscene_events_become_pending_codes():
    class Core:
        view = "map"

        def take_events(self):
            return [("autosave", 9998), ("cutscene", 2)]
    sh = Shell(None, (640, 480), Settings(), Services(video=True))
    sh.campaign = type("C", (), {"camp": object()})()
    sh._town = Core()
    sh._town.camp = sh.campaign.camp
    sh.drain_town()
    assert sh.pending_cuts == [2]


# -- the Cut Scenes window -----------------------------------------------------------------------------------------------------------------

def test_rows_are_the_set_bits_in_order_titled_by_bit():
    from engine.shell.cutlist import rows_of
    titles = ["Intro", "Astral travel", "Starfall", "Crown", "Knights", "Druids"]
    assert rows_of(0b101011, titles) == [(0, "Intro"), (1, "Astral travel"), (3, "Crown"), (5, "Druids")]
    assert rows_of(1 | 1 << 9, titles) == [(0, "Intro"), (9, "")]


def click_at(sh, x, y):
    sh.handle(Move(x, y))
    sh.handle(Press(x, y, 1))
    sh.handle(Release(x, y, 1))


@needs_videos
def test_cut_scenes_flow_ok_plays_the_row_then_the_window_returns():
    sh = shell()
    sh.settings.videos_seen = 0b1011                                 # intro, teleport, crown
    sh.start("menu")
    assert sh.screens["menu"].enabled(2)                              # CUT SCENES is on once videos play
    sh.go("cutlist")
    d = sh.screens["cutlist"]
    assert [t for _, t in d.rows] == ["Intro", "Astral travel", "Crown"] and d.list.sel == 0
    d.list.sel = 1
    sh.handle(Key("return", False, ""))
    assert sh.name == "cutscene" and sh.params["codes"] == [1] and sh.params["then"] == "cutlist"
    sh.handle(Press(5, 5, 1))                                        # abort -> back to the list, selection kept
    assert sh.name == "cutlist" and sh.screens["cutlist"].list.sel == 1


@needs_videos
def test_cut_scenes_row_index_quirk_and_cancel():
    sh = shell()
    sh.settings.videos_seen = 0b101111                               # bits 0-3 and 5: five rows
    sh.start("menu")
    sh.go("cutlist")
    d = sh.screens["cutlist"]
    d.list.sel = 4                                                   # the druids row...
    sh.handle(Key("return", False, ""))
    assert sh.params["codes"] == [4]                                 # ...plays code 4 (knights): the exe passes the row index (`0x48a7f4`)
    sh.handle(Key("x", False, "x"))
    sh.handle(Key("escape", False, ""))
    assert sh.name == "menu"


@needs_videos
def test_cut_scenes_buttons_and_scene():
    sh = shell()
    sh.start("menu")
    sh.go("cutlist")
    d = sh.screens["cutlist"]
    ok, cancel = [d.abs(r) for r in d.button_rects()]
    assert (ok[0], cancel[0]) == (124 + 392 // 7, 124 + 4 * 392 // 7) and ok[1] == 60 + 360 - 0x3C
    click_at(sh, cancel[0] + 5, cancel[1] + 5)
    assert sh.name == "menu"
    sh.go("cutlist")
    click_at(sh, ok[0] + 5, ok[1] + 5)
    assert sh.name == "cutscene" and sh.params["codes"] == [0]


def test_cut_scenes_stays_disabled_without_a_video_backend():
    sh = Shell(as_fs(INSTALL), (640, 480), Settings(), Services())
    sh.start("menu")
    assert not sh.screens["menu"].enabled(2)


def test_list_page_keys_follow_the_exe_slots():
    """`0x4d86c6` / `0x4d8720`: PageUp = the top visible row, else a page above; PageDown = the bottom visible row, else a page below (clamped)."""
    from engine.shell.saveload import SlotList
    lst = SlotList((0, 0, 100, 19 * 4), ["r%d" % i for i in range(20)])
    assert lst.visible == 4
    lst.page_down()
    assert (lst.sel, lst.top) == (3, 0)
    lst.page_down()
    assert (lst.sel, lst.top) == (7, 4)
    lst.sel, lst.top = 7, 4
    lst.page_up()
    assert (lst.sel, lst.top) == (4, 4)
    lst.page_up()
    assert (lst.sel, lst.top) == (0, 0)
    lst.sel = 19
    lst.show()
    lst.page_down()
    assert lst.sel == 19
