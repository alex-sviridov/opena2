"""Tests for docs/data/progression.md (allods2.formats.progression and the hero state of engine.world).
Synthetic tests always run; the install-backed ones skip without the game files."""

import importlib.util
import json
import os
from types import SimpleNamespace

import pytest

from allods2 import cli
from allods2.assets import AssetCache
from allods2.cli import open_map
from allods2.formats import progression as P
from allods2.formats import unitstats as U
from engine.world import Unit, World

from helpers import GFS, INSTALL, needs

needs_databin = needs("world", "data", "data.bin")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- synthetic -------------------------------------------------------------------------------


def human(name, server_id=1, equipment=("",) * 10, **f):
    fields = dict(body=10, reaction=10, mind=10, spirit=10, hp_max=20, mana_max=-1, known_spells=-1,
                  skill_general=-1, skill_blade=-1, skill_axe=-1, skill_bludgen=-1, skill_pike=-1,
                  skill_shooting=-1)
    fields.update(f)
    return U.UnitType(U.HUMAN, 1, name, server_id, 3, fields, tuple(equipment), ())


def test_derived_vitals_fighter_and_mage():
    # docs/data/progression.md section 3: no XP -> G ~ 0.0 (pools thr[0] = 1 each)
    f = human("f", body=40, spirit=17, skill_blade=20)                 # Start_MF: 116 HP
    assert P.derived_vitals(f) == (116, 0)
    m = human("m", body=14, spirit=44, mana_max=70, gender=1, skill_blade=25, skill_shooting=10)  # Mage_Hero
    assert P.derived_vitals(m) == (14, 146)


def test_derived_vitals_ignore_template_hp_and_cap_attributes():
    a = human("a", body=20, hp_max=1)
    b = human("b", body=20, hp_max=9999)
    assert P.derived_vitals(a) == P.derived_vitals(b)
    capped = human("c", body=200)                                      # fighter male cap 52
    assert P.derived_vitals(capped) == P.derived_vitals(human("c2", body=52))
    assert P.derived_vitals(human("d", body=-1)) == P.derived_vitals(human("d2", body=30))   # -1 = constructor default


def test_derived_vitals_bonus_and_xp_term():
    base = P.derived_vitals(human("x", body=30, skill_blade=0))[0]
    assert P.derived_vitals(human("x", body=30), bonus_hp=7)[0] == base + 7
    # a hero with 80 in all schools has total XP 5 * 2048 -> G = log1.1(3.05) > 11
    assert P.derived_vitals(human("y", body=30, skill_blade=80, skill_axe=80, skill_bludgen=80, skill_pike=80,
                                  skill_shooting=80))[0] > base


class FakeSpells:
    def get(self, n):
        return SimpleNamespace(name="spell%d" % n) if 1 <= n <= 29 else None


def test_curve_values():
    thr = P.Progression().thresholds
    assert len(thr) == 150
    assert thr[:10] == (1, 1, 1, 1, 1, 1, 1, 1, 2, 2)           # trunc(1.1 ** n)
    assert thr[100] == 13780 and thr[149] == 1470652
    assert all(a <= b for a, b in zip(thr, thr[1:]))


def test_threshold_clamps_at_149():
    p = P.Progression()
    assert p.threshold(149) == p.threshold(150) == p.threshold(1000) == 1470652


def test_level_of_is_the_inverse():
    p = P.Progression()
    assert p.level_of(0) == 0 and p.level_of(1) == 7        # thr[1..7] = 1, thr[8] = 2 is the first value above 1
    assert p.level_of(2) == 11                                  # thr[8..11] = 2
    for n in (20, 60, 100, 148):
        assert p.level_of(p.thresholds[n]) == n
        assert p.level_of(p.thresholds[n] - 1) < n
    assert p.level_of(10 ** 9) == 1470652                       # quirk: the table value, not 149


def test_best_school_first_on_ties_and_zero_when_empty():
    assert P.best_school((0, 5, 9, 9, 1, 0)) == 2
    assert P.best_school((0, 20, 0, 0, 0, 20)) == 1
    assert P.best_school((50, 0, 0, 0, 0, 0)) == 0               # general never counts
    assert P.best_school((0, 0, 0, 0, 0, 0)) == 0


def test_start_pools_are_the_curve_at_the_skill():
    pools, total = P.start_pools((0, 20, 0, 0, 0, 10))
    assert pools == (6, 1, 1, 1, 2) and total == 11
    assert P.start_pools((0, 100, 0, 0, 0, 0))[0][0] == 13780


def test_skills_default_to_zero():
    assert P.skills_of(human("X", skill_general=3, skill_pike=40)) == (3, 0, 0, 0, 40, 0)


def test_spell_mask_bit_n_is_spell_n():
    assert P.spells_of(-1, FakeSpells()) == []
    assert P.spells_of(0, FakeSpells()) == []
    assert P.spells_of((1 << 1) | (1 << 24) | (1 << 29), FakeSpells()) == ["spell1", "spell24", "spell29"]
    assert P.spells_of(1 << 30, FakeSpells()) == []              # only bits 1..29 are read
    assert P.spells_of(1 << 3, None) == ["spell 3"]


def test_hero_names():
    for n in ("Start_MF", "Fighter_Hero", "Mage_Hero"):
        assert P.is_hero_name(n)
    for n in ("Hero", "Starter", "Soldier", "hero_x"):
        assert not P.is_hero_name(n)


