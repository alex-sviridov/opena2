"""K5: picking up an item by click (docs/engine/items.md): the script's item instants share the pack with the pickup, the spatial index stays
consistent, replay is deterministic, and the quest items of the seven blocked campaign maps can be fetched and make their checks hold."""

import pytest

from engine.sim import PickUp, Simulation, gear
from engine.sim import triggers as T
from engine.world import World

from gear_helpers import code_of, world_with_hero
from helpers import GFS, have_install


def run(sim, n, hero=None):
    for _ in range(n):
        if hero is not None:
            hero.hp = 300
        sim.step()


def consistent(w):
    """world.items and the spatial index agree: every pile is found at its own cell, nothing else is."""
    for pid, p in w.items.items():
        assert pid in w.items_at(p.x, p.y)
    cells = {(p.x, p.y) for p in w.items.values()}
    for x in range(48):
        for y in range(48):
            assert bool(w.items_at(x, y)) == ((x, y) in cells)


# --- script items and the pack ---------------------------------------------------------------------------------------------------

def test_script_give_and_remove_use_the_pack_of_a_hero_with_a_loadout():
    w, u = world_with_hero()
    gear.give_item(w, u, code_of("Boots"))
    assert [i.code for i in u.pack] == [code_of("Boots")] and u.carried == (code_of("Boots"),)
    assert gear.remove_item(w, u, code_of("Helm")) is None
    assert gear.remove_item(w, u, code_of("Boots")).code == code_of("Boots")
    assert u.pack == () and u.carried == ()


def test_script_take_all_empties_the_pack_and_a_pile_keeps_the_modifiers():
    w, u = world_with_hero()
    gear.give_item(w, u, code_of("Helm"), ((15, 9, 0),))
    gear.give_item(w, u, code_of("Boots"))
    items = gear.take_all(w, u)
    assert [i.code for i in items] == [code_of("Helm"), code_of("Boots")] and u.pack == () and u.carried == ()
    gear.drop_items(w, u.x, u.y, items)
    (pile,) = w.items.values()
    assert pile.mods[0] == ((15, 9, 0),)
    consistent(w)


def test_a_unit_without_a_loadout_keeps_its_section_8_list():
    w, u = world_with_hero()
    u.equipment = ()
    gear.give_item(w, u, code_of("Boots"))
    assert u.carried == (code_of("Boots"),) and u.pack == ()
    assert gear.remove_item(w, u, code_of("Boots")).code == code_of("Boots") and u.carried == ()


def test_pickup_then_script_check_sees_the_item_and_remove_takes_it_back():
    w, u = world_with_hero()
    w.place_pile(24, 20, 0, [code_of("Boots")])
    sim = Simulation(w)
    sim.step([PickUp(1, (u.id,), (24, 20))])
    run(sim, 200)
    assert not w.items and T._has_item(u, code_of("Boots"))
    consistent(w)
    gear.remove_item(w, u, code_of("Boots"))
    assert not T._has_item(u, code_of("Boots"))


def test_pickup_out_of_range_walks_in_and_files_the_whole_sack():
    w, u = world_with_hero()
    w.place_pile(36, 30, 0, [code_of("Boots"), code_of("Helm")])
    sim = Simulation(w)
    sim.step([PickUp(1, (u.id,), (36, 30))])
    assert u.order == gear.PICK_ORDER and (u.x, u.y) == (20, 20)
    run(sim, 600)
    assert (u.x, u.y) == (36, 30) and sorted(u.carried) == sorted([code_of("Boots"), code_of("Helm")]) and not w.items
    consistent(w)


def test_pickup_replays_to_the_same_hash():
    def play():
        w, u = world_with_hero()
        w.place_pile(26, 22, 5, [code_of("Boots")])
        sim = Simulation(w)
        sim.step([PickUp(1, (u.id,), (26, 22))])
        run(sim, 200)
        return w.dump_hash()
    assert play() == play()


# --- the seven maps ------------------------------------------------------------------------------------------------------------------

MAPS = (21, 40, 63, 72, 80, 91, 102)


def _fetch(n):
    """Debug run of one map: every quest item a check waits for is fetched with a PickUp command by an unkillable hero standing a few cells away,
    after the guards around it were cleared and the monster that carries it was killed.  Returns (world, script, hero, codes)."""
    from allods2.cli import open_map
    from engine.coverage import quest_items_on_map
    from engine.session import build_game
    codes = quest_items_on_map(open_map(str(n)))
    w, _ = build_game(str(n), seed=1)
    sim = Simulation(w, triggers=True)
    hero = next(u for u in w.units.values() if u.owner == 1 and u.human)
    for code in sorted(codes):
        cell = next(((p.x, p.y) for p in w.items.values() if code in p.codes), None)
        if cell is None:
            car = next(u for u in w.units.values() if code in [c & 0xFFFF for c in u.carried])
            car.hp = -30
            run(sim, 60, hero)
            cell = next(((p.x, p.y) for p in w.items.values() if code in p.codes))
        for u in w.units.values():
            if u.owner != 1 and abs(u.x - cell[0]) <= 9 and abs(u.y - cell[1]) <= 9 and u.hp > 0:
                u.hp = -30
        run(sim, 40, hero)
        cell = next(((p.x, p.y) for p in w.items.values() if code in p.codes))         # the guards' loot can add piles, the quest pile stays
        spots = sorted(((a, b) for a in range(-7, 8) for b in range(-7, 8) if 3 <= max(abs(a), abs(b)) <= 7),
                       key=lambda d: (abs(max(abs(d[0]), abs(d[1])) - 5), d))
        assert any(T.teleport(w, hero, cell[0] + a, cell[1] + b) for a, b in spots), "no free start cell near %s" % (cell,)
        sim.step([PickUp(1, (hero.id,), cell)])
        for _ in range(900):
            hero.hp = 300
            sim.step()
            if code in hero.carried:
                break
        assert code in hero.carried, "map %d: item %x not picked up (hero at %s, sack at %s)" % (n, code, (hero.x, hero.y), cell)
    run(sim, 40, hero)
    return w, w.script, hero, codes


