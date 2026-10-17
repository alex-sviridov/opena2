"""Tests for docs/data/spells.md (allods2.formats.spelldefs)."""

import importlib.util
import json
import os
import re

import pytest

from allods2 import databin as D
from allods2.formats import spelldefs as S
from allods2.spells import SPELL_NAMES, effect_id

from helpers import GFS, needs

needs_databin = needs("world", "data", "data.bin")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- synthetic table --------------------------------------------------------------------------


def params(**kw):
    p = dict.fromkeys(S.FIELDS, 0)
    p.update(damage_min=-1, damage_max=-1, defensive=-1)
    p.update(kw)
    return [p[n] for n in S.FIELDS]


def synthetic_db():
    db = D.DataBin()
    names = ["", "price", "body", "mind", "reaction", "spirit", "health", "healthMax", "x8", "x9", "x10", "x11",
             "toHit", "x13", "x14", "defence", "absorbtion", "speed", "rotationSpeed", "scanRange"]
    db.stats = [D.Record(n, [0] * 28) for n in names]
    recs = {n: D.Record("", []) for n in range(1, 35)}
    for n, rec in {
        1: D.Record("Fire Arrow", params(complication_level=3, mana_cost=3, sphere=1, target=1, delivery=2,
                                         max_range=7, speed=200, distribution=1, apply_method=1,
                                         damage_min=5, damage_max=10, scroll_cost=50, book_cost=1000), ("",)),
        12: D.Record("Invisibility", params(sphere=3, target=1, delivery=1, max_range=5, duration=10,
                                            defensive=1), ("Invisibility = ON",)),
        18: D.Record("Stone Curse", params(sphere=4, target=1, max_range=5, duration=10),
                     ('"absorbtion=+5:duration 8,defence=-20:duration 8"',)),
        21: D.Record("Haste", params(sphere=5, target=1, max_range=5, duration=10, defensive=1),
                     ("speed=+2: duration 30",)),
        23: D.Record("Teleport", params(sphere=5, target=2, max_range=1), ("",)),
        24: D.Record("Heal", params(sphere=5, target=1, max_range=6, damage_min=8, damage_max=16, defensive=1),
                     ("",)),
        17: D.Record("Wall of Earth", params(sphere=4, target=2, max_range=6, distribution=4, radius=2,
                                             area_duration=10), ("",)),
    }.items():
        recs[n] = rec
    db.spells = [recs[n] for n in range(1, 35)]
    return db


TEXTS = (["Fire Arrow", "x", "x", "x", "x", "x", "x", "x", "x", "x", "x", "Mage Cloak"],
         ["Fire Arrow (Homing)#Inflicts Fire damage to a single target", "Mage Cloak (Caster Only)#Hides"])


@pytest.fixture(scope="module")
def table():
    return S.build(synthetic_db(), TEXTS)


def test_build_numbers_and_empty_records(table):
    assert [d.number for d in table] == [1, 12, 17, 18, 21, 23, 24] and len(table) == 7
    assert table.extra_records == 27                                  # nameless records are counted, not listed
    assert table.get(1).name == "Fire Arrow" and table.get(2) is None


def test_fields_by_name(table):
    d = table.get(1)
    assert (d.complication_level, d.mana_cost, d.sphere, d.speed, d.scroll_cost, d.book_cost) == (3, 3, 1, 200, 50, 1000)
    assert d.raw == tuple(params(complication_level=3, mana_cost=3, sphere=1, target=1, delivery=2, max_range=7,
                                 speed=200, distribution=1, apply_method=1, damage_min=5, damage_max=10,
                                 scroll_cost=50, book_cost=1000))
    assert d.element == "fire" and d.missile and d.targets_unit and d.has_damage
    with pytest.raises(AttributeError):
        d.nonsense


def test_lookup_forms(table):
    assert table.lookup("Fire_Arrow").number == 1 and table.lookup("fire arrow").number == 1
    assert table.lookup("stone_curse").number == 18 and table.lookup("Stone Curse").number == 18
    assert table.lookup("Nothing") is None


def test_effect_and_sound_ids(table):
    d = table.get(1)
    assert (d.effect_id, d.hit_effect_id) == (effect_id("fire_arrow"), 11) and d.effect_id == 10
    assert d.sound_ids == (510, 511)                                  # 500 + effect id (FUN_00467da8)
    assert table.get(18).effect_id == 0x2c and d.key == "fire_arrow"


