"""Scenario triggers on the campaign maps (docs/engine/triggers.md; game files, skipped without the install).

The maps hold no hero: `triggers.enable(..., assets=)` places the party at the "Drop Location" like the exe (engine/party.py,
triggers.md section 9): the main hero (`Start_MF`, 10001) and as many of `Fighter_Hero` / `Mage_Hero` (10002, 10003) as the script names.
"""

import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from allods2.common import campaign_maps
from engine.sim import Simulation
from engine.sim import triggers as T
from engine.world import World

from helpers import GFS, needs_data

pytestmark = needs_data


def build(name, seed=1, party=0):
    a = AssetCache(GFS)
    m = open_map(name, GFS)
    w = World.from_map(m, a, seed=seed)
    T.enable(w, m, assets=a, party=party)
    return w, w.units[w.players[1].main_hero]


def test_every_campaign_script_compiles_with_the_party():
    for path in campaign_maps(GFS):
        w, h = build(path)
        s = w.script
        assert w.players[1].main_hero == h.id and h.server_id == 10210
        assert (h.x, h.y) in s.drops                                        # the lone drop cell of the map is free: the hero stands on it
        assert len(s.triggers) == sum(1 for t in open_map(path, GFS).scenario.triggers if t.active)
        assert s.errors == [], (path, s.errors)        # every unit, hero, group, player and building the scripts name exists


def test_a_fresh_start_has_only_the_main_hero_and_the_other_hero_references_fail_like_in_the_exe():
    w, h = build("52", party=1)
    assert [u.server_id for u in w.units.values() if u.owner == 1 and u.human] == [10210]
    assert "Can't resolve hero 10002" in w.script.errors


@pytest.mark.parametrize("name", ["52", "80", "102"])
def test_no_fake_mission_complete_or_defeat_with_the_party(name):
    w, h = build(name)
    sim = Simulation(w, triggers=True)
    for _ in range(300):
        sim.step()
    assert not [e for e in w.events if type(e).__name__ in ("MissionComplete", "MissionFailed")]
    assert w.players[1].death_code == 0 and not w.players[1].defeat_dialog and w.check_consistency() == []


def test_engine_setup_places_the_party_so_the_run_is_not_lost_at_tick_14():
    from types import SimpleNamespace
    from engine.__main__ import _setup
    a = SimpleNamespace(cmd="screenshot", install=GFS, map="80", seed=1, triggers=True, size=(640, 480), no_shadows=True,
                        no_light=True, no_smoothing=True, no_objects=True, x=0, y=0, debug="", interface=False)
    w = _setup(a)[0]
    assert w.players[1].main_hero in w.units
    sim = Simulation(w, triggers=True)
    for _ in range(40):
        sim.step()
    assert not [e for e in w.events if type(e).__name__ == "MissionFailed"]


def test_map_10_start_trigger_sends_message_1_at_the_first_pass_and_replays():
    def run(n):
        w, h = build("10")
        sim = Simulation(w, triggers=True)
        for _ in range(n):
            sim.step()
        return w

    w = run(40)
    msgs = [(e.tick, e.number) for e in w.events if isinstance(e, T.ScriptMessage)]
    assert (6, 1) in msgs                                       # 'Start': FALSE == FALSE -> 'Send message 1 - start'
    assert w.script.fired[0] == 1 and w.check_consistency() == []
    assert run(40).dump_hash() == w.dump_hash()
