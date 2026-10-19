"""Units, items and players in the engine world (G3a): synthetic tests always run, the
per-map checks need the install.  Spec: docs/engine/architecture.md section 9,
docs/formats/map.md part 5."""

import numpy as np
import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from allods2.common import campaign_maps
from engine.sim import Simulation
from engine.world import (IDLE, ITEM_ID_BASE, UNIT_ID_BASE, Item, MapObject, Unit, World,
                          unit_angle)

from helpers import GFS

N = 32


def world():
    return World(np.zeros((N, N), np.uint16), np.zeros((N, N), np.int8), "syn")


def unit(uid, x, y, **kw):
    return Unit(UNIT_ID_BASE + uid, 1, 1, x, y, uid=uid, hp=10, hp_max=10, **kw)


# --- synthetic -----------------------------------------------------------------------------

def test_units_and_items_are_indexed_but_never_block():
    w = world()
    before = w.block.copy()
    w.add_unit(unit(1, 12, 12))
    w.add_unit(unit(2, 12, 12))
    w.add_item(Item(ITEM_ID_BASE, 12, 12, gold=100))
    w.add_object(MapObject(0x10000, "object", 5, 14, 14))
    assert w.units_at(12, 12) == {UNIT_ID_BASE + 1, UNIT_ID_BASE + 2}
    assert w.items_at(12, 12) == {ITEM_ID_BASE}
    assert w.entities_at(12, 12) == {UNIT_ID_BASE + 1, UNIT_ID_BASE + 2, ITEM_ID_BASE}
    assert w.entities_at(14, 14) == {0x10000}
    assert not w.blocked(12, 12)
    diff = np.argwhere(w.block != before)
    assert diff.tolist() == [[14, 14]]                      # only the object changed the layer
    assert np.array_equal(w.block, w.rebuild_block())


def test_unit_move_remove_and_errors():
    w = world()
    w.add_unit(unit(1, 12, 12))
    w.move_unit(UNIT_ID_BASE + 1, 15, 16, 10, 20)
    u = w.units[UNIT_ID_BASE + 1]
    assert (u.x, u.y, u.sub_x, u.sub_y) == (15, 16, 10, 20)
    assert w.units_at(12, 12) == frozenset() and (12, 12) not in w._ucells
    with pytest.raises(ValueError):
        w.add_unit(unit(1, 3, 3))                           # duplicate id, world unchanged
    with pytest.raises(ValueError):
        w.add_unit(unit(2, N, 3))                           # outside the map
    with pytest.raises(ValueError):
        w.move_unit(UNIT_ID_BASE + 1, -1, 0)
    assert list(w.units) == [UNIT_ID_BASE + 1] and w.units_at(15, 16) == {UNIT_ID_BASE + 1}
    w.remove_unit(UNIT_ID_BASE + 1)
    assert not w.units and not w._ucells
    w.add_item(Item(ITEM_ID_BASE + 3, 4, 4))
    w.remove_item(ITEM_ID_BASE + 3)
    assert not w.items and not w._icells


def test_unit_ids_share_the_structure_space():
    w = world()
    w.add_object(MapObject(0x6000 + 7, "structure", 5, 10, 10, uid=7))
    with pytest.raises(ValueError):
        w.add_unit(unit(7, 3, 3))                           # same uid as a structure


def test_unit_angle_is_the_creature_constructor_range():
    angles = {unit_angle(u) for u in range(1, 600)}
    assert min(angles) >= 0x40 and max(angles) < 0xC0 and len(angles) > 100
    assert unit_angle(5) == unit_angle(5)                   # deterministic
    assert unit_angle(5, 0x80) == 0x80 and unit_angle(5, 8 << 4) == 0x80


def test_simulation_advances_the_tick_and_leaves_units_idle():
    w = world()
    w.add_unit(unit(1, 12, 12))
    before = repr(w.units[UNIT_ID_BASE + 1])
    sim = Simulation(w)
    for _ in range(100):
        sim.step()
    assert w.tick == 100
    assert repr(w.units[UNIT_ID_BASE + 1]) == before        # no behaviour yet
    assert w.units[UNIT_ID_BASE + 1].action == IDLE and w.units[UNIT_ID_BASE + 1].action_start_tick == 0


def test_dump_covers_units_and_items():
    w = world()
    w.add_unit(unit(1, 12, 12))
    w.add_item(Item(ITEM_ID_BASE, 5, 5, gold=100, codes=(0x101,)))
    d = w.dump()
    assert d["units"][0][0] == UNIT_ID_BASE + 1 and d["items"] == [[ITEM_ID_BASE, 5, 5, 128, 128, 100, [0x101], []]]
    h = w.dump_hash()
    w.units[UNIT_ID_BASE + 1].hp = 9
    assert w.dump_hash() != h