def test_handler_selection(table):
    assert table.get(1).handler == "damage"
    assert table.get(24).handler == "heal"                            # has damage params but its own case
    assert table.get(23).handler == "teleport" and table.get(17).handler == "wall_of_earth"


def test_modifier_text_terms(table):
    sc = table.get(18)
    assert sc.modifier_text == "absorbtion=+5:duration 8,defence=-20:duration 8"
    assert [(m.kind, m.value, m.mode, m.time) for m in sc.modifiers] == [(16, 5, 1, 8), (15, -20, 1, 8)]
    assert [(m.kind, m.value, m.time) for m in table.get(21).modifiers] == [(17, 2, 30)]
    assert table.get(12).modifiers == ()                              # "Invisibility = ON" is special-cased by the exe


def test_texts(table):
    d = table.get(1)
    assert d.display_name == "Fire Arrow" and d.kind_text == "Homing" and d.description.startswith("Inflicts Fire")
    assert table.get(12).display_name == "Mage Cloak" and table.get(12).description == "Hides"
    assert table.get(21).display_name == "Haste" and table.get(21).description == ""     # falls back to the data name


def test_level_of_clamps():
    assert S.level_of(50, 20) == 40 and S.level_of(10, 5) == 0 and S.level_of(255, 100) == 255


def test_scaled_damage_and_range(table):
    s = table.get(1).scaled(60)                                       # m = 3.0
    assert (s.damage_min, s.damage_spread, s.max_range, s.duration) == (15, 15, 9, 0)
    s0 = table.get(1).scaled(0)
    assert (s0.damage_min, s0.damage_spread, s0.max_range) == (5, 5, 7)
    assert table.get(23).scaled(30).max_range == 1 + 10               # teleport: level / 3
    assert table.get(24).scaled(29).max_range == 6                    # level / 30 truncates


def test_scaled_durations(table):
    assert table.get(12).scaled(20).duration == 20 << 4               # invisibility: level * 16
    assert table.get(18).scaled(50).duration == 50 * 15 * 16 * 2 // 100
    assert table.get(21).scaled(0).duration == 10 * 16                # p14 * 1.1^level * 16
    assert table.get(21).scaled(10).duration == int(10 * 1.1 ** 10 * 16)
    assert table.get(17).scaled(30).duration == (10 << 4) + (30 << 4) // 10      # area duration


def test_damage_taken():
    assert S.damage_taken(10, 0) == 10
    assert S.damage_taken(10, 30) == int(10 * 70 / 100.0 + 0.75)      # 7.75 -> 7
    assert S.damage_taken(1, 100) == 0 and S.damage_taken(10, 130) == 0
    assert S.damage_taken(7, 50) == 4                                 # 3.5 + 0.75 -> 4


def test_to_dict_is_json(table):
    d = table.to_dict()
    json.dumps(d)
    assert d["empty_records"] == 27 and d["spells"][0]["fields"]["speed"] == 200
    assert d["spells"][0]["handler"] == "damage"


def test_spell_name_table_matches_python_keys(table):
    for d in table:
        assert d.key == d.name.lower().replace(" ", "_")


# --- install ----------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def spells():
    return S.load(GFS)


@pytest.fixture(scope="module")
def db():
    from allods2.databin import databin
    return databin(GFS)


