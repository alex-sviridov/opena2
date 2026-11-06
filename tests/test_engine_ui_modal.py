"""Modal windows and GameUi (docs/engine/ui-layout.md 11.4, 11.5): menu, End Quest, pause, story, result dialogs, freeze, messages.  Synthetic."""

from engine.sim import campaign
from engine.sim.triggers import MissionComplete, ScriptMessage
from engine.ui import GameUi, Layout, MainText, MessageLine, modal
from engine.ui.messages import PickupWatch
from engine.world import Player

from allods2.formats import saves as S
from test_engine_death import hero, unit, world

MAIN = MainText(["m%02x" % i for i in range(0x140)])
DIALOGS = MainText(["d%02x" % i for i in range(0xA0)])
PATCH = MainText(["p%02x" % i for i in range(0x80)])
MISSION = ("#briefing\r\nx\r\n#\r\n#event1\r\n<NPC=21, IAMMALE, IAMFIGHTER, PART=1>\r\nmale fighter\r\n<NPC=21, IAMFEMALE, IAMFIGHTER, PART=1>\r\nfemale fighter\r\n"
           "<NPC=21, IAMMALE, IAMMAGE, PART=1>\r\nmale mage\r\n#\r\n#event2\r\n<npc=623, part=1>\r\nhello\r\n<NPC=21, IAMMALE, IAMFIGHTER, PART=3>\r\nreply\r\n#\r\n")


def make(w=None, mission=MISSION, size=(640, 480)):
    w = w or world()
    w.players[1].main_hero = hero(w, 9, 5, 5).id
    return GameUi(Layout.for_size(*size), w, 1, MAIN, DIALOGS, MainText(), mission, patch=PATCH), w


def test_escape_opens_the_menu_and_return_to_game_closes_it():
    ui, w = make()
    assert not ui.frozen
    assert ui.key("escape") and ui.modals.kinds() == ("menu",) and ui.frozen
    assert ui.key("escape") and not ui.frozen                      # ESC in the menu = message 0x446, Return to Game
    ui.open_menu()
    assert [b.label for b in ui.modals.top.buttons] == ["d22", "d23", "d24", "d25", "d26", "d27", "d28"]
    assert ui.key("r") and ui.frozen                               # the synthetic labels have no ~R: the key is consumed, nothing happens
    ui.modals.clear()


def test_menu_entries_follow_the_exes_order_hotkeys_and_states():
    lay = Layout.for_size(640, 480)
    labels = MainText(["~Save Game" if i == 0x22 else "~Load Game" if i == 0x23 else "Game ~Options" if i == 0x24 else "Sou~nd Options" if i == 0x25
                       else "~Quest Objectives" if i == 0x26 else "~End Quest" if i == 0x27 else "~Return to Game" if i == 0x28 else "?" for i in range(0x40)])
    d = modal.menu_dialog(lay, labels.line)
    assert [b.key for b in d.buttons] == ["s", "l", "o", "n", "q", "e", "r"]
    assert [b.enabled for b in d.buttons] == [False] * 5 + [True, True]             # DECISION: the windows of phase K are disabled
    assert d.key("e") == ("open", "endquest") and d.key("s") is None and d.key("r") == modal.RETURN and d.key("escape") == modal.RETURN
    f = d.frame
    assert [b.rect.y - f.y for b in d.buttons] == [0x28 + 0x1E * k for k in range(7)]      # CONFIRMED start y 0x28 (`0x4400d7` rect arg)


def test_end_quest_victory_is_disabled_until_the_mission_is_complete_and_exits_end_the_game():
    ui, w = make()
    ui.open_menu()
    ui.apply(("open", "endquest"))
    d = ui.modals.top
    assert d.kind == "endquest" and [b.enabled for b in d.buttons] == [False, True, True, True]
    assert d.click((d.buttons[0].rect.x + 3, d.buttons[0].rect.y + 3)) is None             # disabled
    assert d.key("escape") == modal.RETURN
    w.mission_complete = True
    ui.modals.clear()
    ui.open_menu()
    ui.apply(("open", "endquest"))
    assert ui.modals.top.buttons[0].enabled
    b = ui.modals.top.buttons[1]                                  # Exit to Main Menu
    assert ui.mouse_down((b.rect.x + 2, b.rect.y + 2))[0] and ui.quit is None
    assert ui.mouse_up((b.rect.x + 2, b.rect.y + 2)) and ui.quit == "menu" and not ui.frozen
    ui, w = make()
    ui.open_menu()
    ui.apply(("open", "endquest"))
    b = ui.modals.top.buttons[2]
    ui.mouse_down((b.rect.x + 2, b.rect.y + 2))
    ui.mouse_up((0, 0))                                           # released off the button: nothing
    assert ui.quit is None and ui.frozen
    ui.mouse_down((b.rect.x + 2, b.rect.y + 2))
    ui.mouse_up((b.rect.x + 2, b.rect.y + 2))
    assert ui.quit == "windows"


