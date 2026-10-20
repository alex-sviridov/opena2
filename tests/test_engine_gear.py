"""Hero gear (engine/sim/gear.py, docs/data/items.md 15): equip / unequip / use / drop / pickup, the load and the effects of the equipped items.
Synthetic (tests/gear_helpers.py), always run; the start heroes of the install are in the needs_data section at the end."""

import pytest

from allods2.formats import saves as S
from engine.sim import DropGold, MoveItem, PickUp, Simulation, gear
from engine.sim.combat import combat_stats
from engine.sim.movement import unit_speed
from engine.world import PILE_ID_BASE

from gear_helpers import code_of, item, table, world_with_hero
from helpers import GFS, needs_data


def fill(u, *items):
    u.pack = tuple(items)


def mv(w, u, sk, dk, si=0, di=0, count=1):
    return gear.move_item(w, u, sk, dk, si, di, count)


# --- pack rules --------------------------------------------------------------------------------------------------------------

def test_potions_scrolls_and_unmodified_items_stack_but_modified_items_do_not():
    t = table()
    pack = []
    for it in (item("Potion Healing"), item("Potion Healing", count=3), item("Scroll Fire", mods=((41, 1, 50),)), item("Scroll Fire", mods=((41, 1, 50),)),
               item("Sword"), item("Sword"), item("Sword", mods=((12, 5, 0),)), item("Sword", mods=((12, 5, 0),))):
        gear.pack_insert(t, pack, it)
    assert [(i.code, i.count) for i in pack] == [(code_of("Potion Healing"), 4), (code_of("Scroll Fire"), 2), (code_of("Sword"), 2),
                                                 (code_of("Sword"), 1), (code_of("Sword"), 1)]
    assert gear.pack_weight(t, pack) == 4 * 1 + 2 * 1 + 2 * 20 + 2 * 20


def test_pack_insert_index_and_take_split():
    t = table()
    pack = [item("Sword", mods=((12, 1, 0),)), item("Buckler")]
    gear.pack_insert(t, pack, item("Helm"), 1)
    assert [i.code for i in pack] == [code_of("Sword"), code_of("Helm"), code_of("Buckler")]
    gear.pack_insert(t, pack, item("Boots"), 99)
    assert pack[-1].code == code_of("Boots")
    stack = [item("Potion Healing", count=5)]
    got = gear.pack_take(stack, 0, 2)
    assert (got.count, stack[0].count) == (2, 3)
    assert gear.pack_take(stack, 0, 3).count == 3 and stack == []
    assert gear.pack_take(stack, 0, 1) is None


# --- equip rules -------------------------------------------------------------------------------------------------------------

def test_a_fighter_equips_a_sword_from_the_pack_and_the_combat_numbers_follow():
    w, u = world_with_hero()
    bare = combat_stats(w, u)
    fill(u, item("Sword"))
    assert mv(w, u, 2, 1, 0, 0)
    st = combat_stats(w, u)
    assert u.pack == () and gear.slots_of(u)[1].code == code_of("Sword")
    assert st.has_weapon and st.record.lo == bare.record.lo + 5 + 25 // 5 and st.record.sp == bare.record.sp + 4 and st.record.kind == 1
    assert st.record.skill > bare.record.skill                      # to-hit 3 + 3 * blade skill
    assert st.weapon_weight == 20


def test_refused_items_go_back_to_the_pack_at_their_place():
    w, u = world_with_hero()                                        # a fighter may not wield a staff (suitable_for 2)
    fill(u, item("Buckler"), item("Staff"), item("Helm"))
    assert mv(w, u, 2, 1, 1, 0)
    assert gear.slots_of(u) == {} and [i.code for i in u.pack] == [code_of("Buckler"), code_of("Staff"), code_of("Helm")]
    w2, m = world_with_hero(mage=True)                              # a mage may not wield a sword
    fill(m, item("Sword"))
    assert mv(w2, m, 2, 1, 0, 0) and gear.slots_of(m) == {} and len(m.pack) == 1
    fill(m, item("Staff"))
    assert mv(w2, m, 2, 1, 0, 0) and gear.slots_of(m)[1].code == code_of("Staff")


def test_the_replaced_item_returns_to_the_pack_index_the_new_one_came_from():
    w, u = world_with_hero()
    fill(u, item("Sword"), item("Helm"), item("Great Sword"))
    mv(w, u, 2, 1, 0)
    assert [i.code for i in u.pack] == [code_of("Helm"), code_of("Great Sword")]
    mv(w, u, 2, 1, 1)                                               # the great sword (index 1) replaces the sword, which goes to index 1
    assert gear.slots_of(u)[1].code == code_of("Great Sword")
    assert [i.code for i in u.pack] == [code_of("Helm"), code_of("Sword")]


