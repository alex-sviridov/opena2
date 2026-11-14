"""L4, the town core (docs/engine/town.md 1-2): the mask arithmetic, the guards and every edge of the visit's state machine over the campaign's Scenario
state.  Synthetic: no install needed."""

import pytest

from engine import town as T
from engine.sim import campaign as C


def core(*available, loc=None, chapter=10, v301=0):
    camp = C.Campaign()
    camp.available = list(available)
    camp.vars[C.CHAPTER] = chapter
    if v301:
        camp.set(0x301, v301)
    if loc is not None:
        camp.enter(loc)
    return T.TownCore(camp)


def in_scene(town=1, v301=1):
    c = core((C.TOWN, town), loc=(C.TOWN, town), v301=v301)
    c.send(T.MSG_ENTER)
    c.take_events()
    return c


def test_window_table():
    assert {t: (w.scene, w.inn, w.shop, w.music) for t, w in T.TOWNS.items()} == {
        1: (0x110, 0x104, 0xf8, "town1"), 2: (0x118, 0x10c, 0x100, "town2"), 3: (0x114, 0x108, 0xfc, "town3")}


def test_entering_a_town_builds_its_scene_with_mask_zero():
    for n, music in ((1, "town1"), (2, "town2"), (3, "town3")):
        c = core((C.TOWN, n), loc=(C.TOWN, n))
        c.send(T.MSG_ENTER)
        assert (c.view, c.town, c.mask) == ("scene", n, 0) and c.take_events() == [("music", music)]


def test_unknown_town_and_missing_location_are_errors():
    with pytest.raises(T.TownError):
        core(loc=(C.TOWN, 9)).send(T.MSG_ENTER)
    with pytest.raises(T.TownError):
        core().send(T.MSG_ENTER)


def test_inn_opens_from_the_scene_and_sets_bit_4():
    c = in_scene(2)
    c.send(T.MSG_INN)
    assert (c.view, c.mask) == ("inn", T.M_INN) and c.take_events() == [("inn", 2)] and c.shows_hero_arrows


def test_shop_opens_and_sets_bit_2():
    c = in_scene(3)
    c.send(T.MSG_SHOP)
    assert (c.view, c.mask) == ("shop", T.M_SHOP) and c.take_events() == [("shop", 3)] and c.shows_hero_arrows


def test_entry_guard_second_click_does_nothing():
    c = in_scene()
    c.send(T.MSG_INN)
    c.take_events()
    c.send(T.MSG_SHOP)                          # mask is 4: the guard drops it
    c.send(T.MSG_INN)
    assert (c.view, c.mask) == ("inn", T.M_INN) and c.events == []


def test_no_open_from_the_map_or_a_mission():
    c = core((C.TOWN, 1))
    c.open_map()
    c.send(T.MSG_INN)
    c.send(T.MSG_SHOP)
    assert (c.view, c.mask) == ("map", T.M_MAP)


def test_close_chain_returns_to_the_scene_with_its_music():
    for opener, name in ((T.MSG_INN, "inn"), (T.MSG_SHOP, "shop")):
        c = in_scene(3)
        c.send(opener)
        c.take_events()
        c.close_window()
        assert (c.view, c.mask, c.town) == ("scene", 0, 3) and c.take_events() == [("music", "town3")], name


def test_close_returns_to_the_scene_only_when_the_mask_is_exactly_the_windows_bit():
    c = in_scene()
    c.send(T.MSG_INN)
    c.mask |= T.M_MODAL                         # a modal dialog is up as well: bit 4 clears, no 0x42e
    c.take_events()
    c.close_window()
    assert c.mask == T.M_MODAL and c.view == "inn" and c.events == []


def test_close_with_nothing_open_does_nothing():
    c = in_scene()
    c.close_window()
    assert (c.view, c.mask) == ("scene", 0) and c.events == []


def test_leave_human_town_needs_var_0x301():
    c = in_scene(1, v301=0)
    c.leave_town()
    assert c.view == "scene" and c.take_events() == [("speech", "plagatguard")] and c.camp.location == (C.TOWN, 1)


