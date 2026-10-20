"""Hero gear against the install's data (engine/sim/gear.py): the start heroes and every human template, section 9 effects of piles and carried
items, the free-id bitmap of a real map.  Skipped without the game files."""

import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from allods2.formats import progression as prog
from allods2.formats import saves as S
from allods2.formats import unitstats as U
from engine import party as PT
from engine.sim import combatstats as cs
from engine.sim import gear
from engine.sim.combat import combat_stats
from engine.world import UNIT_ID_BASE, Unit, World
from helpers import GFS, needs_data

pytestmark = needs_data


@pytest.fixture(scope="module")
def assets():
    return AssetCache(None)


def _same(a, b):
    assert a.record == b.record and a.block.defence == b.block.defence and a.block.absorb == b.block.absorb
    assert a.block.prot == b.block.prot and a.block.res == b.block.res
    assert (a.windup, a.recovery, a.range, a.mage, a.has_weapon, a.weapon_weight, a.weapon_spell) == \
           (b.windup, b.recovery, b.range, b.mage, b.has_weapon, b.weapon_weight, b.weapon_spell)
    assert a.attrs is None or a.attrs == b.attrs


def test_every_human_template_gives_the_same_stats_through_an_explicit_loadout(assets):
    """The template-string path and the loadout path (items as objects with wire-style modifiers) must agree for all every human template."""
    table = assets.items()
    w = World.from_map(open_map("10", None), assets)
    n = 0
    for t in assets.unit_stats().types:
        if t.kind != U.HUMAN:
            continue
        u = Unit(UNIT_ID_BASE + 5000 + n, 1, 9, 2, 2, uid=5000 + n, hp=10, hp_max=10, human=True, stats=t)
        u.skills = prog.skills_of(t)
        u.xp, u.xp_total = prog.start_pools(u.skills)
        w.players.setdefault(9, w.players[next(iter(w.players))])
        want = cs.human_stats(t, table, u.skills)
        assert gear.ensure_loadout(w, u)
        _same(combat_stats(w, u), want)
        n += 1
    assert n > 250


def test_start_mage_staff_keeps_its_cast_spell_and_a_fresh_party_hero_is_unchanged(assets):
    table = assets.items()
    t = next(x for x in assets.unit_stats().types if x.name == "Start_MM")
    st = cs.human_stats(t, table)
    assert st.weapon_spell == (table.spell_id("Fire_Arrow"), 1) and st.mage and st.has_weapon
    w = World.from_map(open_map("10", None), assets)
    placed = PT.place_party(w, assets, [(40, 40)], start="MM")
    assert placed and placed[0].equipment == ()                  # a fresh hero keeps the template strings until an item message
    assert combat_stats(w, placed[0]).weapon_spell == st.weapon_spell


def test_a_record_hero_equips_its_items_and_the_effects_apply(assets):
    table = assets.items()
    t = next(x for x in assets.unit_stats().types if x.name == "Start_MM")
    staff = gear.make_item(table, cs.item_code(table.resolve(*table.parse_equipment("Wood Staff {castSpell=Lightning:7}", 0))),
                           table.parse_effects("castSpell=Lightning:7"))
    ring = gear.make_item(table, cs.item_code(table.resolve(*table.parse_equipment("Uncommon Silver Ring {protectionFire=30, Spirit=5}", 2))),
                          table.parse_effects("protectionFire=30, Spirit=5"))
    sword = gear.make_item(table, cs.item_code(table.resolve(*table.parse_equipment("Iron Long Sword", 0))))
    rec = S.Character(identity=S.Identity((1, 2), 0, "Hero", 0x40, 4, 5), stats=S.Stats(0, 0, 0, 0, 10, (14, 30, 20, 40), 0b110, 3, (100, 100, 100, 100, 100)),
                      settings=bytes(2560), equipment=S.ItemPacket([staff, S.Item(0, 0), ring] + [S.Item(0, 0)] * 9),
                      pack=S.ItemPacket([sword, S.Item(code=0x0E01, count=3)]))
    w = World.from_map(open_map("10", None), assets)
    u = PT.place_party(w, assets, [(40, 40)], record=rec)[0]
    slots = gear.slots_of(u)
    assert slots[1].code == staff.code and ring.code in [i.code for i in slots.values()]
    st = combat_stats(w, u)
    bare = cs.human_stats(u.stats, table, u.skills, gear={})
    assert st.weapon_spell == (table.spell_id("Lightning"), 7)
    assert st.block.prot[1] > bare.block.prot[1]
    assert st.attrs[3] == bare.attrs[3] + 5
    assert u.hp == u.hp_max and u.mana == u.mana_max > 0
    # the sword (a fighter's weapon) stays in the pack: a mage may not wield it
    assert gear.move_item(w, u, 2, 1, 0, 0) and gear.slots_of(u)[1].code == staff.code and u.pack[0].code == sword.code
    assert [i.code for i in u.pack][1] == 0x0E01


def test_section9_effects_survive_in_piles_and_carried_items():
    assets = AssetCache(None)
    w = World.from_map(open_map("83", None), assets)
    (pile,) = w.items.values()
    assert pile.mods and pile.mods[0] == ((16, 5, 0),)
    w = World.from_map(open_map("70", None), assets)
    u = next(u for u in w.units.values() if u.carried_mods)
    assert u.carried_mods[0][0] == (25, 70, 0) and len(u.carried) == len(u.carried_mods)
    # the death drop keeps them
    from engine.sim import death
    u.hp = -20
    death.drop_loot(w, u)
    drop = w.items[max(w.items)]
    assert drop.mods and drop.mods[0] == u.carried_mods[0]


def test_a_dropped_orc_shaman_staff_keeps_its_cast_spell(assets):
    table = assets.items()
    t = next(x for x in assets.unit_stats().types if x.name == "Orc_Shaman.2")
    w = World.from_map(open_map("10", None), assets)
    x, y = next((x, y) for y in range(20, 60) for x in range(20, 60) if not w.pile_blocked(x, y) and not w.items_at(x, y))
    m = Unit(UNIT_ID_BASE + 9000, 60, 2, x, y, uid=9000, hp=-20, hp_max=10, stats=t)
    w.add_unit(m)
    from engine.sim import death
    death.drop_loot(w, m)
    pile = next(p for p in w.items.values() if (p.x, p.y) == (x, y))
    i = [k for k, c in enumerate(pile.codes) if c == 0x810E][0]      # Wood Shaman Staff (combat.md 12.4)
    assert pile.mods[i] == ((41, table.spell_id("Fire_Arrow"), 5),)
    # picking it up gives the object back with its effect: weapon_spell after equipping
    items = gear.pile_items(w, pile)
    assert gear.resolve(table, items[i]).effects[0].kind == 41


def test_free_ids_of_a_real_map(assets):
    w = World.from_map(open_map("83", None), assets)
    assert len(w.items) == 1 and w.net_ids.used == {0, 1}
    placed = PT.place_party(w, assets, [(40, 40)], count=2)
    assert [u.net_id for u in placed] == [2, 3]