@pytest.mark.skipif(not have_install(), reason="needs the game install")
@pytest.mark.parametrize("n", MAPS)
def test_quest_item_can_be_reached_and_its_checks_hold(n):
    w, sc, hero, codes = _fetch(n)
    for c in sc.checks:
        if c.type in (12, 16, 17) and c.item in codes and c.unit is hero:
            assert sc.values[c.index] != (0xFF if c.type == 16 else 0), (n, c.index, c.type, sc.values[c.index])
    assert all(any(c & 0xFFFF == code for c in hero.carried) for code in codes)
    assert all(pid in w.items_at(p.x, p.y) for pid, p in w.items.items())


@pytest.mark.skipif(not have_install(), reason="needs the game install")
def test_info_panel_lists_the_carried_quest_items_of_the_own_hero():
    from allods2.assets import AssetCache
    from engine.ui import info
    w, u = world_with_hero()
    w.item_table = AssetCache().items()
    from allods2.formats.unitstats import UnitType
    u.stats = UnitType(u.stats.kind, 1, "Fighter_Hero_1", 1, 3, {k: u.stats.get(k, 0) for k in ("body", "reaction", "mind", "spirit")}, ("",) * 10, ())
    assert info.quest_items(w, u) == []
    gear.give_item(w, u, 0xE53)                     # a quest item (class 14, no potion / scroll / book prefix)
    gear.give_item(w, u, 0xE53)
    names = info.quest_items(w, u)
    assert names == [(names[0][0], 2)] and names[0][0]            # the two stack (no effects, FUN_005234c2)
    rows = info.quest_rows(w, u, 1)
    assert len(rows) == 1 and rows[0].y == info.QUEST_Y and rows[0].text.endswith(" x2")
    assert info.quest_rows(w, u, 2) == []           # not the viewer's unit


# --- P: pick up all sacks in sight (message 0x13, order 0x1a, Brain mode 12) ------------------------------------------------------------------

def test_pickall_walks_to_the_nearest_sack_then_the_next_and_stands_when_none_is_left():
    from engine.sim import PickAll
    w, u = world_with_hero()
    w.place_pile(22, 20, 0, [code_of("Boots")])
    w.place_pile(20, 25, 0, [code_of("Helm")])
    sim = Simulation(w)
    assert gear.nearest_sack(w, u) in ((22, 20), (20, 25))
    sim.step([PickAll(1, (u.id,))])
    assert u.order == gear.PICKALL_ORDER
    run(sim, 600)
    assert not w.items and sorted(u.carried) == sorted([code_of("Boots"), code_of("Helm")])
    assert u.order == 0xC                                   # nothing left in sight: FUN_0056d52b
    consistent(w)


def test_nearest_sack_prefers_the_own_cell_then_the_innermost_ring_and_takes_the_last_cell_found():
    w, u = world_with_hero()
    w.place_pile(24, 20, 0, [code_of("Boots")])             # ring 4
    w.place_pile(21, 21, 0, [code_of("Helm")])              # ring 1
    assert gear.nearest_sack(w, u) == (21, 21)
    w.place_pile(21, 19, 0, [code_of("Boots")])             # ring 1 too: d = 1 finds (21, 21) and (21, 19); the last one found wins
    assert gear.nearest_sack(w, u) == (21, 19)
    w.place_pile(20, 20, 0, [code_of("Boots")])
    assert gear.nearest_sack(w, u) == (20, 20)              # the own cell first
    for i in [i for i, p in w.items.items() if max(abs(p.x - 20), abs(p.y - 20)) < 10]:
        w.remove_item(i)
    w.place_pile(31, 20, 0, [code_of("Boots")])
    assert gear.nearest_sack(w, u) is None                  # a hero's sight here is 6 cells (the human recompute): ring 11 is not scanned


def test_pickall_ui_key_sends_only_hero_units():
    from engine.sim import PickAll
    from engine.ui import OrderInput
    oi = OrderInput(1, 640, lambda: (10, 11), lambda: "own", hero_fn=lambda i: i == 11)
    assert oi.key("p") == (PickAll(1, (11,)), None)
    oi = OrderInput(1, 640, lambda: (10, 11), lambda: "own", hero_fn=lambda i: False)
    assert oi.key("p") == (None, None)


# --- a doll item on the cursor leaves the doll and the hero's map sprite (FUN_004b012f, FUN_0046a215) --------------------------------------------

def test_hidden_slot_removes_the_item_from_the_equipped_view_and_the_hero_look():
    from engine.ui import info, pack
    from engine import herolook
    w, u = world_with_hero()
    gear.give_item(w, u, code_of("Sword"))
    assert gear.move_item(w, u, gear.KIND_PACK, gear.KIND_SLOT, 0, 0, 1) and 1 in gear.slots_of(u)
    assert herolook._codes(w, u).get(1) == code_of("Sword") and 1 not in herolook._codes(w, u, 1)
    carried = pack.Carried(u.id, gear.KIND_SLOT, 0, 1, None)
    assert pack.hidden_slot(carried, u) == 1
    assert pack.hidden_slot(carried._replace(kind=gear.KIND_PACK), u) == 0
    assert pack.hidden_slot(None, u) == 0 and pack.hidden_slot(carried._replace(unit=u.id + 1), u) == 0
    assert 1 not in info.equipped_items(w, u, 1) and 1 in info.equipped_items(w, u)