def test_leave_autosaves_9998_leaves_the_location_and_starts_the_intro_walk():
    c = in_scene(1, v301=1)
    c.leave_town()
    assert c.take_events() == [("autosave", 9998), ("music", "map")]
    assert (c.view, c.mask, c.town, c.intro) == ("map", T.M_MAP, None, True)
    assert c.camp.location is None and (C.TOWN, 1) not in c.camp.available and c.party_point == (C.TOWN, 1)


def test_other_towns_leave_without_the_gate_and_without_intro():
    for n in (2, 3):
        c = in_scene(n, v301=0)
        c.leave_town()
        assert (c.view, c.intro) == ("map", False) and ("autosave", 9998) in c.events
        assert (C.TOWN, n) in c.camp.available                 # only town 1 leaves the list


def test_leave_from_an_inn_is_refused():
    c = in_scene()
    c.send(T.MSG_INN)
    c.take_events()
    c.leave_town()
    assert c.view == "inn" and c.events == []


def test_walk_to_a_mission_autosaves_9999_and_sets_bit_1():
    c = core((C.MISSION, 10))
    c.open_map()
    c.take_events()
    assert c.walk_to((C.MISSION, 10))
    assert (c.view, c.mask, c.intro, c.party_point) == ("mission", T.M_MISSION, False, (C.MISSION, 10))
    assert c.take_events() == [("autosave", 9999), ("mission", 10)] and c.camp.location == (C.MISSION, 10)


def test_walk_to_a_town_builds_the_scene_and_clears_the_map_bit():
    c = core((C.TOWN, 2), (C.MISSION, 20))
    c.open_map()
    c.take_events()
    assert c.walk_to((C.TOWN, 2))
    assert (c.view, c.mask, c.town) == ("scene", 0, 2) and c.take_events() == [("music", "town2")]


def test_walk_needs_the_map_and_an_available_location():
    c = core((C.MISSION, 10))
    assert not c.walk_to((C.MISSION, 10))                      # the map is not open
    c.open_map()
    assert not c.walk_to((C.MISSION, 99)) and c.view == "map"


def test_mission_over_to_the_map():
    c = core((C.TOWN, 2))
    c.mask = T.M_MISSION
    c.mission_over(C.Outcome("world_map"))
    assert (c.view, c.mask) == ("map", T.M_MAP) and c.events == [("music", "map")]


def test_mission_over_without_a_town_starts_the_head_mission_at_once():
    c = core((C.MISSION, 20), loc=(C.MISSION, 20))              # complete() already entered the head
    c.mask = T.M_MISSION
    c.mission_over(C.Outcome("mission", -1, 0, (C.MISSION, 20)))
    assert (c.view, c.mask) == ("mission", T.M_MISSION)
    assert c.events == [("autosave", 9999), ("mission", 20)]    # the map is never shown


def test_mission_over_ending_and_cutscene_and_main_menu():
    c = core()
    c.mask = T.M_MISSION
    c.mission_over(C.Outcome("ending", 4))
    assert (c.view, c.mask) == ("ending", 0) and c.events == [("cutscene", 4)]
    c2 = core()
    c2.mission_over(C.Outcome("main_menu"))
    assert c2.view == "menu" and c2.events == []


def test_the_whole_visit_loop_through_the_real_completion():
    """town 1 -> leave -> map -> mission 10 -> won (the real `complete`) -> map -> town 2 -> inn -> back -> leave."""
    camp = C.Campaign.new_game()
    camp.set(0x301, 1)
    camp.available = [(C.TOWN, 1)]
    c = T.TownCore(camp)
    c.send(T.MSG_ENTER)
    c.leave_town()
    camp.available.append((C.MISSION, 10))                      # what the town's talk did
    assert c.walk_to((C.MISSION, 10))
    camp.available.append((C.TOWN, 2))                          # a town is available: the map is shown
    out = C.complete(camp, 100)                                 # mission 10 won: unlocks 20, cutscene 1
    c.mission_over(out)
    assert c.view == "map" and ("cutscene", 1) in c.events and (C.MISSION, 20) in camp.available
    assert c.walk_to((C.TOWN, 2)) and c.view == "scene"
    c.send(T.MSG_INN)
    c.close_window()
    c.leave_town()
    assert c.view == "map" and c.mask == T.M_MAP and not c.intro