def test_two_handed_weapons_and_shields_push_each_other_into_the_pack():
    w, u = world_with_hero()
    fill(u, item("Buckler"), item("Great Sword"))
    mv(w, u, 2, 1, 0)
    assert gear.slots_of(u).keys() == {2}
    mv(w, u, 2, 1, 0)                                               # the two-handed sword: the shield moves to the pack
    assert gear.slots_of(u).keys() == {1} and [i.code for i in u.pack] == [code_of("Buckler")]
    mv(w, u, 2, 1, 0)                                               # and back: the shield sends the weapon away
    assert gear.slots_of(u).keys() == {2} and [i.code & 0xFFF for i in u.pack] == [code_of("Great Sword")]


def test_armour_goes_to_the_slot_of_its_class_and_a_second_piece_replaces_it():
    w, u = world_with_hero()
    fill(u, item("Helm"), item("Hat"), item("Boots"))
    base = combat_stats(w, u).block
    mv(w, u, 2, 1, 0)
    mv(w, u, 2, 1, 0)                                               # the hat replaces the helm (both slot 4); the helm is filed at index 0
    mv(w, u, 2, 1, 1)
    assert gear.slots_of(u).keys() == {4, 9} and [i.code for i in u.pack] == [code_of("Helm")]
    st = combat_stats(w, u)
    assert st.block.defence == base.defence + 1 + 2 and st.block.absorb == base.absorb


def test_equipping_a_slot_to_the_pack_and_dropping_on_the_ground():
    w, u = world_with_hero()
    fill(u, item("Sword", mods=((41, 1, 5),)))
    mv(w, u, 2, 1, 0)
    assert combat_stats(w, u).weapon_spell == (1, 5)
    assert mv(w, u, 1, 2, 0, 0)                                     # slot index 0 = the weapon, to pack index 0
    assert u.equipment[0].code == 0 and u.pack[0].mods == ((41, 1, 5),) and combat_stats(w, u).weapon_spell is None
    assert mv(w, u, 2, 3, 0, 22 | 21 << 8)                          # to the ground, the target cell (22, 21) is within 2 cells
    (pile,) = w.items.values()
    assert (pile.x, pile.y, pile.codes, pile.mods) == (22, 21, (code_of("Sword"),), (((41, 1, 5),),)) and u.pack == ()
    assert mv(w, u, 2, 3, 0, 0) is False                            # the pack is empty


def test_a_far_drop_target_falls_back_to_the_hero_cell():
    w, u = world_with_hero()
    fill(u, item("Helm"))
    mv(w, u, 2, 3, 0, 40 | 40 << 8)
    (pile,) = w.items.values()
    assert (pile.x, pile.y) == (20, 20)


def test_a_cell_that_cannot_hold_a_pile_loses_the_dropped_item():
    w, u = world_with_hero()
    w._block[20, 20] |= 1
    fill(u, item("Helm"))
    mv(w, u, 2, 3, 0, 0)
    assert not w.items and u.pack == ()


# --- effects of the items ----------------------------------------------------------------------------------------------------

def test_item_modifiers_reach_the_stats():
    w, u = world_with_hero()
    base = combat_stats(w, u)
    hp0 = u.hp_max
    fill(u, item("Helm", mods=((2, 4, 0), (15, 6, 0), (21, 10, 0), (7, 30, 0), (17, 2, 0), (27, 5, 0))))
    mv(w, u, 2, 1, 0)
    st = combat_stats(w, u)
    assert st.attrs[0] == base.attrs[0] + 4                                  # Body
    assert st.block.defence == base.block.defence + 3 + 6 + 0 and st.block.prot[1] == base.block.prot[1] + 10
    assert u.hp_max > hp0 + 30 and u.attr_bonus[0] == 4
    assert u.skill_bonus[1] == 5 and st.speed_bonus == 2
    assert unit_speed(u) == unit_speed.__globals__["prog"].derived_speed(u.stats, u.type_id) + 2     # Reaction rule + the speed modifier
    assert u.gear_speed == unit_speed(u)
    mv(w, u, 1, 2, 3, 0)                                                     # slot 4 -> index 3 is the helm
    assert u.hp_max == hp0 and u.attr_bonus == () and u.skill_bonus == ()


def test_a_mage_gets_mana_from_mana_max_modifiers_and_a_fighter_does_not():
    w, m = world_with_hero(mage=True)
    mana0 = m.mana_max
    fill(m, item("Hat", mods=((10, 25, 0),)))
    mv(w, m, 2, 1, 0)
    assert m.mana_max == mana0 + 25
    w2, f = world_with_hero()
    fill(f, item("Hat", mods=((10, 25, 0),)))
    mv(w2, f, 2, 1, 0)
    assert f.mana_max == 0