@needs_databin
class TestInstall:
    def test_every_record_parses(self, spells, db):
        assert len(db.spells) == 34 and len(spells) == 29 and spells.extra_records == 5
        assert [d.number for d in spells] == list(range(1, 30))
        for d in spells:
            assert len(d.raw) == 22 and d.key == SPELL_NAMES[d.number], d.name
            assert 1 <= d.sphere <= 5 and d.target in (1, 2) and d.delivery in (1, 2)
            assert d.missile == (d.speed > 0 and d.delivery == 2)
            assert d.item == 0 and d.skill_offset == 0                     # never read by the exe (spec §2)

    def test_names_texts(self, spells):
        assert spells.get(16).display_name == "Stone Missile" and spells.get(22).display_name == "Animate Dead"
        assert spells.get(1).description.startswith("Inflicts Fire")
        assert all(d.display_name for d in spells)
        assert {d.name for d in spells if not d.description} == {
            "Acid Stream", "Darkness", "Light", "Curse", "Slow"}

    def test_sphere_groups(self, spells):
        assert [len(spells.of_sphere(s)) for s in range(1, 6)] == [4, 5, 6, 4, 10]
        assert all(d.sphere == 1 for d in list(spells)[:4])

    def test_missiles_and_damage(self, spells):
        missiles = {d.number for d in spells if d.missile}
        assert missiles == {1, 2, 5, 10, 11, 16}
        assert all(spells.get(n).handler == "damage" for n in missiles)
        assert {d.number for d in spells if d.handler == "damage"} == {1, 2, 3, 5, 7, 9, 10, 11, 16}
        assert [d.number for d in spells if d.defensive == 1] == [4, 8, 12, 13, 15, 19, 20, 21, 23, 24, 27]

    def test_mana_and_scaling_examples(self, spells):
        fa = spells.get(1)
        assert (fa.mana_cost, fa.damage_min, fa.damage_max, fa.max_range, fa.speed) == (3, 5, 10, 7, 200)
        s = fa.scaled(30)
        assert (s.damage_min, s.damage_spread, s.max_range) == (10, 10, 8)

    def test_modifier_texts_parse(self, spells, db):
        for d in spells:
            if d.modifier_text:
                assert d.modifiers or d.name == "Invisibility", d.name
        assert [m.kind for m in spells.get(18).modifiers] == [db.stat_index("absorbtion"), db.stat_index("defence")]

    def test_projectile_animations_exist(self, spells):
        from allods2.anim import projectiles as P
        recs = P.load_projectile_records(GFS)
        for d in spells:
            if d.missile:
                assert d.effect_id in recs, d.name
        for d in spells:
            for eid in (d.effect_id, d.hit_effect_id):
                if eid in recs:
                    assert P.load_projectile_set(eid, GFS, recs).rec["ID"] == eid
        none = [d.number for d in spells if d.effect_id not in recs and d.hit_effect_id not in recs]
        assert none == [12, 14, 15, 18, 21, 22, 25, 29]               # no sprite effect: invisibility .. slow

    def test_sound_files_exist(self, spells):
        from allods2.reg import load_reg
        reg = load_reg("sfx/sfx.reg", GFS)
        have = {int(e.name[3:]): reg.blob[e.a:e.a + e.b].split(b"\0")[0].decode()
                for e in reg.entries if re.fullmatch(r"Sfx\d+", e.name)}
        missing = []
        for d in spells:
            cast, hit = d.sound_ids
            if cast not in have:
                missing.append(d.number)
            else:
                assert GFS.isfile("sfx/" + have[cast].replace("\\", "/") + ".wav"), d.name
        assert missing == [3, 7]                                       # 514, 522: no table entry (spec §7)

    def test_items_reference_spells(self, spells, db):
        n = 0
        for group in ("items", "weapons", "shields", "armour"):
            for rec in getattr(db, group):
                for text in [e for e in rec.extra if isinstance(e, str)]:
                    for m in re.finditer(r"(?:cast|teach)Spell=([A-Za-z_]+)", text, re.I):
                        assert spells.lookup(m.group(1)), (rec.name, text)
                        n += 1
        assert n >= 50

    def test_unit_spell_slots_and_known_masks(self, spells):
        from allods2.formats import unitstats
        t = unitstats.load(GFS)
        slots = known = equip = 0
        for u in t:
            f = u.fields
            for k in (1, 2, 3):
                v = f.get("spell_%d" % k, -1)
                if v > 0:
                    assert spells.get(v), (u.name, v)
                    slots += 1
            mask = f.get("known_spells", -1)
            if mask > 0:
                assert mask & 1 == 0 and mask < 1 << 30                     # bits 1..29
                for b in range(1, 31):
                    if mask >> b & 1:
                        assert spells.get(b), (u.name, b)
                known += 1
            for e in u.equipment:
                for m in re.finditer(r"castSpell=([A-Za-z_]+):(\d+)", e):
                    assert spells.lookup(m.group(1)), (u.name, e)
                    equip += 1
        assert slots >= 20 and known >= 60 and equip >= 100

    def test_golden_hash(self):
        with open(os.path.join(ROOT, "tests", "golden.json")) as f:
            want = json.load(f)["spells"]["sha256"]
        spec = importlib.util.spec_from_file_location("update_golden", os.path.join(ROOT, "tools", "update_golden.py"))
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        assert tool.spells_hash(GFS)["sha256"] == want, "spells changed; if intended run tools/update_golden.py"
