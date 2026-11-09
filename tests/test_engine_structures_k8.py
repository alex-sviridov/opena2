"""K8: the other usable structures (docs/engine/structures.md 3, 7): wells (3 charges, Potion Big Healing / Mana through the item use), signposts (the
instant at every use), graves (nothing), altars (the K6 toggle), the exe's lookup order A then B, determinism."""

import pytest

from allods2.formats import itemdefs as I
from engine.sim import Simulation, UseStructure
from engine.sim import structures as st
from engine.world import FLAG_DESTROYED, MapObject

from gear_helpers import world_with_hero
from helpers import have_install


def table_with_potions(base):
    """The gear test table plus the two well potions, as data.bin has them (special items with a modifier text)."""
    defs = list(base.defs)
    for i, (n, text) in enumerate((("Potion Big Healing", "health=+100"), ("Potion Big Mana", "mana=+100")), 50):
        defs.append(I.ItemDef(I.SPECIAL, 14, i, n, 10000, 1, {"price": 10000, "weight": 1}, flag=1, effects_text=text))
    return I.ItemTable(defs, base.qualities, base.materials, base.stats, base.spells)


def near(u, hp):
    """HP within the regeneration of the few ticks of the walk (a few points, every 64 ticks); a well would add 100."""
    return hp <= u.hp <= hp + 8


def hero_world(**kw):
    w, u = world_with_hero(**kw)
    w.item_table = table_with_potions(w.item_table)
    return w, u


def structure(w, uid, x, y, type_id, hp):
    ob = MapObject(0x6000 + uid, "structure", type_id, x, y, uid=uid, hp=hp, hp_max=3, owner=0)
    w.add_object(ob)
    return ob


def use(w, u, ob, ticks=300):
    """Command the use and step until the unit stands again (order 0xc): the regeneration (every 64 ticks) stays out of the numbers."""
    sim = Simulation(w)
    sim.step([UseStructure(1, (u.id,), ob.id)])
    for _ in range(ticks):
        sim.step()
        if u.order == 0xC:
            break
    return sim


def again(sim, w, u, ob):
    sim.step([UseStructure(1, (u.id,), ob.id)])
    for _ in range(100):
        sim.step()
        if u.order == 0xC:
            break


def test_health_well_heals_100_capped_and_runs_out_after_three_uses():
    w, u = hero_world()
    well = structure(w, 1, 26, 20, 15, 3)
    u.hp = 10
    sim = use(w, u, well)
    assert well.hp == 2 and near(u, 110)             # worked example: 10 + 100 (the maximum is higher: no cap here)
    for n, healed in ((1, True), (0, True), (0, False)):             # uses 2 and 3 heal, the 4th finds the well empty: nothing, no message
        u.hp = 1
        again(sim, w, u, well)
        assert well.hp == n and (u.hp >= 101) == healed
        assert healed or near(u, 1)
    assert not u.pack                                                # the potion is drunk, never filed in the pack


def test_mana_well_gives_100_mana_and_leaves_health_alone():
    w, u = hero_world(mage=True)
    well = structure(w, 1, 26, 20, 16, 3)
    u.mana, u.hp = 5, 40
    use(w, u, well)
    assert well.hp == 2 and u.mana == u.mana_max and 40 <= u.hp <= 50      # 5 + 100 capped at the maximum


def test_a_full_unit_still_burns_a_charge():
    w, u = hero_world()
    well = structure(w, 1, 26, 20, 15, 3)
    use(w, u, well)
    assert well.hp == 2 and u.hp == u.hp_max


def test_the_well_state_is_sent_but_the_art_never_changes_and_there_is_no_sound():
    w, u = hero_world()
    well = structure(w, 1, 26, 20, 15, 1)
    use(w, u, well)
    assert well.hp == 0 and not well.flags & FLAG_DESTROYED
    assert [(e.uid, e.hp) for e in w.events if isinstance(e, st.StructureState)] == [(1, 0)]       # message 0x82: the only traffic (structures.md 4.1, 7.1)


