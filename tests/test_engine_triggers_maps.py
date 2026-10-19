"""Scenario triggers on the campaign maps (docs/engine/triggers.md; game files, skipped without the install).

The maps hold no hero: the party is placed at the "Drop Location" at map start (not built).  `with_party` adds the three heroes of the
human player (`Start_MF` = 10001, the main hero; `Fighter_Hero` = 10002, `Mage_Hero` = 10003) at and next to the first drop cell through the
section 6 loader, so the hero references resolve (a missing one makes its records fail and map to slot / index 0, triggers.md 2.4).
"""

from types import SimpleNamespace

import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from allods2.common import campaign_maps
from allods2.formats import entities as E
from engine.sim import Simulation
from engine.sim import triggers as T
from engine.world import World

from helpers import GFS, needs_data

pytestmark = needs_data
PARTY = (10210, 10220, 10230)       # Start_MF, Fighter_Hero, Mage_Hero: reduced ids 21, 22, 23 = heroes 10001, 10002, 10003
HERO_UID = 997                      # uids above every map's


def with_party(w, m, assets):
    drops = [r for r in m.scenario.instants if r.type == 0x10002]
    x, y = (drops[0].values[0], drops[0].values[1]) if drops else (w.width // 2, w.height // 2)
    recs = []
    for k, (sid, (dx, dy)) in enumerate(zip(PARTY, ((0, 0), (1, 0), (0, 1)))):
        tpl = assets.unit_stats().lookup(True, sid)
        recs.append(E.Unit(((x + dx) << 8) + 128, ((y + dy) << 8) + 128, tpl.unit_type, 0, E.HUMAN_FLAG, 0, sid, 1, 0, 0,
                           E.NO_HP, E.NO_HP, HERO_UID + k, 0, 0))
    w._load_units(SimpleNamespace(units=recs, item_groups=[]), assets, None)
    return w.units[0x6000 + HERO_UID]


def build(name, seed=1):
    a = AssetCache(GFS)
    m = open_map(name, GFS)
    w = World.from_map(m, a, seed=seed)
    h = with_party(w, m, a)
    T.enable(w, m)
    return w, h


def test_every_campaign_script_compiles_with_the_party():
    for path in campaign_maps(GFS):
        w, h = build(path)
        s = w.script
        assert w.players[1].main_hero == h.id
        assert len(s.triggers) == sum(1 for t in open_map(path, GFS).scenario.triggers if t.active)
        assert s.errors == [], (path, s.errors)        # every unit, hero, group, player and building the scripts name exists


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
