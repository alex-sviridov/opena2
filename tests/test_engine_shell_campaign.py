"""L2, the campaign in one window (docs/engine/chargen.md, shell.md 3.4): the character generator's rules (pure model), its screen (press acts on the stat
buttons and the classes, text buttons on the release, Accept builds the campaign), the between-missions screen, and a scripted run through the shell from the
menu to the third mission with the objective oracle as the player.  Needs the install except the model tests."""

import os

import pytest

pytest.importorskip("pygame")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from allods2.common import as_fs  # noqa: E402
from engine import party as PT  # noqa: E402
from engine.shell import GRAPH, Key, Move, Press, Release, Services, Shell  # noqa: E402
from engine.shell import chargen as cg  # noqa: E402
from engine.shell.chargen import ChargenState  # noqa: E402
from helpers import GFS, needs_graphics  # noqa: E402
from shell_scenarios import Recorder, chargen_centre, click, make_shell, to_menu  # noqa: E402


# -- the model (no install) --------------------------------------------------------------------------------------------------------------

def test_cost_table_matches_the_creation_call():
    assert [cg.cost(v) for v in range(15, 46)] == [7, 8, 8, 9, 10, 10, 11, 12, 12, 13, 13, 14, 15, 15, 16, 17, 17, 18, 19, 19, 20, 21, 22, 22, 23, 24, 24, 25, 26, 26, 27]
    assert all(cg.cost(v) == PT.attribute_cost(v) for v in range(1, 60))


def test_start_state_is_the_template_with_an_empty_pool():
    for key, vals in (("MF", (40, 36, 25, 17)), ("FF", (37, 39, 21, 25)), ("MM", (28, 20, 41, 32)), ("FM", (19, 23, 30, 42))):
        s = ChargenState(key)
        assert tuple(s.values) == vals and s.pool == 0 and s.school == 1 and s.mage == (key[1] == "M")


def test_worked_example_of_the_spec():
    s = ChargenState("MF")
    assert not s.can_plus(2)                                                  # an empty pool: only free steps
    assert s.minus(0) and (s.values[0], s.pool) == (39, 1)                    # down(40) = 24 - 23 = 1
    assert s.plus(3) and (s.values[3], s.pool) == (18, 0)                     # up(17) = 9 - 8 = 1
    assert not s.plus(2)                                                      # up(25) = 1 > pool 0: nothing happens
    assert s.values == [39, 36, 25, 18]
    assert s.pick(2) and s.school == 3 and s.clicked
    c = s.choice("Aldor")
    assert (c.start, c.attributes, c.school, c.name) == ("MF", (39, 36, 25, 18), 3, "Aldor")


def test_limits_free_steps_and_the_fifth_class():
    s = ChargenState("FM")
    assert not s.plus(3)                                                      # 42 -> 43 costs 1, pool 0
    s.reset()
    assert s.values == [25] * 4 and s.pool == 100                             # Reset: not the template
    for _ in range(30):
        s.plus(0)
    assert s.values[0] == 45 and not s.can_plus(0)                            # the maximum
    for _ in range(40):
        s.minus(1)
    assert s.values[1] == 15 and not s.can_minus(1)                           # the minimum
    free = ChargenState("MF")
    free.values[3] = 16
    assert free.up(3) == 0 and free.plus(3) and free.values[3] == 17 and free.pool == 0       # a free step on an empty pool
    assert not s.pick(4) and not s.pick(-1) and s.school == 1                 # bow / astral cannot be picked


def test_pool_never_goes_negative_and_a_round_trip_restores_it():
    s = ChargenState("MM")
    start = (list(s.values), s.pool)
    for i in range(4):
        s.minus(i)
        s.minus(i)
    assert s.pool > 0
    for i in range(4):
        s.plus(i)
        s.plus(i)
    assert s.pool >= 0
    assert sum(cg.cost(v) for v in s.values) + s.pool == sum(cg.cost(v) for v in start[0]) + start[1]     # points are conserved