def test_the_load_slows_a_hero_once_it_reaches_the_capacity():
    w, u = world_with_hero(body=3)                                           # capacity 3 * 10 + 1 = 31, Reaction 30 -> speed 30 // 5 + 12 = 18
    assert unit_speed(u) == 18
    fill(u, item("Great Sword"), item("Buckler"))
    mv(w, u, 2, 1, 0)
    st = combat_stats(w, u)
    assert (st.load, st.capacity) == (40 + 10 // 2, 31)                      # the equipped weight plus half the pack
    assert unit_speed(u) == 18 - 45 // 31                                    # load // capacity
    mv(w, u, 1, 2, 0, 0)                                                     # sword into the pack: (40 + 10) // 2 = 25 < 31
    assert combat_stats(w, u).load == 25 and unit_speed(u) == 18


def test_the_speed_floor_is_six():
    w, u = world_with_hero(body=1)                                           # capacity 11
    fill(u, item("Great Sword"))
    mv(w, u, 2, 1, 0)
    assert unit_speed(u) == max(18 - 40 // 11, 6) == 15
    w2, v = world_with_hero(body=1, reaction=8)
    fill(v, item("Great Sword"))
    mv(w2, v, 2, 1, 0)
    assert unit_speed(v) == max(8 - 40 // 11, 6) == 6


def test_a_loadout_changes_spell_level_through_mind_and_skill_modifiers():
    from engine.sim import spells
    w, m = world_with_hero(mage=True)
    m.skills = (0, 0, 0, 0, 0, 40)
    class S_:                       # the level only reads the sphere
        sphere = 5
    base = spells.unit_level(m, S_)
    fill(m, item("Hat", mods=((3, 6, 0), (37, 10, 0))))                      # Mind +6, skillAstral +10 (a mage's skill kinds are 32..37)
    mv(w, m, 2, 1, 0)
    assert spells.unit_level(m, S_) == base + 6 + 10


# --- use ---------------------------------------------------------------------------------------------------------------------

def test_potions_are_used_by_putting_them_on_the_equipment_area():
    w, u = world_with_hero()
    u.hp = 10
    fill(u, item("Potion Healing", count=3), item("Potion Body"))
    body = u.stats.fields["body"]
    mv(w, u, 2, 1, 0, 0)                                                     # one of the stack: health +30
    assert u.hp == 40 and u.pack[0].count == 2 and gear.slots_of(u) == {}
    u.hp = u.hp_max - 5
    mv(w, u, 2, 1, 0, 0)
    assert u.hp == u.hp_max
    hp_max = u.hp_max
    mv(w, u, 2, 1, 1, 0)                                                     # Body +1: a permanent change of the base
    assert u.stats.fields["body"] == body + 1 and u.hp_max > hp_max and len(u.pack) == 1


def test_use_ignores_a_dead_hero_and_a_quest_item_is_consumed_without_effect():
    w, u = world_with_hero()
    fill(u, item("Quest Key"))
    mv(w, u, 2, 1, 0)
    assert u.pack == ()


# --- gold and pickup ---------------------------------------------------------------------------------------------------------

def test_drop_gold_validates_the_amount_and_drops_a_gold_pile():
    w, u = world_with_hero()
    w.players[1].gold = 100
    sim = Simulation(w)
    sim.step([DropGold(1, (u.id,), 0, (20, 21)), DropGold(1, (u.id,), 101, (20, 21))])
    assert w.players[1].gold == 100 and not w.items
    sim.step([DropGold(1, (u.id,), 60, (21, 21))])
    (pile,) = w.items.values()
    assert (w.players[1].gold, pile.gold, (pile.x, pile.y), pile.codes) == (40, 60, (21, 21), ())


def test_pickup_walks_to_the_sack_and_files_items_with_their_effects():
    w, u = world_with_hero()
    w.players[1].gold = 5
    w.place_pile(24, 20, 70, [code_of("Helm"), code_of("Sword")], mods=(((15, 9, 0),), ()))
    pile_id = next(iter(w.items))
    sim = Simulation(w)
    sim.step([PickUp(1, (u.id,), (30, 30))])                                # no sack there: nothing happens
    assert u.order == 0
    sim.step([PickUp(1, (u.id,), (24, 20), 0)])
    assert u.order == gear.PICK_ORDER
    for _ in range(400):
        sim.step()
        if pile_id not in w.items:
            break
    assert pile_id not in w.items and w.players[1].gold == 75
    assert [(i.code, i.mods) for i in u.pack] == [(code_of("Sword"), ()), (code_of("Helm"), ((15, 9, 0),))]    # index 0 each time: the second lands in front
    assert u.carried == (code_of("Sword"), code_of("Helm")) and (u.x, u.y) == (24, 20)
    for _ in range(40):
        sim.step()
    assert u.state != gear.PICK_STATE


def test_a_pickup_on_the_own_cell_files_at_once_at_the_next_pass():
    w, u = world_with_hero()
    w.place_pile(20, 20, 0, [code_of("Boots")])
    sim = Simulation(w)
    sim.step([PickUp(1, (u.id,), (20, 20))])
    for _ in range(40):
        sim.step()
    assert not w.items and [i.code for i in u.pack] == [code_of("Boots")]


def test_pile_net_id_is_freed_by_the_pickup():
    w, u = world_with_hero()
    pile = w.place_pile(20, 20, 0, [code_of("Boots")])
    assert pile.net_id in w.net_ids.used
    gear.pick_up(w, u, pile)
    assert pile.net_id not in w.net_ids.used


# --- death -------------------------------------------------------------------------------------------------------------------

def test_a_dying_hero_drops_pack_second_hand_weapon_and_armour_with_their_effects():
    from engine.sim import death
    w, u = world_with_hero()
    fill(u, item("Potion Healing", count=2), item("Sword", mods=((12, 3, 0),)), item("Buckler"), item("Helm", mods=((15, 4, 0),)), item("Boots"))
    mv(w, u, 2, 1, 1)
    mv(w, u, 2, 1, 1)
    mv(w, u, 2, 1, 1)
    assert [i.code for i in u.pack] == [code_of("Potion Healing"), code_of("Boots")]
    death.drop_loot(w, u)
    (pile,) = w.items.values()
    assert pile.codes == (code_of("Potion Healing"),) * 2 + (code_of("Boots"), code_of("Buckler"), code_of("Sword"), code_of("Helm"))
    assert pile.mods == ((), (), (), (), ((12, 3, 0),), ((15, 4, 0),))


@pytest.mark.parametrize("text,mods", [("Staff {castSpell=Fire_Arrow:5}", ((41, 1, 5),)), ("Staff", ())])
def test_template_equipment_keeps_its_castspell_in_the_dropped_pile(text, mods):
    """Combat 12.11 item 2: the dropped template weapon is the item object with its effects, not a 16-bit code."""
    from allods2.formats.unitstats import MONSTER, UnitType
    from engine.sim import death
    from engine.world import Unit, UNIT_ID_BASE
    w, _ = world_with_hero()
    t = UnitType(MONSTER, 7, "Shaman", 7, 60, {"hp_max": 10, "gold_chance": 0, "item_chance": 0}, (text, ""), ())
    m = Unit(UNIT_ID_BASE + 9, 60, 2, 30, 30, uid=9, hp=-20, hp_max=10, stats=t)
    w.add_unit(m)
    death.drop_loot(w, m)
    (pile,) = w.items.values()
    assert [c & 0xFFF for c in pile.codes] == [code_of("Staff")] and (pile.mods == (mods,) if mods else pile.mods == ())


def test_a_template_hero_gets_its_loadout_on_the_first_item_message_with_unchanged_stats():
    from dataclasses import replace
    from engine.sim import combatstats as cs
    w, u = world_with_hero()
    u.equipment = ()
    u.gear_speed = None
    u.stats = replace(u.stats, equipment=("Sword", "Buckler", "Helm", "Boots", "", "", "", "", "", ""))
    want = cs.human_stats(u.stats, w.item_table, u.skills)
    assert gear.ensure_loadout(w, u)
    st = combat_stats(w, u)
    assert st.record == want.record and st.block.defence == want.block.defence and st.has_weapon
    assert sorted(gear.slots_of(u)) == [1, 2, 4, 9] and u.pack == ()
    fill(u, item("Potion Healing"))
    assert mv(w, u, 1, 2, 0, 0)                                              # take the sword off into the pack
    assert not combat_stats(w, u).has_weapon and [i.code & 0xFFF for i in u.pack][0] == code_of("Sword")


def test_template_two_handed_weapon_and_shield_leave_the_weapon_in_the_pack():
    from dataclasses import replace
    w, u = world_with_hero()
    u.equipment = ()
    u.stats = replace(u.stats, equipment=("Great Sword", "Buckler", "", "", "", "", "", "", "", ""))
    gear.ensure_loadout(w, u)
    assert sorted(gear.slots_of(u)) == [2] and [i.code & 0xFFF for i in u.pack] == [code_of("Great Sword")]
