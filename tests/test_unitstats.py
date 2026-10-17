"""Tests for docs/data/units.md (allods2.formats.unitstats)."""

import hashlib
import json

import pytest

from allods2 import databin as D
from allods2.common import campaign_maps
from allods2.formats import Map
from allods2.formats import unitstats as U

from helpers import GFS, needs
from test_databin import base, cstr, group, sample

needs_databin = needs("world", "data", "data.bin")

# Documented exclusions: map unit (is_human, serverID) pairs without a record. None today.
EXCLUDED = set()
# Records with hp_max -1 (constructor default); no map uses them: human ManMage_Unarmed.
NO_HP = {("human", 23)}


def test_field_names():
    assert U.field_name("healthMax") == "hp_max" and U.field_name("HP regeneraton") == "hp_regen"
    assert U.field_name("prot Fire") == "prot_fire" and U.field_name("res.Blade") == "res_blade"
    assert U.field_name("Skill.Blade (Fire)") == "skill_blade"
    assert U.field_name("treasure.1 Gold") == "gold_chance" and U.field_name("treasureMax.2") == "item_value_max"
    assert U.field_name("gender ( is female? )") == "gender"


def table_with(monster_params, labels):
    db = D.parse_databin(sample())
    db.headers[4] = ["name"] + labels
    db.monsters[0].params = monster_params
    db.humans = []                                   # the sample's human has no serverID column
    return U.build(db)


def test_build_names_every_param_and_keeps_raw():
    t = table_with([10, 600, 7], ["healthMax", "serverID", "typeID"])
    (m,) = t.of_kind("monster")
    assert (m.name, m.index, m.server_id, m.unit_type, m.hp_max) == ("Goblin", 1, 600, 7, 10)
    assert m.raw == (10, 600, 7) and m.equipment == ("Bronze Pike", "")
    assert t.lookup(False, 600) is m and t.lookup(True, 600) is None and t.lookup(False, 1) is None


def test_empty_records_are_skipped_and_first_id_wins():
    t = table_with([], ["healthMax", "serverID", "typeID"])
    assert t.of_kind("monster") == []
    db = D.parse_databin(sample())
    db.headers[4] = ["name", "healthMax", "serverID", "typeID"]
    db.humans = []
    db.monsters = [D.Record("A", [1, 5, 1], ("", "")), D.Record("B", [2, 5, 1], ("", ""))]
    assert U.build(db).lookup(False, 5).name == "A"


def test_attribute_errors():
    t = table_with([10, 600, 7], ["healthMax", "serverID", "typeID"])
    with pytest.raises(AttributeError):
        t.types[0].nope
    assert t.types[0].get("nope", 3) == 3


@needs_databin
class TestInstall:
    table = None

    @classmethod
    def setup_class(cls):
        cls.table = U.load(GFS)

    def test_counts_and_no_leftover_params(self):
        t = self.table
        assert len(t.of_kind("monster")) == 180 and len(t.of_kind("human")) == 284
        db = D.databin(GFS)
        for kind, recs in (("monster", db.monsters), ("human", db.humans)):
            labels = len(db.columns(U.GROUP[kind]))
            named = [r for r in recs if r.params]
            assert all(len(r.params) == labels - 1 for r in named)       # last label = equipment strings
            got = t.of_kind(kind)
            assert len(got) == len(named)
            for ut in got:
                assert len(ut.fields) + 2 == len(ut.raw)                 # + server_id, unit_type
                assert len(ut.equipment) == (2 if kind == "monster" else 10)

    def test_every_map_unit_type_has_a_record(self):
        used = set()
        for p in campaign_maps(GFS):
            used.update((u.is_human, u.server_id) for u in Map.load(p, GFS).units)
        assert len(used) == 205
        assert {k for k in used if self.table.lookup(*k) is None} <= EXCLUDED

    def test_plausible_ranges(self):
        for t in self.table:
            if t.server_id == -1:                     # monster 241 "Human": an editor placeholder, no map uses it
                continue
            # -1 = keep the constructor default (humans); one unused record has it for HP
            assert t.hp_max > 0 or (t.kind, t.server_id) in NO_HP, t.name
            assert 0 < t.speed <= 100 and 0 < t.turn_rate <= 100, t.name
            assert -1 <= t.mana_max <= 30000 and 1 <= t.scan_range <= 20, t.name
            assert t.movement_type in (-1, 1, 2, 3) and -1 <= t.windup < 100, t.name
            assert t.unit_type > 0 and t.server_id > 0
            if t.kind == U.MONSTER:
                assert 0 < t.damage_min <= 2000 and 0 < t.damage_max <= 2000, t.name   # min > max occurs in the data
                assert 0 < t.windup and 0 < t.recovery < 100 and 0 <= t.defence <= 500, t.name

    def test_known_examples(self):
        g = self.table.lookup(False, 600)                                # docs/formats/databin.md
        assert (g.name, g.unit_type, g.speed, g.turn_rate, g.windup, g.recovery) == ("Goblin_Pike", 64, 24, 16, 7, 3)

    def test_golden_hash(self):
        with open(__file__.rsplit("/", 1)[0] + "/golden.json") as f:
            want = json.load(f)["units"]["sha256"]
        blob = json.dumps(self.table.to_dict(), indent=1, sort_keys=True).encode("utf-8")
        assert hashlib.sha256(blob).hexdigest() == want