def test_graph_has_the_campaign_screens():
    assert GRAPH["newgame"] == {"menu", "chargen"} and GRAPH["chargen"] == {"newgame", "locations"}
    assert GRAPH["locations"] == {"game", "menu"} and "locations" in GRAPH["game"]


# -- the screens (install) ---------------------------------------------------------------------------------------------------------------

def to_chargen(sh, hero=0, code=0, name="Aldor", level=1):
    sh.start("menu")
    sh.go("newgame")
    sh.go("chargen", difficulty=level + 1, hero=hero, hero_code=code, name=name)
    return sh.current


def button_centre(i):
    x, y, w, h = cg.BUTTONS[i]
    return x + w // 2, y + h // 2


@needs_graphics
def test_stat_buttons_act_on_the_press_with_the_change_sound():
    sh, rec = make_shell(GFS)
    to_chargen(sh)
    p = chargen_centre(sh, "minus", 0)
    sh.handle(Move(*p))
    sh.handle(Press(*p))
    assert sh.current.state.values[0] == 39 and sh.current.state.pool == 1 and rec.sounds[-1] == "sfx/chrgen/+_-.wav"    # on the press, before any release
    sh.handle(Release(*p))
    assert sh.current.state.values[0] == 39                                   # the release does nothing more
    n = len(rec.sounds)
    click(sh, chargen_centre(sh, "plus", 2))                                  # pool 1, up(25) = 1: allowed
    click(sh, chargen_centre(sh, "plus", 2))                                  # pool 0 now: refused, no sound
    assert sh.current.state.values[2] == 26 and len(rec.sounds) == n + 1


@needs_graphics
def test_class_columns_pick_the_school_and_only_four_are_pickable():
    sh, rec = make_shell(GFS)
    cur = to_chargen(sh)
    click(sh, chargen_centre(sh, "class", 3))                                 # pike
    assert cur.state.school == 4 and rec.sounds[-1] == "sfx/chrgen/skill/fpike.wav"
    ox, oy = cur.origin
    bow = cg.MASK["fighter"][4]
    click(sh, (ox + bow[1] + 20, oy + bow[2] + 12))                           # the bow icon is in the picture but no hit loop reaches it
    assert cur.state.school == 4
    sh2, rec2 = make_shell(GFS)
    cur2 = to_chargen(sh2, 3, 0x40, "Gildarius")                              # a mage: spheres, mage sounds
    assert cur2.kind == "mag" and tuple(cur2.state.values) == (28, 20, 41, 32)
    click(sh2, chargen_centre(sh2, "class", 1))
    assert cur2.state.school == 2 and rec2.sounds[-1] == "sfx/chrgen/skill/mwater.wav"


@needs_graphics
def test_text_buttons_act_on_the_release_over_the_same_button():
    sh, rec = make_shell(GFS)
    cur = to_chargen(sh)
    click(sh, chargen_centre(sh, "minus", 0))
    ox, oy = cur.origin
    reset = (ox + button_centre(1)[0], oy + button_centre(1)[1])
    sh.handle(Press(*reset))
    assert rec.sounds[-1] == "sfx/sbros.wav" and cur.state.values[0] == 39    # the sound is on the press, the action waits
    sh.handle(Release(ox + button_centre(0)[0], oy + button_centre(0)[1]))    # released over Accept: nothing
    assert cur.state.values[0] == 39 and sh.name == "chargen"
    click(sh, reset)
    assert cur.state.values == [25] * 4 and cur.state.pool == 100
    back = (ox + button_centre(2)[0], oy + button_centre(2)[1])
    click(sh, back)
    assert sh.name == "newgame" and rec.sounds[-1] == "sfx/back.wav"


