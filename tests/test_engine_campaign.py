"""The end-of-mission flow, Scenario.dll's start values, the by-name hero look-up, instant 22's loop, the ready message and the
'already on the map' test (docs/engine/triggers.md sections 2.1, 8, 9, 10, 11).  Synthetic, always run."""

from allods2.formats import scenario as S
from engine import party as PT
from engine.sim import campaign as C
from engine.sim import triggers as T
from engine.world import Player

from test_engine_ai import hero, run, unit, world
from test_engine_party import Assets
from test_engine_triggers import TRUE, rec, script, setup


# --- Scenario.dll start values (item 5) --------------------------------------------------------------------------------------------

def test_a_new_game_has_every_variable_zero_except_the_chapter_10():
    assert C.new_game_vars() == {0x300: 10}
    c = C.Campaign.new_game()
    assert c.get(0x300) == 10 and c.get(0x123) == 0 and c.location == (C.TOWN, 1) and c.available == [(C.TOWN, 1)]


def test_the_script_runtime_starts_with_the_scenario_dll_values_and_the_dump_ignores_them():
    w, sim, *_ = setup(script([], [rec(23, 1, (S.K_INT, 0x300))], []))
    assert w.script.scenario_vars == {0x300: 10}
    T.eval_check(w, w.script, w.script.checks[0])
    assert w.script.values[0] == 10                                 # check 23 = ScenarioGetVar(0x300)
    assert "vars" not in w.script.dump()
    w.script.scenario_vars[0x301] = 4
    assert w.script.dump()["vars"] == [(0x300, 10), (0x301, 4)]


def test_entering_a_location_zeroes_the_16_sub_objectives():
    c = C.Campaign.new_game()
    c.set(0x2F0, 1)
    c.set(0x2FF, 3)
    c.set(0x300 - 0, 10)
    c.set(0x30F, 5)
    c.enter((C.MISSION, 10))
    assert c.get(0x2F0) == c.get(0x2FF) == 0 and c.get(0x30F) == 5 and c.get(0x300) == 10


# --- ScenarioLeaveLocation and the next screen (item 4) --------------------------------------------------------------------------------

def finish(mission, camp=None, **kw):
    w = world()
    w.mission_complete = True
    camp = camp or C.Campaign.new_game()
    camp.available.append((C.MISSION, mission))
    camp.enter((C.MISSION, mission))
    dlg = C.poll(w, camp)
    return w, camp, dlg


def test_mission_complete_opens_a_one_button_dialog_and_continue_runs_leave_location():
    w, camp, dlg = finish(10)
    assert dlg.kind == "complete" and [b.command for b in dlg.buttons] == [0x41D] and w.mission_ended
    assert C.poll(w, camp) is dlg                                   # still open
    w.tick = 16 * 7 + 3
    out = C.press(w, camp, 0x41D)
    assert w.dialog is None and camp.times == [7]
    assert camp.get(0x380 + 10) == 1 and camp.get(0x300) == 20      # mission 10 done, the chapter +10
    assert out.cutscene == 1 and (C.MISSION, 20) in camp.available and (C.MISSION, 10) not in camp.available
    assert out.kind == "world_map"                                  # town 1 is still in the available list


def test_a_town_in_the_list_sends_the_player_to_the_world_map_else_the_first_location_starts():
    w, camp, _ = finish(10)
    camp.available.insert(0, (C.TOWN, 1))
    assert C.press(w, camp, 0x41D).kind == "world_map"
    w, camp, _ = finish(10)
    camp.available = [x for x in camp.available if x[0] != C.TOWN]
    out = C.press(w, camp, 0x41D)
    assert out.kind == "mission" and out.location == (C.MISSION, 20) and camp.location == (C.MISSION, 20)


def test_mission_110_ends_the_campaign_with_the_cutscene_by_variable_0x30b():
    for v30b, code in ((0, 4), (1, 5)):
        camp = C.Campaign.new_game()
        camp.set(0x300, 0x6E)
        camp.set(0x30B, v30b)
        w, camp, dlg = finish(110, camp)
        assert dlg.kind == "complete"                                 # the chapter is still 110 < 0x78 when the message arrives
        out = C.press(w, camp, 0x41D)
        assert (out.kind, out.cutscene, camp.get(0x300)) == ("ending", code, 0x78)


def test_a_chapter_at_0x78_skips_the_dialog():
    camp = C.Campaign.new_game()
    camp.set(0x300, 0x78)
    w, camp, out = finish(110, camp)
    assert out.kind == "ending" and w.dialog is None and w.mission_ended


def test_mission_40_recruits_the_mage_hero_and_a_script_value_of_var_0x305_is_erased_by_the_leave():
    w, camp, _ = finish(40)
    camp.set(0x305, 22)                                             # a script wrote it during the mission
    assert C.press(w, camp, 0x41D).recruit == 0x17
    w, camp, _ = finish(31)
    camp.set(0x305, 22)
    assert C.press(w, camp, 0x41D).recruit == 0
    assert (C.MISSION, 32) in camp.available


def test_leaving_the_menu_without_a_result_is_the_main_menu():
    w = world()
    camp = C.Campaign.new_game()
    assert C.press(w, camp, 0x41D).kind == "main_menu" and camp.times == []


