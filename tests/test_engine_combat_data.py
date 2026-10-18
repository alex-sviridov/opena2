"""Combat with the install's data (I1): real templates and items through the whole chain.  Skipped without the game files.
Spec: docs/engine/combat.md sections 5.3 and 6."""

import math

import numpy as np
import pytest

from allods2.assets import AssetCache
from engine.sim import AttackUnit, Simulation
from engine.sim.combat import BRAIN_SWING, combat_stats
from engine.world import UNIT_ID_BASE, Damage, Player, Unit, World
from helpers import GFS, needs_data

pytestmark = needs_data


@pytest.fixture(scope="module")
def assets():
    return AssetCache(GFS)


@pytest.fixture(scope="module")
def templates(assets):
    return {t.name: t for t in assets.unit_stats().types}


def arena(assets, seed=1):
    w = World(np.zeros((40, 40), np.uint16), np.zeros((40, 40), np.int8), "arena", seed=seed)
    w._cost = np.full((40, 40), 8, np.uint8)
    w.players[1] = Player(1, 0, human=True)
    w.players[2] = Player(2, 1)
    w.item_table = assets.items()
    return w


def spawn(w, templates, name, uid, x, y, owner, hp=100_000, facing=64):
    t = templates[name]
    u = Unit(UNIT_ID_BASE + uid, 1, owner, x, y, uid=uid, hp=hp, hp_max=hp, facing=facing, human=t.kind == "human", stats=t,
             move_type=t.movement_type if t.movement_type in (1, 2, 3) else 1)
    u.mover.turn_rate = 32
    u.speed_mod = 12
    if u.human:
        from allods2.formats import progression as prog
        u.skills = prog.skills_of(t)
    w.add_unit(u)
    return u


def fight(w, a, t, ticks):
    sim = Simulation(w)
    sim.step([AttackUnit(a.owner, (a.id,), t.id)])
    starts, prev = [], 0
    for _ in range(ticks):
        tick = w.tick
        sim.step()
        if a.brain_order == BRAIN_SWING and prev != BRAIN_SWING:
            starts.append(tick)
        prev = a.brain_order
    return [e for e in w.fight_log if isinstance(e, Damage)], starts


def test_orc_sword_against_ogre_matches_example_a(assets, templates):
    w = arena(assets, seed=2024)
    a, ogre = spawn(w, templates, "Orc_Sword", 1, 10, 10, 2), spawn(w, templates, "Ogre", 2, 11, 10, 1)
    st = combat_stats(w, a)
    assert (st.record.skill, st.record.lo, st.record.sp, st.windup, st.recovery) == (53, 12, 12, 11, 4)
    log, starts = fight(w, a, ogre, 12_000)
    n = len(log)
    assert n > 400
    hits = [d for d in log if d.amount > 0]
    p = 83 / 201
    assert abs(len(hits) - n * p) < 3.5 * math.sqrt(n * p * (1 - p))
    assert min(d.amount for d in hits) == 7 and max(d.amount for d in hits) == 19
    assert abs(sum(d.amount for d in hits) / len(hits) - 13) < 0.5
    assert log[0].tick == starts[0] + 11                                   # the first blow lands `windup` ticks after the swing starts
    gaps = {b - s for s, b in zip(starts, starts[1:])}
    assert gaps <= set(range(11 + 4 + 2, 11 + 7 + 2 + 1)) and len(gaps) == 4        # 17..20: recovery 4 + rand(0..3), plus 2


def test_goblin_pike_against_troll_matches_example_b(assets, templates):
    w = arena(assets, seed=7)
    a, troll = spawn(w, templates, "Goblin_Pike", 1, 10, 10, 2), spawn(w, templates, "Troll", 2, 11, 10, 1)
    log, _ = fight(w, a, troll, 40_000)
    n = len(log)
    assert n > 1500
    p = 16 / 201
    hits = [d for d in log if d.hit]
    assert abs(len(hits) - n * p) < 4 * math.sqrt(n * p * (1 - p))
    assert {d.amount for d in log} <= {0, 1, 2, 3, 4}
    zeros = sum(1 for d in hits if d.amount == 0)
    assert abs(zeros - len(hits) / 3) < 4 * math.sqrt(len(hits) * (1 / 3) * (2 / 3))        # a third of the hits are absorbed


def test_hero_with_a_two_handed_sword_against_a_goblin(assets, templates):
    w = arena(assets, seed=99)
    hero, gob = spawn(w, templates, "Fighter_Hero", 1, 10, 10, 1), spawn(w, templates, "Goblin_Pike", 2, 11, 10, 2)
    st = combat_stats(w, hero)
    assert (st.record.skill, st.record.lo, st.record.sp, st.windup, st.recovery, st.weapon_weight) == (97, 20, 15, 10, 4, 57)
    log, starts = fight(w, hero, gob, 6000)
    hits = [d for d in log if d.hit]
    assert len(log) > 250
    p = (97 + 100 - 31 + 1) / 201                                          # rolls with 97 + roll > 31: roll >= -65
    assert abs(len(hits) - len(log) * p) < 3.5 * math.sqrt(len(log) * p * (1 - p))
    assert all(20 <= d.amount <= 35 for d in hits)                         # no absorption on the goblin
    # recovery 4 + hero delay 1 + rand(0..3), windup 10, plus 2
    gaps = {b - s for s, b in zip(starts, starts[1:])}
    assert gaps <= set(range(10 + 5 + 2, 10 + 8 + 2 + 1)) and len(gaps) == 4


def test_bats_never_miss_and_ignore_absorption(assets, templates):
    w = arena(assets, seed=5)
    bat, tank = spawn(w, templates, "Bat_Sonic", 1, 10, 10, 2), spawn(w, templates, "Troll", 2, 12, 10, 1)
    st = combat_stats(w, bat)
    assert st.sure_hit and st.range == 4                                   # the sonic beam is a ranged weapon
    log, _ = fight(w, bat, tank, 4000)
    assert len(log) > 30 and all(d.hit for d in log)
    assert all(d.amount >= 1 for d in log)                                 # absorption 10 would have eaten a 1..4 blow


def test_archer_approaches_to_range_and_the_blow_is_delayed_by_the_arrow(assets, templates):
    w = arena(assets, seed=3)
    bow, foe = spawn(w, templates, "Orc_Bow", 1, 10, 10, 2), spawn(w, templates, "Ogre", 2, 18, 10, 1)
    foe.speed_mod = -100                                                   # stand still (speed floor 1)
    assert combat_stats(w, bow).range == 4
    log, starts = fight(w, bow, foe, 3000)
    assert log and max(abs(bow.x - foe.x), abs(bow.y - foe.y)) <= 4
    gap = max(abs(bow.x - foe.x), abs(bow.y - foe.y))
    extra = (gap * 256 + 128) // 200 if gap > 1 else 0
    assert log[0].tick == starts[0] + 21 + extra                           # windup 21 plus the flight of the arrow


def test_every_unit_of_a_campaign_map_gets_stats(assets):
    from allods2.cli import open_map
    w = World.from_map(open_map("10", GFS), assets)
    assert w.item_table is not None
    for u in w.units.values():
        st = combat_stats(w, u)
        assert st.range >= 1 and 0 <= st.record.lo <= 255