def test_edges_cover_every_view_move():
    assert set(T.EDGES) == {("map", "walk"), ("scene", "inn"), ("scene", "shop"), ("scene", "leave"), ("inn", "close"), ("shop", "close"),
                            ("mission", "over")}


# -- the shell screens over the core (placeholders, no install) -----------------------------------------------------------------------------

def shell_in_map(available):
    """A shell on the `locations` screen with a synthetic campaign (no files: the screens never read the install here)."""
    from engine.campaign import CampaignGame
    from engine.shell import Services, Shell
    from engine.shell.events import Move, Press, Release  # noqa: F401
    saves, music, lines = [], [], []
    sh = Shell(None, services=Services(autosave=saves.append, music=music.append, log=lines.append))
    sh.campaign = CampaignGame()
    sh.campaign.camp.available = list(available)
    sh.start("locations")
    return sh, saves, music


def click_button(sh, label):
    """A placeholder town screen's button by label."""
    from engine.shell.events import Move, Press, Release
    for b in sh.current.buttons():
        if b[4] == label:
            x, y = b[0] + 5, b[1] + 5
            for ev in (Move(x, y), Press(x, y), Release(x, y)):
                sh.handle(ev)
            return
    raise AssertionError("no button %r in %s" % (label, [b[4] for b in sh.current.buttons()]))


def map_walk(sh, loc):
    import sys
    sys.path.insert(0, __file__.rsplit("/", 1)[0])
    from shell_scenarios import map_walk as walk
    return walk(sh, loc)


def test_shell_visit_loop_scene_inn_shop_leave():
    sh, saves, music = shell_in_map([(C.TOWN, 2)])
    assert music == ["map"] and sh.name == "locations"
    map_walk(sh, (C.TOWN, 2))
    assert sh.name == "town" and sh.town_core().view == "scene" and music[-1] == "town2"
    click_button(sh, "Inn")
    assert sh.name == "inn" and sh.town_core().mask == T.M_INN
    click_button(sh, "Exit")
    assert sh.name == "town" and sh.town_core().mask == 0 and music[-1] == "town2"
    click_button(sh, "Shop")
    assert sh.name == "shop" and sh.town_core().mask == T.M_SHOP
    from engine.shell.events import Key
    sh.handle(Key("escape"))
    assert sh.name == "town" and sh.town_core().mask == 0
    click_button(sh, "Leave town")
    assert sh.name == "locations" and sh.town_core().mask == T.M_MAP and saves == [9998] and music[-1] == "map"
    assert sh.history == ["locations", "town", "inn", "town", "shop", "town", "locations"]


def test_shell_graph_has_the_town_edges():
    from engine.shell import GRAPH
    assert GRAPH["town"] == {"inn", "shop", "locations", "menu"} and GRAPH["inn"] == {"town"} and GRAPH["shop"] == {"town"}


def test_shell_mission_walk_autosaves_9999_and_starts_the_game():
    sh, saves, music = shell_in_map([(C.MISSION, 10)])
    sh.services.start_game = lambda params: object()
    map_walk(sh, (C.MISSION, 10))
    core = sh.town_core()
    assert sh.name == "game" and sh.params["mission"] == 10 and saves == [9999]
    assert core.view == "mission" and core.mask == T.M_MISSION and sh.campaign.camp.location == (C.MISSION, 10)


def test_mission_over_clears_the_intro_flag_on_the_map_branch():
    c = core((C.TOWN, 2))
    c.intro = True
    c.mask = T.M_MISSION
    c.mission_over(C.Outcome("world_map"))
    assert not c.intro and c.mask == T.M_MAP
