"""Hits on structures (FUN_00516ea0 / FUN_005201b2, docs/engine/combat.md 5.4).  Synthetic scenes always run; the map-32 part needs the install."""

import numpy as np
import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.sim import AttackUnit, Simulation
from engine.sim.combat import STRUCTURE_ARMOUR, resolve_structure_attack, structure_damage
from engine.sim.combatstats import AttackRecord
from engine.rng import Rng
from engine.world import MapObject, World

from helpers import GFS, needs_data
from test_engine_combat import damages, fighter, world


def tower(w, hp=500, x=12, y=10, **kw):
    ob = MapObject(0x6800, "structure", 21, x, y, owner=3, hp=hp, hp_max=hp, uid=0x800, footprint=((0, 0, True), (1, 0, True)), **kw)
    w.add_object(ob)
    return ob


def swing_at(w, a, ob):
    a.swing_target = ob.id


def test_damage_is_elemental_only_minus_five():
    r = Rng(1)
    assert structure_damage(AttackRecord(skill=999, lo=50, sp=50), r) == 0          # physical damage never counts
    assert structure_damage(AttackRecord(elo=5, esp=0), r) == 0                     # exactly the flat 5
    assert structure_damage(AttackRecord(elo=20, esp=0), r) == 20 - STRUCTURE_ARMOUR
    r = Rng(1)
    seen = {structure_damage(AttackRecord(elo=10, esp=6), r) for _ in range(300)}
    assert seen <= set(range(5, 12)) and len(seen) > 3                              # 10 + 0..6 - 5


def test_hit_lowers_hp_and_logs():
    w = world()
    ob = tower(w)
    a = fighter(w, 1, 10, 10, rng=2)
    a.range = 2
    a.combat.record.elo = 30
    assert resolve_structure_attack(w, a, ob, a.combat) == 25
    assert ob.hp == 475
    assert damages(w)[-1].target == ob.id and damages(w)[-1].amount == 25


def test_gates_range_hp_and_indestructible():
    w = world()
    ob = tower(w)
    a = fighter(w, 1, 2, 10, rng=1)
    a.range = 1
    a.combat.record.elo = 30
    assert resolve_structure_attack(w, a, ob, a.combat) is None and ob.hp == 500     # out of range
    b = fighter(w, 2, 11, 10, hp=0)
    b.range = 1
    b.combat.record.elo = 30
    assert resolve_structure_attack(w, b, ob, b.combat) is None                      # dead attacker
    c = fighter(w, 3, 11, 10)
    c.range = 1
    c.combat.record.elo = 30
    ob.indestructible = True
    assert resolve_structure_attack(w, c, ob, c.combat) == 0 and ob.hp == 500


def test_lethal_hit_keeps_the_object_and_its_blocks():
    w = world()
    ob = tower(w, hp=10)
    blocked = w._block.copy()
    a = fighter(w, 1, 11, 10)
    a.range = 1
    a.combat.record.elo = 100
    resolve_structure_attack(w, a, ob, a.combat)
    assert ob.hp == -85 and ob.id in w.objects
    assert (w._block == blocked).all()                                               # no block release
    assert damages(w)[-1].hp == -85                                                  # HP was > 0 before: message 0x73 carries it
    resolve_structure_attack(w, a, ob, a.combat)
    assert ob.hp == -180 and len(damages(w)) == 1                                    # HP <= 0 before and < -10 now: silent


def test_swing_through_the_simulation_hits_the_structure():
    w = world()
    ob = tower(w)
    a = fighter(w, 1, 11, 10, windup=3, recovery=2)
    a.range = 1
    a.combat.record.elo = 20
    sim = Simulation(w)
    a.swing_target = ob.id
    a.brain_order, a.state = 1, 3
    for _ in range(12):
        sim.step()
    assert ob.hp < 500 and all(d.target == ob.id for d in damages(w))


def test_attack_order_on_a_structure_is_dropped_without_crash():
    w = world()
    ob = tower(w)
    a = fighter(w, 1, 5, 10)
    sim = Simulation(w)
    sim.step([AttackUnit(1, (a.id,), ob.id)])
    for _ in range(40):
        sim.step()
    assert a.order == 0 and ob.hp == 500 and (a.x, a.y) == (5, 10)


@needs_data
def test_map32_structures_resist_the_brigands_and_swordsman():
    a = AssetCache(GFS)
    m = open_map("scenario/32.alm", GFS)
    w = World.from_map(m, a, seed=1)
    sts = [o for o in w.objects.values() if o.kind == "structure"]
    assert len(sts) == 2 and not any(o.indestructible for o in sts)
    from engine.sim.combat import combat_stats
    for u in w.units.values():
        if u.owner != 1:
            assert structure_damage(combat_stats(w, u).record, Rng(7)) == 0, u.server_id    # no elemental damage: structures never take a scratch


def test_structure_gap_uses_size_one_at_the_anchor_whatever_the_footprint():
    from engine.sim.combat import structure_gap
    w = world()
    ob = tower(w, x=12, y=10, size=(3, 3))                  # a 3 x 3 footprint is still size 1 for the gap (vtable +0x1c = 1, `0x541fe0`)
    a = fighter(w, 1, 10, 10)                               # two cells west of the anchor cell
    assert structure_gap(a, ob) == 2 and structure_gap(fighter(w, 2, 11, 10), ob) == 1
    assert structure_gap(fighter(w, 3, 14, 10), ob) == 2    # east of the anchor: the far side of the footprint is not nearer
