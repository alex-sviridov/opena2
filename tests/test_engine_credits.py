"""m2: the credits screen (docs/engine/credits.md)."""

from engine.audio.settings import Settings
from engine.shell import Key, Move, Press, Services, Shell
from engine.shell.credits import START, TICK_MS, Credits

from allods2.common import INSTALL, as_fs
from helpers import needs

needs_install = needs("main", "text", "credits.txt")


def shell(music=None):
    sh = Shell(as_fs(INSTALL), (640, 480), Settings(), Services(music=(music or []).append))
    sh.start("menu")
    return sh


@needs_install
def test_menu_credits_button_opens_the_screen_and_asks_for_its_music():
    music = []
    sh = shell(music)
    assert sh.current.enabled(3)
    sh.go("credits")
    assert sh.name == "credits" and sh.current.lines[0] == '"nival.bmp"' and not sh.current.scene().cursor


@needs_install
def test_text_starts_below_the_screen_and_scrolls_one_pixel_per_tick():
    sh = shell()
    sh.go("credits")
    c = sh.current
    assert c.offset == START and all(o.y >= 480 for o in c.scene().ops)      # everything starts below the screen
    sh.update(TICK_MS - 1)
    assert c.offset == START
    sh.update(1)
    assert c.offset == START - 1
    sh.update(TICK_MS * 100)
    assert c.offset == START - 101


@needs_install
def test_headings_use_the_highlight_table_and_the_logo_is_centred():
    from engine.shell.scene import Image, Text
    sh = shell()
    sh.go("credits")
    c = sh.current
    c.offset = -c.line_h * 7                                      # "GAME DESIGN" (line 8) is on the screen
    ops = c.scene().ops
    imgs = [o for o in ops if isinstance(o, Image)]
    assert imgs and imgs[0].path.endswith("logo/nival.bmp")
    texts = {o.text: o for o in ops if isinstance(o, Text)}
    assert texts["GAME DESIGN"].table == "highlight" and texts["Serge Orlovsky"].table == "normal" and texts["GAME DESIGN"].flags == 2


@needs_install
def test_any_key_or_press_closes_but_a_move_does_not():
    sh = shell()
    sh.go("credits")
    sh.handle(Move(5, 5))
    assert sh.name == "credits"
    sh.handle(Press(5, 5, 1))
    assert sh.name == "menu"
    sh.go("credits")
    sh.handle(Key("x", False, "x"))
    assert sh.name == "menu"


@needs_install
def test_the_scroll_ends_at_the_menu_when_the_first_visible_line_passes_the_last():
    sh = shell()
    sh.go("credits")
    c = sh.current
    c.offset = -(len(c.lines) * c.line_h) + 1
    sh.update(TICK_MS - 1)
    assert sh.name == "credits"
    sh.update(1)
    assert sh.name == "menu"
