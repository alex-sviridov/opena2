"""L10e-B, the shell side: the mission-start auto-save `game9999` ("Restart last mission"), `game9998` at the town scene's leave click, the mission menu's Save / Load
through the codec hook, and the resume of a loaded mission by the game screen (docs/engine/save-ui.md 4, 6).  Needs the install (a real mission)."""

from allods2.formats import saves as S
from engine import saveslots as SS
from engine import savegame
from engine import missionsave as M
from engine.campaign import CampaignGame, HeroChoice
from engine.shell import Services, Shell
from engine.shell import saveload as SL
from engine.sim import Simulation

from helpers import GFS, needs_data

pytestmark = needs_data


class FakeSession:
    """What `start_game` returns: a world and a `run()` that ends the mission with `reason` (`load_file` for the mission menu's Load)."""

    def __init__(self, params, reason="menu", load_file=None):
        loaded = params.get("loaded")
        if loaded is not None:
            self.world = loaded.world
        else:
            self.world, _ = params["campaign"].start_mission(params["mission"])
        self.params, self.reason, self.load_file = params, reason, load_file

    def run(self):
        return self.reason


def campaign():
    g = CampaignGame(GFS, seed=4)
    g.new_game(HeroChoice("MF"))
    return g


def shell(tmp_path, game, **session_kw):
    started = []

    def start(params):
        s = FakeSession(params, **session_kw)
        started.append(s)
        return s
    sh = Shell(None, (640, 480), services=Services(start_game=start), slots=SS.SaveSlots(tmp_path))
    sh.campaign = game
    return sh, started


def test_a_campaign_mission_start_writes_game9999_with_the_restart_description(tmp_path):
    g = campaign()
    sh, started = shell(tmp_path, g)
    sh.start("game", campaign=g, mission=g.next_mission())
    [slot] = sh.slots.scan(include_hidden=True)
    assert slot.name == "game9999.sav" and slot.description == "Restart last mission"
    save = S.parse_save(sh.slots.read("game9999.sav"))
    assert savegame.kind(save) == "mission"
    lm = M.world_from_save(save, g.assets)
    assert lm.world.tick == 0 and lm.world.dump_hash() == started[0].world.dump_hash() and lm.campaign.camp.vars == g.camp.vars
    assert lm.campaign.camp.location == g.camp.location and lm.world.script.scenario_vars is lm.campaign.camp.vars


def test_loading_a_mission_file_resumes_it_without_a_new_autosave(tmp_path):
    g = campaign()
    sh, started = shell(tmp_path, g)
    sh.start("game", campaign=g, mission=g.next_mission())
    sim = Simulation(started[0].world, triggers=True, vision=True)
    for _ in range(90):
        sim.step()
    assert sh.save_mission(started[0], "game0000.sav", "mid mission") is None
    before = sh.slots.read("game9999.sav")
    status, res = SL.load_file(sh, "game0000.sav")
    assert status == "ok" and res[0] == "game" and res[1]["loaded"].world.tick == 90 and res[1]["campaign"] is sh.campaign
    sh.apply(res)                                                       # game -> game: the loaded world is played
    assert sh.name == "game" and started[-1].world is res[1]["loaded"].world
    assert sh.slots.read("game9999.sav") == before                       # `FUN_0048c8a3(1)`: no new auto-save
    assert res[1]["loaded"].world.dump_hash() == started[0].world.dump_hash()


def test_the_mission_menus_load_window_replaces_the_game(tmp_path):
    g = campaign()
    sh, started = shell(tmp_path, g, reason="load", load_file="game9999.sav")
    sh.start("game", campaign=g, mission=g.next_mission())
    out = sh.current.run()
    assert out[0] == "game" and out[1]["loaded"].world.tick == 0
    sh.slots.write("game0001.sav", b"\0" * 32)                         # a refused file: the main menu (`0x421`)
    started[0].load_file = "game0001.sav"
    assert sh.current.run() == "menu"


def test_the_town_scenes_leave_click_writes_game9998_a_town_save(tmp_path):
    g = campaign()
    sh, _ = shell(tmp_path, g)
    sh.autosave(9998)
    [slot] = sh.slots.scan(include_hidden=True)
    assert slot.name == "game9998.sav" and slot.description == "Abort mission and return to town"
    assert savegame.kind(sh.slots.read("game9998.sav")) == "town"
    back = savegame.from_save(sh.slots.read("game9998.sav"), install=GFS, resume_location=True)
    assert back.camp.available == g.camp.available and {k: v for k, v in g.camp.vars.items() if v} == back.camp.vars


def test_the_mission_menu_entries_are_enabled_only_with_a_file_service():
    from engine.ui import Layout, modal
    lay = Layout.for_size(640, 480)
    off = modal.menu_dialog(lay, lambda i: "t%d" % i)
    on = modal.menu_dialog(lay, lambda i: "t%d" % i, files=True)
    assert [b.enabled for b in off.buttons[:2]] == [False, False] and [b.enabled for b in on.buttons[:2]] == [True, True]
    assert on.buttons[0].action == ("open", "save") and on.buttons[1].action == ("open", "load")