def test_the_defeat_dialog_opens_once_and_has_menu_and_load_buttons():
    w = world()
    camp = C.Campaign.new_game()
    w.players[1].defeat_dialog = True
    dlg = C.poll(w, camp, saves_exist=False)
    assert dlg.kind == "defeat"
    assert [(b.command, b.enabled) for b in dlg.buttons] == [(0x445, True), (0x446, False)]
    assert C.press(w, camp, 0x446) is None and w.dialog is dlg      # the disabled load button does nothing
    assert C.press(w, camp, 0x445).kind == "main_menu" and w.dialog is None
    assert C.poll(w, camp) is None                                  # the latch +0x3e8 keeps it from opening again
    C.start_game(w)
    assert C.poll(w, camp, saves_exist=True).buttons[1].enabled     # a new game clears the latches


def test_the_load_button_opens_the_load_window_when_saves_exist():
    w = world()
    camp = C.Campaign.new_game()
    w.players[1].defeat_dialog = True
    C.poll(w, camp, saves_exist=True)
    assert C.press(w, camp, 0x446).kind == "load"


def test_the_trigger_pass_sets_the_mission_complete_flag_and_the_dialog_follows():
    w, sim, *_ = setup(script([rec(4, 1)], TRUE, [T_always()]))
    run(sim, 16 + 16)
    assert w.mission_complete and w.script.complete == 1
    assert C.poll(w, C.Campaign.new_game()).kind == "complete"


def T_always():
    from test_engine_triggers import ALWAYS, trig
    return trig(ALWAYS, [1])


def test_message_actions_of_window_message_0x433():
    assert C.message_action(0xFF) == (("defeat",),)
    assert C.message_action(0xFE) == (("sound", 0x10, 0xDC),)
    assert C.message_action(0xFA)[1] == ("line", 0x61, 30000)
    assert C.message_action(7) == (("text", "event7"),) and C.message_action(7, modal=True) == (("queue", 7),)


# --- the by-name second loop of FUN_00562518 (item 3) ---------------------------------------------------------------------------------

class C_:
    def __init__(self, name, k):
        self.name, self.k = name, k
        self.human, self.server_id = True, (k + 0x15) * 10 + 10000


def test_named_creatures_are_searched_and_the_creature_after_a_named_mismatch_is_skipped():
    a, b, c = C_("Ann", 5), C_("Bob", 1), C_("Cid", 2)
    assert T.find_named_hero([a, b, c], 1) is None                  # b follows the named mismatch a: skipped
    assert T.find_named_hero([a, b, c], 2) is c                      # c follows a, b: a mismatch skips b, c is looked at
    d = C_("", 3)
    assert T.find_named_hero([d, C_("Eve", 3)], 3).name == "Eve"     # an unnamed creature skips nothing
    assert T.find_named_hero([C_("", 1)], 1) is None                 # unnamed creatures never match
    assert T.find_named_hero([C_("Zed", 4), C_("Y", 4)], 4).name == "Zed"


def test_a_hero_owned_by_another_player_resolves_by_name_when_the_human_has_a_main_hero():
    w = world()
    h = hero(w, 1, 20, 24)
    w.players[1].main_hero = h.id
    m = unit(w, 2, 30, 24, 3)
    m.human, m.server_id, m.name = True, 10230, "Mage"               # Mage_Hero held by player 3 (map 40)
    T.enable(w, script([], [rec(5, 1, (S.K_UNIT, 10003))], []))
    assert w.script.checks and w.script.checks[0].unit is m and w.script.errors == []
    w2 = world()
    h2 = hero(w2, 1, 20, 24)
    w2.players[1].main_hero = h2.id
    m2 = unit(w2, 2, 30, 24, 3)
    m2.human, m2.server_id = True, 10230                             # no name: not found
    T.enable(w2, script([], [rec(5, 1, (S.K_UNIT, 10003))], []))
    assert "Can't resolve hero 10003" in w2.script.errors


# --- instant 22 (item 5) -----------------------------------------------------------------------------------------------------------

def test_instant_22_changes_the_owner_of_every_member_of_the_group():
    w, sim, h, a, b = setup(script([rec(22, 1, (S.K_GROUP, 1), (S.K_PLAYER, 1))], [], []))
    c3 = unit(w, 4, 32, 24, 2, 1)
    T.run_instant(w, w.script, 0)
    assert a.owner == 1 and b.owner == 1                              # the walking iterator holds the next position: no member is skipped
    assert w.groups[a.order_group] is not w.groups[b.order_group]    # each member got a group of its own (FUN_004f0568)


# --- the ready message and the roster test (item 2) --------------------------------------------------------------------------------

def test_on_map_is_the_ground_occupant_of_the_units_own_cell():
    w = world()
    u = unit(w, 1, 20, 20, 1)
    assert PT.on_map(w, u)
    w.slots.occ[0].clear()                                            # a first-come loser holds no occupant slot: placed again by the exe
    assert not PT.on_map(w, u)


def test_party_is_placed_before_the_first_tick_and_the_script_compiles_against_it():
    w = world()
    sc = script([rec(0x10002, 1, (S.K_X, 24), (S.K_Y, 24))], [rec(5, 1, (S.K_UNIT, 10001))], [])
    T.enable(w, sc, assets=Assets())
    h = w.units[w.players[1].main_hero]
    assert (h.x, h.y) == (24, 24) and w.tick == 0 and w.script.errors == []
    assert w.script.checks[0].unit is h                               # the roster hero exists before the first step (FUN_004f2c83 runs in step 1's drain)