def test_lookup_b_takes_the_first_structure_near_the_hero_even_if_it_is_no_well():
    w, u = hero_world()
    structure(w, 1, 24, 19, 39, 1)                                  # a grave earlier in the list, within 2 of the stop cell: it shadows the well
    well = structure(w, 2, 26, 20, 15, 3)
    u.hp = 10
    use(w, u, well)
    assert well.hp == 3 and near(u, 10)


def test_a_switch_use_also_runs_lookup_b():
    w, u = hero_world()
    sw = structure(w, 1, 26, 20, 28, 1)
    use(w, u, sw)
    assert sw.hp == 0 and sw.flags & FLAG_DESTROYED


def test_graves_do_nothing_but_the_walk():
    for type_id in (39, 40):
        w, u = hero_world()
        g = structure(w, 1, 26, 20, type_id, 0)
        u.hp = 10
        use(w, u, g)
        assert (g.hp, g.flags) == (0, 0) and near(u, 10) and u.order == 0xC and not w.events


def test_an_altar_toggles_like_a_switch_and_back():
    w, u = hero_world()
    a = structure(w, 1, 26, 20, 76, 1)
    sim = use(w, u, a)
    assert a.hp == 0 and a.flags & FLAG_DESTROYED
    again(sim, w, u, a)
    assert a.hp == 1 and not a.flags & FLAG_DESTROYED


def test_a_signpost_runs_its_instant_at_every_use_and_index_0_is_never_run(monkeypatch):
    from engine.sim import triggers
    calls = []
    monkeypatch.setattr(triggers, "run_instant", lambda world, script, index: calls.append(index))
    for index, expect in ((3, [3, 3]), (0, []), (-1, [])):
        calls.clear()
        w, u = hero_world()
        w.script = object()
        p = structure(w, 1, 26, 20, 71, 0)
        w.pointers = {1: index}
        sim = use(w, u, p)
        again(sim, w, u, p)
        assert calls == expect


def test_a_signpost_ends_the_case_before_lookup_b():
    w, u = hero_world()
    structure(w, 1, 25, 20, 71, 0)                                  # signpost first: lookup A returns it and breaks
    well = structure(w, 2, 26, 21, 15, 3)
    u.hp = 10
    use(w, u, well)
    assert well.hp == 3 and near(u, 10)


def test_wells_replay_to_the_same_hash():
    out = []
    for _ in range(2):
        w, u = hero_world()
        well = structure(w, 1, 26, 20, 15, 3)
        u.hp = 10
        sim = use(w, u, well)
        out.append((w.dump_hash(), u.hp, well.hp, sim.log))
    assert out[0] == out[1]
    from engine.sim import structures as m
    assert "rand" not in open(m.__file__).read().split("def use_well")[1]          # no RNG anywhere in a use (structures.md 7.1)


# --- the real maps --------------------------------------------------------------------------------------------------------------

import os

ALL_MAPS = [10, 20, 21, 30, 31, 40, 42, 43, 50, 52, 53, 60, 62, 63, 70, 73, 74, 75, 76, 77, 80, 83, 86, 87, 92, 93, 94, 95, 96, 100, 102, 103, 110]
KINDS = {15: "well2", 16: "well3", 39: "grave", 40: "grave", 70: "pointer", 71: "pointer", 72: "pointer", 73: "pointer", 74: "pointer", 75: "pointer"}