@needs_graphics
def test_escape_does_nothing_and_enter_accepts_with_the_panels_values():
    sh, rec = make_shell(GFS)
    to_chargen(sh, name="Elfric")
    sh.handle(Key("escape"))
    assert sh.name == "chargen"                                               # the panel ignores Esc (chargen.md 1.2)
    click(sh, chargen_centre(sh, "minus", 0))
    click(sh, chargen_centre(sh, "plus", 3))
    click(sh, chargen_centre(sh, "class", 2))
    sh.handle(Key("return"))
    assert sh.name == "locations" and sh.campaign is not None
    hero = sh.campaign.roster[0]
    assert (hero.spec.attributes, hero.spec.school, hero.spec.name) == ((39, 36, 25, 18), 3, "Elfric")
    assert sh.campaign.difficulty == 2 and sh.campaign.next_mission() == 10


@needs_graphics
def test_accept_without_changes_sends_school_one_not_none():
    sh, _ = make_shell(GFS)
    cur = to_chargen(sh, 2, 0xC0, "Galinel")
    ox, oy = cur.origin
    click(sh, (ox + button_centre(0)[0], oy + button_centre(0)[1]))
    spec = sh.campaign.roster[0].spec
    assert (spec.attributes, spec.school) == ((19, 23, 30, 42), 1)           # chargen.md 2.5: school 1 is sent, never None
    assert sh.campaign.is_mage and sh.campaign.is_female