# --- every campaign map --------------------------------------------------------------------

MAPS = campaign_maps(GFS) if GFS else []
needs_maps = pytest.mark.skipif(not MAPS, reason="game files not present")


@pytest.fixture(scope="module")
def assets():
    return AssetCache(GFS)


@needs_maps
@pytest.mark.parametrize("name", MAPS)
def test_every_map_units_items_players_match_the_parsed_records(name, assets):
    m = open_map(name, GFS)
    w = World.from_map(m, assets)
    ground = m.ground_groups
    assert len(w.units) == len(m.units)
    assert len(w.items) == len({(g.x >> 8, g.y >> 8) for g in ground})          # one pile per cell
    assert sum(i.gold for i in w.items.values()) == sum(g.extra for g in ground)
    assert sum(len(i.groups) for i in w.items.values()) == len(ground)
    assert sorted(w.players) == list(range(1, len(m.players) + 1))
    assert [p.colour for p in w.players.values()] == [p.colour for p in m.players]
    assert all(u.owner in w.players for u in w.units.values())
    # ids: 0x6000 + uid in record order; items: section 8 order
    assert [u.id for u in w.units.values()] == [UNIT_ID_BASE + r.uid for r in m.units]
    assert all(u.id not in w.objects for u in w.units.values())
    assert [i.id for i in w.items.values()] == sorted(i.id for i in w.items.values())
    for r, u in zip(m.units, w.units.values()):
        assert (u.x, u.y) == (r.x >> 8, r.y >> 8) and u.type_id == r.type and u.owner == r.owner
        assert u.human == r.is_human and 0 <= u.hp and u.hp_max > 0 and u.action == IDLE
    # everything resolves (nothing silently dropped), and the report says so
    assert not w.report.unknown_units
    assert all(u.known for u in w.units.values())
    # indexes hold exactly the entities, units never reach the block layer
    assert sum(len(s) for s in w._ucells.values()) == len(w.units)
    assert sum(len(s) for s in w._icells.values()) == len(w.items)
    assert np.array_equal(w.block, w.rebuild_block())


@needs_maps
def test_hp_overrides_and_facing_range(assets):
    total = 0
    for name in MAPS[:6]:
        m = open_map(name, GFS)
        w = World.from_map(m, assets)
        for r, u in zip(m.units, w.units.values()):
            if r.max_hp != 0xFFFF and not (r.is_human and r.hp == r.max_hp):
                assert u.hp_max == r.max_hp
                total += 1
            assert 0x40 <= u.facing < 0xC0
        w2 = World.from_map(m, assets, facing=0x80)
        assert {u.facing for u in w2.units.values()} == {0x80}
    assert total


@needs_maps
def test_unknown_unit_types_are_reported_not_dropped(assets):
    m = open_map(MAPS[0], GFS)
    import dataclasses
    bad = dataclasses.replace(m.units[0], type=9999)
    m.units[0] = bad                                            # Map caches the parsed list
    w = World.from_map(m, assets)
    assert len(w.units) == len(m.units)
    assert w.report.unknown_units and w.report.unknown_units[0][1] == 9999
    assert not w.units[UNIT_ID_BASE + bad.uid].known


@needs_maps
def test_difficulty_tweak_scales_monsters_only_and_the_default_is_neutral(assets):
    """`FUN_00561bf9` 0x561e20: mode 2 (the server ctor default) skips; 1 = x0.5 template HP, 3 = x1.5; humans and map overrides are not scaled."""
    m = open_map(MAPS[0], GFS)
    base = World.from_map(m, assets)
    assert World.from_map(m, assets, difficulty=2).dump() == base.dump()
    assert all(u.tweak == 0 for u in base.units.values())
    easy, hard = World.from_map(m, assets, difficulty=1), World.from_map(m, assets, difficulty=3)
    seen = 0
    for r, b, e, h in zip(m.units, base.units.values(), easy.units.values(), hard.units.values()):
        if r.is_human:
            assert (e.hp_max, h.hp_max, e.tweak, h.tweak) == (b.hp_max, b.hp_max, 0, 0)
        elif r.max_hp == 0xFFFF and b.stats is not None:
            assert e.hp_max == int(b.stats.hp_max * 0.5) and h.hp_max == int(b.stats.hp_max * 1.5)
            assert (e.tweak, h.tweak) == (1, 3)
            seen += 1
        elif r.max_hp != 0xFFFF:
            assert e.hp_max == h.hp_max == r.max_hp
    assert seen
