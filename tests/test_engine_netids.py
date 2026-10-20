"""The server's free-id bitmap (engine/netids.py, combat.md 12.11 item 1): synthetic worlds, always run."""

from engine import party as PT
from engine.netids import NetIds
from engine.sim import death, spells

from test_engine_ai import hero, unit, world
from test_engine_minions import FakeAssets, caster, world as minion_world
from test_engine_party import Assets


def test_lowest_free_id_never_zero_and_free_reuses():
    n = NetIds()
    assert [n.alloc() for _ in range(4)] == [1, 2, 3, 4]
    n.free(2)
    assert n.alloc() == 2 and n.alloc() == 5
    n.free(0)                                  # id 0 is reserved (`FUN_004f8cc9` sets bit 0)
    assert n.alloc() == 6
    n.free(0x6000)                             # >= 0x6000: never recorded
    n.used.add(0x6000)


def test_piles_take_ids_first_then_the_hero_gets_the_next_free_one():
    w = world()
    a = w.place_pile(10, 10, 5, [1])
    b = w.place_pile(11, 10, 0, [2])
    assert (a.net_id, b.net_id) == (1, 2)
    placed = PT.place_party(w, Assets(), [(24, 24)])
    assert placed[0].net_id == 3 and placed[0].oid == 3
    w.remove_item(a.id)                        # a picked-up pile frees its id
    c = w.place_pile(12, 10, 0, [3])
    assert c.net_id == 1


def test_a_map_unit_keeps_its_file_id():
    w = world()
    u = unit(w, 7, 20, 20, 2)
    assert u.net_id == 0 and u.oid == u.id


def test_a_summoned_minion_gets_an_id_and_its_master_is_the_casters_oid():
    w = minion_world(seed=5)
    c = caster(w, skill=60)
    c.net_id = 0x45
    m = spells.summon_release(w, c)
    assert m.master == 0x45 and m.net_id == 1
    c2 = hero(w, 9, 30, 30)
    c2.human, c2.skills = True, (0, 0, 0, 0, 0, 60)
    m2 = spells.summon_release(w, c2)
    assert m2.master == c2.id and m2.net_id == 2          # a map-style caster: key = its `0x6000 + uid`


def test_a_ground_corpse_frees_its_id_at_stage_5_a_flyer_at_the_removal():
    w = minion_world(seed=5)
    ids = []
    for k, move in enumerate((1, 3)):
        u = unit(w, 40 + k, 10 + k, 10, 2)
        u.move_type = move
        u.net_id = w.net_ids.alloc()
        ids.append(u.net_id)
    ground, flyer = w.units[0x6000 + 40], w.units[0x6000 + 41]
    ground.hp = flyer.hp = -10
    w.bury(flyer.id)
    assert ids[1] not in w.net_ids.used and ids[0] in w.net_ids.used
    w.bury(ground.id)
    assert ids[0] in w.net_ids.used
    ground.hp = -601
    death.decay_step(w, ground)
    assert ids[0] not in w.net_ids.used