def _stand_next_to(w, hero, ob):
    from engine.sim import triggers as T
    for a, b in ((1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
        if T.teleport(w, hero, ob.x + a, ob.y + b):
            return True
    return False


def use_on_map(n):
    """Use every well, signpost and grave of map `n` once with the hero standing next to it: returns [(uid, type, kind, ok, text)].  The lookup quirk can
    hand the use to another structure within 2 cells, so the expectation follows the exe's lookup (`find_structure`), not the clicked structure."""
    from engine.session import build_game
    from engine.sim import triggers
    w, _ = build_game(str(n), seed=1)
    sim = Simulation(w, triggers=True)
    hero = next(u for u in w.units.values() if u.owner == 1 and u.human)
    rows = []
    for ob in [o for o in w.objects.values() if o.kind == "structure" and o.type_id in KINDS]:
        if not _stand_next_to(w, hero, ob):
            rows.append((ob.uid, ob.type_id, KINDS[ob.type_id], None, "no free cell"))
            continue
        hero.hp, hero.mana = 1, 1
        w.events.clear()
        a = st.find_structure(w, (hero.x - 1, hero.y - 1))
        b = st.find_structure(w, (hero.x, hero.y))
        charges = {o.uid: o.hp for o in w.objects.values() if o.kind == "structure" and o.type_id in (15, 16)}
        sim.step([UseStructure(1, (hero.id,), ob.id)])
        for _ in range(400):
            hero.hp = max(hero.hp, 1)
            sim.step()
            if hero.order == 0xC:
                break
        used = {u: c for u, c in charges.items() if next(o for o in w.objects.values() if o.kind == "structure" and o.uid == u).hp != c}
        want_b = b is not None and b.type_id in st.WELLS and charges.get(b.uid, 0) > 0 and not (a is not None and a.type_id in st.POINTER_TYPES | st.SHOP_INN_TYPES)
        ok = set(used) == ({b.uid} if want_b else set())
        if a is not None and a.type_id in st.POINTER_TYPES and w.pointers.get(a.uid, -1) > 0:      # a live signpost: its instant (a story message in the install) ran
            from engine.sim.triggers import ScriptMessage
            ok = ok and any(isinstance(e, ScriptMessage) for e in w.events)
        rows.append((ob.uid, ob.type_id, KINDS[ob.type_id], ok, "A=%s B=%s used=%s" % (a and a.uid, b and b.uid, sorted(used))))
    return rows


@pytest.mark.skipif(not have_install(), reason="needs the game install")
@pytest.mark.parametrize("n", [73, 40, 10])
def test_real_maps_use_every_well_signpost_and_grave(n):
    rows = use_on_map(n)
    assert rows and all(r[3] in (True, None) for r in rows), rows


@pytest.mark.skipif(not have_install() or not os.environ.get("ALLODS2_ALL_MAPS"), reason="ALLODS2_ALL_MAPS=1")
def test_every_campaign_map_with_usable_structures():
    bad = []
    for n in ALL_MAPS:
        rows = use_on_map(n)
        bad += [(n,) + r for r in rows if r[3] is False]
    assert not bad, bad


def test_the_info_panel_of_a_hovered_well_shows_the_falling_charges():
    from engine.ui import info
    w, u = hero_world()
    well = structure(w, 1, 26, 20, 15, 3)
    rows = lambda: info.structure_rows(well, type("T", (), {"line": lambda self, i: "Health"})(), ["", "Well"] * 20)[-1].text
    assert rows() == "3/3"
    use(w, u, well)
    assert rows() == "2/3"                                           # the panel reads the structure's HP (obj+0x104, written by message 0x82)


@pytest.mark.skipif(not have_install(), reason="needs the game install")
def test_map_53_well_uid_41_starts_empty_and_every_other_campaign_well_has_3_charges():
    """`intact == 0` -> `+0x42 = 0` (FUN_00561422, the plain structure branch): that well gives nothing; the 25 others hold 3 (structures.md 7.1 f)."""
    from engine.session import build_game
    charges = {}
    for n in (30, 40, 52, 53, 60, 62, 63, 73, 74, 75, 77, 83, 86, 87, 100):
        w, _ = build_game(str(n), seed=1)
        charges.update({(n, o.uid): o.hp for o in w.objects.values() if o.kind == "structure" and o.type_id in (15, 16)})
    assert [k for k, v in charges.items() if v != 3] == [(53, 41)] and charges[(53, 41)] == 0 and len(charges) == 26
