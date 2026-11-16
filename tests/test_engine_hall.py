"""m3: the hall of fame screen (docs/engine/hall.md)."""

from engine import famehall
from engine.audio.settings import Settings
from engine.shell import Key, Move, Press, Release, Services, Shell
from engine.shell.hall import NAME_X, OK_RECT, RANK_X, SCORE_RIGHT, thousands
from engine.shell.scene import Image, Text

from allods2.common import INSTALL, as_fs
from allods2.formats import saves as S
from helpers import needs

needs_install = needs("main", "graphics", "famehall", "hall.bmp")


def shell(sounds=None, hall=None):
    sh = Shell(as_fs(INSTALL), (640, 480), Settings(), Services(sound=(sounds if sounds is not None else []).append))
    if hall is not None:
        sh.hall = hall
    sh.start("menu")
    return sh


def centre(sh):
    ox, oy = sh.current.origin
    l, t, w, h = OK_RECT
    return ox + l + w // 2, oy + t + h // 2


def test_thousands_separators():
    assert [thousands(n) for n in (0, 999, 1000, 70006, 1234567, -123, -1234)] == ["0", "999", "1,000", "70,006", "1,234,567", "-123", "-1,234"]


@needs_install
def test_install_hall_is_read_when_no_settings_file_exists():
    h = famehall.load(None, as_fs(INSTALL))
    assert [e.name for e in h.entries][:2] == ["Diamond", "Glazz"] and len(h.entries) == 10


@needs_install
def test_menu_button_opens_the_hall_and_ok_returns():
    sounds = []
    sh = shell(sounds)
    assert sh.current.enabled(6)
    sh.go("hall")
    assert sh.name == "hall"
    sh.handle(Move(*centre(sh)))
    ops = sh.current.scene().ops
    assert any(isinstance(o, Image) and o.path.endswith("Ok_l_off.bmp") for o in ops)
    sh.handle(Press(*centre(sh), 1))
    assert sounds == ["sfx/chrgen/ok.wav"] and any(isinstance(o, Image) and o.path.endswith("Ok_l_on.bmp") for o in sh.current.scene().ops)
    sh.handle(Release(*centre(sh), 1))
    assert sh.name == "menu"


@needs_install
def test_release_outside_does_not_close_and_keys_do():
    sh = shell()
    sh.go("hall")
    sh.handle(Press(*centre(sh), 1))
    sh.handle(Release(5, 5, 1))
    assert sh.name == "hall"
    sh.handle(Key("escape"))
    assert sh.name == "menu"


@needs_install
def test_table_rows_use_the_exe_columns_and_row_step():
    hall = famehall.Hall([S.HallEntry("Aldor", 1234567, 0, 0), S.HallEntry("Sagita", 5, 0, 0), S.HallEntry("Third", 3, 0, 0)])
    sh = shell(hall=hall)
    sh.go("hall")
    ox, oy = sh.current.origin
    texts = [o for o in sh.current.scene().ops if isinstance(o, Text)]
    assert [t.text for t in texts] == ["1.", "Aldor", "1,234,567", "2.", "Sagita", "5", "3.", "Third", "3"]
    assert (texts[0].x, texts[1].x, texts[2].x) == (ox + RANK_X, ox + NAME_X, ox + SCORE_RIGHT) and texts[2].flags == 1 and texts[1].flags == 0
    lh = sh.current.line_h
    assert [t.y - oy for t in texts[::3]] == [0x91, 0x91 + int(1.5 * lh), 0x91 + int(3.0 * lh)] and all(t.font == 4 for t in texts)


@needs_install
def test_credits_lead_to_the_hall_only_when_the_campaign_is_finished():
    sh = shell()
    sh.go("credits")
    sh.handle(Press(5, 5, 1))
    assert sh.name == "menu"

    class Camp:
        vars = {0x300: 0x78}

    class Game:
        camp = Camp()

    sh.campaign = Game()
    sh.go("credits")
    sh.handle(Press(5, 5, 1))
    assert sh.name == "hall"
    Camp.vars = {0x300: 0x77}
    assert not sh.campaign_finished()