def test_pause_key_opens_the_notice_and_a_second_press_closes_it_but_not_inside_other_dialogs():
    ui, w = make()
    assert ui.key("pause") and ui.modals.kinds() == ("pause",) and ui.frozen
    assert ui.modals.top.text == "m77"
    assert ui.key("pause") and not ui.frozen
    ui.toggle_pause()
    assert ui.key("escape") and not ui.frozen                       # ESC closes the notice
    ui.toggle_pause()
    ok = ui.modals.top.buttons[0]
    ui.mouse_down((ok.rect.x + 1, ok.rect.y + 1))
    ui.mouse_up((ok.rect.x + 1, ok.rect.y + 1))
    assert not ui.frozen
    ui.open_menu()
    assert not ui.toggle_pause() and ui.modals.kinds() == ("menu",)     # Pause needs game mode 1
    assert not ui.open_menu() or ui.modals.kinds() == ("menu",)


def test_every_click_is_taken_by_the_dialog_and_tab_toggles_the_panel_mode():
    ui, w = make()
    assert ui.panel_mode == "picture" and ui.key("tab") and ui.panel_mode == "text" and ui.key("tab") and ui.panel_mode == "picture"
    assert not ui.key("a") and ui.key("return") and ui.chat.open     # letters go to OrderInput, Enter opens the chat line
    ui.chat_key("escape", "", 0)
    ui.open_menu()
    assert ui.mouse_down((10, 10)) == (True, None)
    assert ui.key("tab") and ui.panel_mode == "picture"              # a dialog swallows TAB
    ui.modals.clear()
    lay = ui.layout
    mode = (lay.info_panel.rect.x + 0x90, lay.info_panel.rect.y + 10)
    assert ui.info_release(mode) and ui.panel_mode == "text"
    menu = (lay.info_panel.rect.x + 0x80, lay.info_panel.rect.y + 0xD0)
    assert ui.info_release(menu) and ui.modals.kinds() == ("menu",)         # the disk button
    ui.modals.clear()
    assert ui.mouse_down((20, 20)) == (False, None)


def test_menu_button_still_works_with_a_foreign_selection_in_a_mission():
    """`FUN_004aebc8`: the disk posts 0x416 whenever the game mode has bit 1; the arrows replace it only in the town modes (0x226), never in a mission."""
    ui, w = make()
    other = unit(w, 3, 8, 8, owner=2)
    w.players[1].selection = (other.id,)
    lay = ui.layout
    menu = (lay.info_panel.rect.x + 0x80, lay.info_panel.rect.y + 0xD0)
    assert ui.world_state() == "foreign" and ui.info_release(menu) and ui.modals.kinds() == ("menu",)


def test_script_messages_open_the_story_window_or_queue_behind_a_dialog():
    ui, w = make()
    w.events.append(ScriptMessage(0, 1))
    ui.poll(0)
    assert ui.modals.kinds() == ("story",) and ui.modals.top.text == "male fighter" and w.events == []
    w.events.append(ScriptMessage(1, 2))
    ui.poll(1)
    assert ui.queue == [2] and ui.modals.kinds() == ("story",)       # a modal is open: the number waits (exe list 0x627170)
    ui.key("escape")                                                 # closes the story; the queued one follows
    assert ui.modals.kinds() == ("story",) and ui.modals.top.text == "hello" and ui.queue == []
    ui.modals.clear()
    w.events.append(ScriptMessage(2, 0xFD))
    ui.poll(2)
    assert not ui.frozen                                              # sounds only
    w.events.append(ScriptMessage(3, 0xFA))
    ui.poll(3)
    assert ui.messages.lines(3) == ("p61",) and ui.messages.queue[0][1] == 30000
    w.events.append(ScriptMessage(4, 99))
    ui.poll(4)
    assert ui.modals.kinds() == ("story",) and ui.modals.top.text == "Nothing to say"      # no such section: the window with its initial text (`FUN_0041d15e`)


def click(ui, b):
    ui.mouse_down((b.rect.x + 2, b.rect.y + 2))
    ui.mouse_up((b.rect.x + 2, b.rect.y + 2))


