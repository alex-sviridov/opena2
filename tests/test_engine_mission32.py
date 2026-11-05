"""J3: map 32 can be won and lost (docs/engine/triggers.md 12; game files, skipped without the install).

Win = 'Swordsman alive ?' (check 5 on the sword carrier, uid 8) == 0 -> instant 4; script loss = 'Swordsman swarmed successfully'
(distance sword carrier - point (71, 13) <= 1) -> instant 5 'we are late'; the third way to lose is the main hero's death (T§6).
Scenarios use the real systems; the setup moves units with the scripted teleport (instant 27) like the map's own scripts do.
"""

import logging

import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.sim import Simulation, replay, triggers as T
from engine.sim.commands import AttackUnit
from engine.world import World

from helpers import GFS, needs_data

pytestmark = needs_data

SWORD_UID, POINT = 2021, (71, 13)       # 'CH_SwordCarrier' (server id 2021, scenario uid 8) and the swarm point of the script


def build(seed=1):
    a = AssetCache(GFS)
    m = open_map("scenario/32.alm", GFS)
    w = World.from_map(m, a, seed=seed)
    T.enable(w, m, assets=a)
    sim = Simulation(w, triggers=True)
    hero = w.units[w.players[1].main_hero]
    sword = next(u for u in w.units.values() if u.server_id == SWORD_UID)
    return w, sim, hero, sword


def run_until(sim, w, n, commands_at=None):
    for _ in range(n):
        sim.step((commands_at or {}).get(w.tick, ()))
        if T.result(w):
            break
    return T.result(w)


def next_to_the_sword(w, hero, sword):
    T.teleport(w, hero, sword.x - 1, sword.y)           # the setup is a world change: replays repeat it before the log


def win_scenario(seed=1):
    w, sim, hero, sword = build(seed)
    next_to_the_sword(w, hero, sword)
    cmd = AttackUnit(1, (hero.id,), sword.id)
    sim.step([cmd])
    result = run_until(sim, w, 1500, {w.tick + 16: [cmd]})
    return w, sim, result


def test_nothing_is_decided_at_the_start():
    w, sim, hero, sword = build()
    assert T.result(w) is None and w.script.errors == []
    assert run_until(sim, w, 64) is None                                 # the start trigger only sends message 1


def test_killing_the_sword_carrier_wins():
    w, sim, result = win_scenario()
    assert result == "won", (w.tick, w.players[1].death_code)
    assert w.mission_complete and any(type(e).__name__ == "MissionComplete" for e in w.events)
    assert not any(type(e).__name__ == "MissionFailed" for e in w.events)


def test_the_sword_carrier_reaching_the_point_loses():
    w, sim, hero, sword = build()
    T.teleport(w, sword, *POINT)
    assert run_until(sim, w, 64) == "lost"
    assert w.script.fail == 5 and w.players[1].death_code == 5 and w.players[1].defeat_dialog
    assert any(type(e).__name__ == "MissionFailed" for e in w.events)


def test_the_main_hero_dying_loses():
    w, sim, hero, sword = build()
    hero.hp = -20
    assert run_until(sim, w, 200) == "lost"
    assert w.players[1].death_code == 21 - 0x13                     # the byte `+0x14c - 0x13` of Start_MF (reduced id 21)
    assert w.players[1].defeat_dialog and w.script.fail == 0       # the hero's own death byte, not a script failure


def test_the_win_replays_identically():
    w1, sim1, r1 = win_scenario(seed=3)
    w2, sim2, hero2, sword2 = build(3)
    next_to_the_sword(w2, hero2, sword2)
    replay(sim2, sim1.log, w1.tick)
    assert (T.result(w2), w2.tick, w2.dump_hash()) == (r1, w1.tick, w1.dump_hash())


def test_the_map_needs_no_unimplemented_opcode():
    w, sim, hero, sword = build()
    run_until(sim, w, 200)
    assert not w.script.unsupported


def test_an_unimplemented_kind_is_reported_once_and_skipped(caplog):
    w, sim, hero, sword = build()
    s = w.script
    with caplog.at_level(logging.WARNING, logger=T.log.name):
        for _ in range(3):
            T._unsupported(s, "instant", 37)
    msgs = [r.getMessage() for r in caplog.records]
    assert msgs == ["not implemented: instant 37 (unnamed)"] and s.unsupported[("instant", 37)] == 3