@needs_graphics
def test_hint_shows_per_class_changes_after_a_class_click_and_closes():
    sh, _ = make_shell(GFS)
    cur = to_chargen(sh)
    assert cur.hint and cur.tips_text().startswith("This screen allows you")
    click(sh, chargen_centre(sh, "class", 0))
    assert cur.tips_text().startswith("Now you can change the basic stats")
    ox, oy = cur.origin
    x, y, w, h = cur.tips_win.close
    click(sh, (ox + x + w // 2, oy + y + h // 2))
    assert not cur.hint
    sh2, _ = make_shell(GFS, settings=type(sh.settings)(tips=False))
    assert not to_chargen(sh2).hint                                           # TipsMode off: no hint


@needs_graphics
def test_hint_check_box_writes_tips_mode_and_the_window_stays():
    sh, _ = make_shell(GFS)
    cur = to_chargen(sh)
    ox, oy = cur.origin
    assert cg.HINT == (160, 280, 312, 200) and cur.tips_win.close == (160 + 192, 280 + 160, 80, 18) and cur.tips_win.checked and sh.settings.tips      # the exe's SetRect (0, 0x118, 0x138, 0x1e0) in the class column
    x, y, w, h = cur.tips_win.check
    click(sh, (ox + x + w // 2, oy + y + h // 2))
    assert not cur.tips_win.checked and not sh.settings.tips and cur.hint                    # message 0x46e writes TipsMode; the window stays until Close
    click(sh, (ox + x + w // 2, oy + y + h // 2))
    assert cur.tips_win.checked and sh.settings.tips
    off = [op for op in cur.scene().ops if getattr(op, "path", "").endswith("radiob.256")]
    assert {op.frame for op in off} == {5}                                            # on = frame 5
    click(sh, (ox + x + w // 2, oy + y + h // 2))
    assert {op.frame for op in cur.scene().ops if getattr(op, "path", "").endswith("radiob.256")} == {4}
    sh3, _ = make_shell(GFS)
    c3 = to_chargen(sh3)
    ox, oy = c3.origin
    click(sh3, (ox + cg.HINT[0] + 100, oy + cg.HINT[1] + 100))                        # inside the window (text): swallowed, nothing happens
    assert c3.hint and c3.state.school == 1


@needs_graphics
def test_locations_lists_the_available_missions_and_main_menu():
    sh, rec = make_shell(GFS)
    to_chargen(sh)
    sh.handle(Key("return"))
    loc = sh.current
    assert sh.name == "locations" and loc.missions == [10] and loc.labels[0].startswith("Mission 10")
    assert loc.party == ["Aldor (new)"]
    bx, by, bw, bh, label, mission = loc.buttons()[0]
    assert mission == 10
    click(sh, (bx + 5, by + 5))
    assert sh.name == "game" and sh.params == {"campaign": sh.campaign, "mission": 10}
    sh2, _ = make_shell(GFS)
    to_chargen(sh2)
    sh2.handle(Key("return"))
    bx, by, bw, bh, label, mission = sh2.current.buttons()[-1]
    assert label == "Main Menu" and mission is None
    click(sh2, (bx + 5, by + 5))
    assert sh2.name == "menu"


# -- the campaign in one window: menu -> three missions, the oracle as the player ---------------------------------------------------------

class OracleSession:
    """What `start_game` returns for a campaign mission: the world the campaign built; `run` makes the objective true (as the player would) and reports a win."""

    def __init__(self, params, shell, log):
        camp = params["campaign"]
        self.world, _ = camp.start_mission(params["mission"])
        self.mission = params["mission"]
        log.append(self.mission)

    def run(self):
        from engine import objective
        r = objective.run(str(self.mission), GFS, seed=1, world=self.world, side=())
        return "victory" if r["result"] == "won" else "defeat"


@needs_graphics
def test_scripted_menu_run_through_the_first_three_missions():
    rec, played = Recorder(), []
    rec.services.start_game = lambda params: OracleSession(params, sh, played)
    sh, _ = make_shell(GFS, rec=rec)
    to_menu(sh)
    click(sh, __import__("shell_scenarios").button_centre(sh, 0))             # NEW GAME
    assert sh.name == "newgame"
    sh.handle(Key("return"))                                                  # OK with the default name
    assert sh.name == "chargen"
    sh.handle(Key("return"))                                                  # Accept: the starting template
    assert sh.name == "locations"
    for _ in range(3):
        n = sh.current.missions[0]
        bx, by, *_ = sh.current.buttons()[0]
        click(sh, (bx + 5, by + 5))
        assert sh.name == "game"
        sh.apply(sh.current.run())                                            # the oracle wins; the game screen ends the mission through the campaign
        assert sh.name == "locations", sh.history
        assert n in played
    assert len(set(played)) == 3 and played[0] == 10
    camp = sh.campaign
    assert all(camp.camp.get(0x380 + m) == 1 for m in played)                 # Scenario.dll marked them finished
    assert camp.roster and camp.roster[0].state is not None                   # the carried hero left the world with a state
    assert sh.history[2:] == ["newgame", "chargen", "locations"] + ["game", "locations"] * 3


@needs_graphics
def test_a_defeat_or_leaving_goes_to_the_main_menu_without_carry_over():
    rec, played = Recorder(), []

    class Lost(OracleSession):
        def run(self):
            return "defeat"
    rec.services.start_game = lambda params: Lost(params, sh, played)
    sh, _ = make_shell(GFS, rec=rec)
    to_chargen(sh)
    sh.handle(Key("return"))
    bx, by, *_ = sh.current.buttons()[0]
    click(sh, (bx + 5, by + 5))
    before = sh.campaign.state_hash()
    sh.apply(sh.current.run())
    assert sh.name == "menu" and sh.campaign.state_hash() == before          # no carry-over, nothing completed


@needs_graphics
def test_the_last_missions_ending_goes_to_the_menu(monkeypatch):
    from engine.sim import campaign as C
    rec, played = Recorder(), []
    rec.services.start_game = lambda params: OracleSession(params, sh, played)
    sh, _ = make_shell(GFS, rec=rec)
    to_chargen(sh)
    sh.handle(Key("return"))
    bx, by, *_ = sh.current.buttons()[0]
    click(sh, (bx + 5, by + 5))
    monkeypatch.setattr(type(sh.campaign), "leave_mission", lambda self, world, result="won": C.Outcome("ending"))
    sh.apply(sh.current.run())
    assert sh.name == "menu"                                                  # the credits are not built