def test_mission_complete_dialog_is_the_menu_class_window_with_victory_and_continue():
    ui, w = make()
    w.mission_complete = True
    assert ui.poll(0) == 1 and ui.modals.kinds() == ("complete",) and ui.modals.top.text == "m8c"
    assert ui.poll(1) == 0
    d = ui.modals.top
    f = d.frame
    assert (f.w, f.h) == (296, 168) and (f.x, f.y) == (172, 156)                              # CONFIRMED `0x44da0f` rect 384x180 snapped, centred on 640x480
    assert [(b.rect.x - f.x, b.rect.y - f.y, b.rect.w, b.rect.h) for b in d.buttons] == [(0x28, 84, 208, 24), (0x28, 108, 208, 24)]      # stack from `h - 0x60`, 24 high
    assert [b.label for b in d.buttons] == ["d2b", "d9a"] and [b.key for b in d.buttons] == ["v", "c"]
    assert (d.text_rect.x - f.x, d.text_rect.y - f.y, d.text_rect.w, d.text_rect.h) == (0x28, 0x20, 0xC0, 0x30) and d.align == "center" and d.table == "normal"
    assert d.key("escape") == modal.RETURN and ui.quit is None                                    # ESC = Continue
    assert d.key("return") == ("quit", "victory") and d.key("up") == modal.NOOP and d.key("return") == modal.RETURN      # Enter = the focused button: Victory! first (`FUN_004dc232`), Up / Down move it (`FUN_00440082`)
    assert d.key("down") == modal.NOOP and d.key("return") == ("quit", "victory")
    assert d.key("c") == modal.RETURN and d.key("v") == ("quit", "victory")
    click(ui, d.buttons[1])                                                                        # Continue: the window closes, the mission goes on
    assert not ui.frozen and ui.quit is None and ui.poll(2) == 0
    ui, w = make()
    w.mission_complete = True
    ui.poll(0)
    click(ui, ui.modals.top.buttons[0])                                                            # Victory!
    assert ui.quit == "victory"


def test_mission_failed_dialog_is_a_text_window_with_two_stacked_buttons_and_the_plus_0x40_quirk():
    ui, w = make()
    w.players[1].defeat_dialog = True
    w.players[1].death_code = 2
    assert ui.poll(0) == 1 and ui.modals.kinds() == ("failed",)
    d = ui.modals.top
    f = d.frame
    assert d.caption == "m8d" and d.text == "m11a" and d.lines == ("m11a",)                        # caption `main 0x8d`; no `#failure2` section: the default `main 0x118 + 2`
    assert (f.w, f.h) == (488, 232) and f.x == 76 and f.y == (480 - 168) // 2                      # centred with 168, then `bottom += 0x40` (`0x44d263`): 32 px low
    assert [(b.rect.x - f.x, b.rect.y - f.y, b.rect.w, b.rect.h) for b in d.buttons] == [(61, 136, 366, 24), (61, 160, 366, 24)]      # w/8 .. 7w/8, h-0x60 / h-0x48
    assert (d.caption_rect.x - f.x, d.caption_rect.y - f.y) == (0x28, 0x30) and d.align == "left"
    assert ui.poll(1) == 0 and ui.key("escape") and ui.frozen and ui.quit is None                   # ESC = message 0x446 (Load Game, unbuilt): nothing happens
    assert d.key("return") == ("quit", "defeat")                                                     # Enter = the first button in child order, Exit to Main Menu (`FUN_004d460b`)
    load = d.buttons[1]
    assert not load.enabled and d.click((load.rect.x + 1, load.rect.y + 1)) is None                 # Load Game stays disabled in J1
    click(ui, d.buttons[0])
    assert ui.quit == "defeat"


def test_failed_window_grows_with_a_reason_text_one_snap_step_at_a_time():
    wrap = lambda t, width: t.split("\n")
    lay = Layout.for_size(640, 480)
    heights = [modal.failed_dialog(lay, MAIN.line, DIALOGS.line, "\n".join("w" * (k + 1) for k in range(n)), wrap).frame.h for n in (0, 1, 2, 3, 6)]
    assert heights == [232, 232, 296, 296, 360]          # 0x90 + 0x44 + 17 n snapped, + 0x40; 6 lines overflow the text rect (15 n > 88): scroll bar, the rect keeps its height


