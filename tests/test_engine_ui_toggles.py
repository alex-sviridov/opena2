"""The option-toggle lines of the message list that the engine had no home for (ui-layout 11.5): Ctrl+W / N / C / U and the script message."""

from engine.ui import GameUi, Layout, MainText
from engine.ui.messages import OPTION_MS, SCRIPT_MS, OptionToggles
from engine.sim.triggers import ScriptMessage
from test_engine_death import world

MAIN = MainText(["m%03x" % i for i in range(0x180)])
PATCH = MainText(["p%03x" % i for i in range(0x80)])


def test_retreat_cycles_and_text():
    t = OptionToggles()
    assert [t.press("w", MAIN, PATCH) for _ in range(4)] == ["m05f", "m060", "m05e", "m05f"]     # 0x5e + mode 1, 2, 0, 1


def test_day_night_and_colours_flip():
    t = OptionToggles()
    assert t.press("n", MAIN, PATCH) == "m068" and t.press("n", MAIN, PATCH) == "m069"            # default on: first press = Off
    assert t.press("c", MAIN, PATCH) == "p056" and t.press("c", MAIN, PATCH) == "p055"            # patch.txt 0x55 + new state


def test_autocast_cycle_keeps_low_bits():
    t = OptionToggles()
    t.autocast = 0x0F
    assert [t.press("u", MAIN, PATCH) for _ in range(4)] == ["p074", "p075", "p073", "p074"]      # 0x08 -> 0x18 -> 0x38 -> 0x08 (+ 7 kept)
    assert t.autocast & 7 == 7
    assert t.press("x", MAIN, PATCH) is None


def test_gameui_option_key_shows_2000ms_system_line():
    ui = GameUi(Layout.for_size(640, 480), world(), 1, MAIN, MainText(), MainText(), patch=PATCH)
    assert ui.option_key("w", 10) and ui.option_key("q", 10) is False
    assert ui.messages.lines(10) == ("m05f",) and ui.messages.queue[0][1] == OPTION_MS == 2000 and ui.messages.queue[0][2] is None


def test_script_message_0xfa_is_patch_line_30s():
    w = world()
    ui = GameUi(Layout.for_size(640, 480), w, 1, MAIN, MainText(), MainText(), patch=PATCH)
    w.events.append(ScriptMessage(1, 0xFA))
    ui.poll(5)
    assert ui.messages.lines(5) == ("p061",) and ui.messages.queue[0][1] == SCRIPT_MS == 30000
