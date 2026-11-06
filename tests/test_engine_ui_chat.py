"""The chat input line (ui-layout 11.5): Enter opens it above the open bottom windows, typing echoes, Enter submits, Esc cancels, `#show map` is gated."""

import numpy as np

from engine.ui import GameUi, Layout, MainText
from engine.ui.chat import CHAT_MS, LINE_H, MAX_CHARS
from engine.sim import vision
from test_engine_death import world


def make(size=(800, 600)):
    w = world()
    return GameUi(Layout.for_size(*size), w, 1, MainText(), MainText(), MainText()), w


def type_text(ui, text):
    for ch in text:
        ui.chat_key("", ch, 0)


def test_enter_opens_line_at_bottom_and_blocks_other_keys():
    ui, _ = make()
    assert not ui.chat.open
    assert ui.key("return") and ui.chat.open
    assert ui.chat.rect == (0, 600 - LINE_H, 640, LINE_H)
    assert ui.key("tab") and ui.panel_mode == "picture"          # the key is swallowed while the line is open


def test_line_sits_above_open_bottom_windows():
    ui, _ = make()
    ui.book.open_book()
    ui.open_chat()
    assert ui.chat.y == 600 - (LINE_H + 85)
    ui.chat_key("escape", "", 0)
    ui.pack.open_pack()
    ui.open_chat()
    assert ui.chat.y == 600 - (LINE_H + 85 + 90)       # both bars open: heights add


def test_typing_echo_backspace_and_cursor():
    ui, _ = make()
    ui.key("return")
    type_text(ui, "hi!")
    assert ui.chat.text == "hi!" and ui.chat.shown_text() == "hi!_"
    ui.chat_key("backspace", "", 0)
    assert ui.chat.text == "hi"
    type_text(ui, "x" * 400)
    assert len(ui.chat.text) == MAX_CHARS


def test_escape_cancels_and_sends_nothing():
    ui, _ = make()
    ui.key("return")
    type_text(ui, "hello")
    assert ui.chat_key("escape", "", 5) == ("cancel",)
    assert not ui.chat.open and ui.messages.queue == []
    ui.key("return")
    assert ui.chat.text == ""                                     # cleared at every activation


def test_enter_sends_echo_line_with_sender_colour_and_history():
    ui, w = make()
    p = w.players[1]
    ui.key("return")
    type_text(ui, "hello")
    assert ui.chat_key("return", "", 7) == ("send", "hello")
    assert not ui.chat.open
    (text, ms, col), = ui.messages.queue
    assert text == "%s: hello" % p.name and ms == CHAT_MS == 10000 and col == ("player", p.colour)
    ui.key("return")
    ui.chat_key("up", "", 8)
    assert ui.chat.text == "hello"


def test_empty_enter_closes_without_a_message():
    ui, _ = make()
    ui.key("return")
    ui.chat_key("return", "", 0)
    assert not ui.chat.open and ui.messages.queue == []


def test_cheat_commands_are_gated_by_the_cheat_level():
    ui, w = make()
    w.fog = np.zeros(w.fog.shape if getattr(w, "fog", None) is not None else (4, 4), dtype=w.fog.dtype if getattr(w, "fog", None) is not None else np.uint16)
    before = w.fog.copy()
    ui.key("return")
    type_text(ui, "#show map")
    ui.chat_key("return", "", 0)
    assert (w.fog == before).all() and ui.messages.queue == []   # level 0: refused, and a '#' text is never echoed
    ui.cheat_level = 0x33
    ui.key("return")
    type_text(ui, "#show map")
    ui.chat_key("return", "", 0)
    assert (w.fog & vision.v.IN_SIGHT).all() and ui.messages.queue == []