def test_pause_window_height_follows_the_wrapped_text():
    lay = Layout.for_size(640, 480)
    one = modal.pause_dialog(lay, MAIN.line)
    assert (one.frame.w, one.frame.h) == (488, 168) and (one.frame.x, one.frame.y) == (76, 156)       # 0x90 + 0x38 + 17 snapped
    ok = one.buttons[0].rect
    assert (ok.x - one.frame.x, ok.y - one.frame.y, ok.w, ok.h) == (488 // 2 - 0x30, 168 - 0x3C, 96, 24)
    assert one.align == "left" and one.lines == ("m77",) and one.text_rect.h == 17
    wrap3 = lambda t, width: ["a", "b", "c"]
    three = modal.pause_dialog(lay, MAIN.line, wrap3)
    assert three.frame.h == 232 and three.frame.y == (480 - 232) // 2 and three.buttons[0].rect.y - three.frame.y == 232 - 0x3C


def test_modal_stack_is_bottom_first_and_any_dialog_freezes():
    st = modal.ModalStack()
    assert st.top is None and not st.frozen and st.pop() is None and st.kinds() == ()
    lay = Layout.for_size(640, 480)
    a, b = modal.menu_dialog(lay, DIALOGS.line), modal.pause_dialog(lay, MAIN.line)
    st.push(a)
    st.push(b)
    assert st.top is b and st.frozen and st.kinds() == ("menu", "pause")
    assert st.pop() is b and st.top is a and st.frozen
    st.push(b)
    st.clear()
    assert st.top is None and not st.frozen and st.kinds() == ()


def test_result_dialogs_keep_the_campaign_flow_state():
    ui, w = make()
    w.mission_complete = True
    ui.poll(0)
    assert w.mission_ended is True and isinstance(w.dialog, campaign.Dialog) and w.dialog.kind == "complete"


def test_gold_and_item_pickup_lines():
    w = world()
    h = hero(w, 1, 5, 5)
    watch = PickupWatch(w, 1)
    assert watch.poll(w, MAIN) == []
    w.players[1].gold += 25
    assert watch.poll(w, MAIN) == [("m58 25 m59", "normal", 3000)]
    assert watch.poll(w, MAIN) == []
    h.pack = (S.Item(0x104, 1, 0, (), True),)
    got = watch.poll(w, MAIN)
    assert got == [("m55 item 0x104", "normal", 3000)]             # no item table in a synthetic world: the code stands in for the name
    h.pack = (S.Item(0x104, 3, 0, (), True),)
    assert watch.poll(w, MAIN) == [("m55 item 0x104 (m56 3 m57)", "normal", 3000)]
    h.pack = (S.Item(0x104, 3, 0, (), False), S.Item(0x105, 1, 0, ()))        # items that are not flagged new (equip, drop) say nothing
    assert watch.poll(w, MAIN) == []


def test_message_entries_carry_the_colour_slot_and_the_lifetime_rule_stays():
    m = MessageLine()
    m.show("a", 0, 3000, "normal")
    m.show("b", 0, 3000)
    assert m.entries(10) == (("a", "normal"), ("b", None))
    assert m.entries(3011) == (("b", None),)                         # only the first line has a clock


def test_a_fresh_mission_starts_with_both_bottom_bars_closed():
    ui, w = make()
    assert not ui.book.open and not ui.pack.open                    # CONFIRMED `FUN_00483129`: built, never attached (ui-layout 1-2)


def test_the_result_dialogs_close_an_open_spell_book_but_not_the_inventory():
    ui, w = make()
    ui.key("b")
    ui.toggle_pack()
    assert ui.book.open and ui.pack.open
    w.mission_complete = True
    assert ui.poll(0) == 1
    assert not ui.book.open and ui.pack.open                        # `0x42a` -> `FUN_0048aea8` -> `FUN_0041b077` (book only)
    ui, w = make()
    ui.key("b")
    assert ui.book.open
    assert ui._open_failed() == 1 and not ui.book.open              # `0x42b` -> `FUN_0048b885`


FAIL = "#briefing\r\nx\r\n#\r\n#failure2 \r\nHero died\r\n#\r\n#failure3\r\nIgles\r\nsecond line\r\n# \r\n#failure5\r\nSword\r\n#\r\n#event1\r\nx\r\n"


def test_failure_reason_list_follows_the_exes_table_with_defaults_for_2_to_4():
    from engine.ui import story
    assert story.failure_texts(FAIL, MAIN.line) == ["Hero died", "Igles\nsecond line", "m11c", "Sword"]      # #failure4 missing: main 0x11c; #failure6 missing and n >= 5: end
    assert story.failure_texts(None, MAIN.line) == ["m11a", "m11b", "m11c"]
    assert [story.failure_text(FAIL, MAIN.line, c) for c in (1, 2, 3, 4, 5, 6)] == ["", "Hero died", "Igles\nsecond line", "m11c", "Sword", ""]


def test_failed_window_shows_the_reason_of_the_players_death_code():
    ui, w = make(mission=FAIL)
    w.players[1].defeat_dialog = True
    w.players[1].death_code = 5
    ui.poll(0)
    assert ui.modals.top.text == "Sword"
    ui, w = make(mission=FAIL)
    w.players[1].defeat_dialog = True
    w.players[1].death_code = 3
    ui.poll(0)
    assert ui.modals.top.lines == ("Igles", "second line") and ui.modals.top.escape == modal.NOOP