def test_build_takes_only_heroes_and_decodes_them():
    t = human("Start_MM", 7, ("Wood Staff", "") + ("",) * 8, skill_blade=20, mana_max=70, known_spells=1 << 5)
    table = U.UnitTable([t, human("Soldier", 8, skill_blade=60),
                         U.UnitType(U.MONSTER, 1, "Mage_Hero", 9, 3, {}, (), ())])
    p = P.build(table, FakeSpells())
    assert [h["name"] for h in p.hero_templates] == ["Start_MM"]
    h = p.hero(7)
    assert h["skills"] == [0, 20, 0, 0, 0, 0] and h["best_school"] == 1
    assert h["known_spells"] == ["spell5"] and h["start_pools"] == [6, 1, 1, 1, 1] and h["start_total"] == 10
    assert h["equipment"][0] == "Wood Staff" and h["attributes"]["body"] == 10
    assert p.hero(8) is None
    json.dumps(p.to_dict())


def test_unit_defaults_have_no_progression():
    u = Unit(1, 1, 1, 0, 0)
    assert u.skills == () and u.xp == () and u.xp_total == 0 and u.best_school == 0


# --- install ---------------------------------------------------------------------------------


@needs_databin
class TestInstall:
    assets = AssetCache(GFS) if GFS else None

    def test_hero_templates(self):
        p = self.assets.progression()
        assert [(h["name"], h["server_id"]) for h in p.hero_templates] == [
            ("Start_MF", 10210), ("Start_FF", 10211), ("Start_MM", 10212), ("Start_FM", 10213),
            ("Fighter_Hero", 10220), ("Mage_Hero", 10230)]
        assert self.assets.progression() is p
        mf, mm, mage = p.hero(10210), p.hero(10212), p.hero(10230)
        assert mf["skills"] == [0, 20, 0, 0, 0, 0] and mf["known_spells"] == []
        assert mf["start_pools"] == [6, 1, 1, 1, 1] and mf["best_school"] == 1
        assert mm["known_spells"] == ["Heal", "Shield"] and mm["mana_max"] == 70
        assert mage["skills"] == [0, 25, 0, 0, 0, 10] and mage["start_total"] == 15
        assert mage["known_spells"] == ["Fire Arrow", "Protection from Fire", "Bless", "Haste", "Heal", "Shield"]
        assert mm["equipment"][0] == "Wood Staff {castSpell=Fire_Arrow:1}"

    def test_every_hero_skill_is_in_range(self):
        for h in self.assets.progression().hero_templates:
            assert all(0 <= s <= P.SKILL_CAP for s in h["skills"])
            assert h["start_total"] == sum(h["start_pools"])

    def test_export_cli_and_golden(self, tmp_path):
        dest = tmp_path / "p.json"
        assert cli.main(["data", "export", "progression", str(dest), "--install", str(INSTALL)]) == 0
        d = json.load(open(dest))
        assert d["thresholds"][100] == 13780 and len(d["hero_templates"]) == 6
        spec = importlib.util.spec_from_file_location("update_golden", os.path.join(ROOT, "tools", "update_golden.py"))
        tool = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tool)
        with open(os.path.join(ROOT, "tests", "golden.json")) as f:
            want = json.load(f)["progression"]["sha256"]
        assert tool.progression_hash(GFS)["sha256"] == want, "progression changed; if intended run tools/update_golden.py"

    def test_world_hero_state_on_map_40(self):
        w = World.from_map(open_map("40", GFS), self.assets)
        heroes = [u for u in w.units.values() if u.human and u.server_id == 10230]
        assert len(heroes) == 1
        u = heroes[0]
        assert u.skills == (0, 25, 0, 0, 0, 10) and u.xp == (10, 1, 1, 1, 2) and u.xp_total == 15
        assert u.best_school == 1

    def test_world_human_and_monster_state(self):
        w = World.from_map(open_map("40", GFS), self.assets)
        thr = self.assets.progression().thresholds
        humans = [u for u in w.units.values() if u.human and u.stats is not None]
        assert humans
        for u in humans:
            assert u.xp == tuple(thr[s] for s in u.skills[1:]) and u.xp_total == sum(u.xp)
            if not P.is_hero_name(u.stats.name):
                assert u.best_school == 0
        for u in w.units.values():
            if not u.human:
                assert u.skills == () and u.xp == ()


    def test_world_humans_use_derived_vitals(self):
        # docs/data/progression.md section 6: the template healthMax of a human is never used
        w = World.from_map(open_map("10", GFS), self.assets)
        humans = [u for u in w.units.values() if u.human and u.stats is not None]
        assert humans
        for u in humans:
            hp, mana = P.derived_vitals(u.stats)
            assert (u.hp_max, u.hp) == (hp, hp) and u.mana == u.mana_max == mana

    def test_world_map_hp_only_sets_current_hp_of_a_damaged_hero(self):
        w = World.from_map(open_map("40", GFS), self.assets)
        u = [u for u in w.units.values() if u.human and u.server_id == 10230][0]
        assert (u.hp, u.hp_max) == (5, 14)              # map record: hp 5, max_hp default -> derived maximum 14
        assert u.mana_max == 146                        # derived, the map has no mana

    def test_known_exe_values(self):
        by = {t.name: t for t in self.assets.unit_stats() if t.kind == "human"}
        assert P.derived_vitals(by["Start_MF"]) == (116, 0)
        assert P.derived_vitals(by["Mage_Hero"]) == (14, 146)
        assert P.derived_vitals(by["2A_Knight4"]) == (167, 0)
        assert P.derived_vitals(by["2M_Knight4"]) == (58, 267)
