"""Cross-references between the game-data tables and the campaign maps (docs/data/overview.md).
Every table loads, every reference resolves; failures list the offenders.  Skipped without the
install.  A reference that legitimately does not resolve is listed in an EXCLUDED_* table with its
reason (and in overview.md); anything else is a real bug."""

import pytest

from allods2.anim import projectiles
from allods2.assets import AssetCache
from allods2.common import campaign_maps
from allods2.formats import Map
from allods2.formats import entities as E
from allods2.formats.itemdefs import icon_path
from allods2.formats.unitstats import MONSTER

from helpers import GFS, needs

pytestmark = needs("world", "data", "data.bin")

# Unit types (kind, name) whose own `unit_type` has no units.reg set.  Checked for monsters only:
# a human's `unit_type` is overwritten by the by-name ctor (0x21..0x24 + gender, units.md), the
# sprite of a map human comes from the map record's `type` (checked per map below).
EXCLUDED_UNIT_SETS = {
    ("monster", "Root"): "unit_type 78 is not in units.reg; placed on no campaign map",
    ("monster", "Human"): "template with serverID -1 / unit_type -1 (editor placeholder); placed on no map",
}
# Item definitions that no item code names (itemname.bin has none): monster weapons that only exist
# through the monsters' equipment strings (Sonic Beam: bats, succubi; Flame Thrower: dragons; Boulder
# Thrower: catapults), the default BareHands, the placeholder record "rem" and the never-equipped Plasma Sword.
EXCLUDED_UNNAMED_ITEMS = {("weapon", i) for i in (1, 23, 24, 25, 26, 27)}
# Every named item has an icon.  Paper-doll layers exist for the
# equipment classes only; special items (class 14: potions, scrolls, books, quest items) are never
# drawn on the doll.
NO_PAPERDOLL_CLASSES = {14}
# Spells without a sprite effect record in projectiles.reg (spells.md section 7: they draw through
# unit effects or have no visual); every missile spell must have one.
SPELLS_WITHOUT_EFFECT_RECORD = {12, 14, 15, 18, 21, 22, 25, 29}
BODIES = ("mfighter", "mmage", "ffighter", "fmage")


@pytest.fixture(scope="module")
def assets():
    return AssetCache(GFS)


@pytest.fixture(scope="module")
def maps():
    return [(p, Map.load(p, GFS)) for p in campaign_maps(GFS)]


def fail(title, offenders):
    assert not offenders, "%s (%d):\n  %s" % (title, len(offenders), "\n  ".join(map(str, offenders[:40])))


# --- every table loads ---------------------------------------------------------------------------

def test_tables_load(assets):
    assert len(assets.databin().monsters) and len(assets.databin().humans)
    assert len(assets.unit_stats()) == 464
    assert len(assets.items()) == 162 and len(assets.items().names) == 491
    assert len(assets.spells()) == 29
    p = assets.progression()
    assert p.threshold(100) == 13780 and len(p.hero_templates) == 6


# --- unit type -> units.reg ----------------------------------------------------------------------

def test_unit_types_have_sprite_sets(assets):
    bad = [(t.kind, t.name, t.server_id, t.unit_type) for t in assets.unit_stats()
           if t.kind == MONSTER and (t.kind, t.name) not in EXCLUDED_UNIT_SETS
           and assets.unit_set(t.unit_type) is None]
    fail("monster types without a units.reg sprite set", bad)


def test_excluded_unit_sets_are_still_excluded(assets):
    still = {(t.kind, t.name) for t in assets.unit_stats()
             if t.kind == MONSTER and assets.unit_set(t.unit_type) is None}
    assert still == set(EXCLUDED_UNIT_SETS)


# --- item -> sprite ------------------------------------------------------------------------------

def test_items_have_icons_and_paperdoll_layers(assets):
    """Every named item code has its inventory icon; every equipment class (weapon, shield, armour)
    has a paper-doll layer file under at least one body type."""
    items = assets.items()
    no_icon, no_layer = [], []
    for code in items.names:
        path = icon_path(code)
        if not GFS.exists(path):
            no_icon.append((hex(code), path))
        ic = E.decode_item(code)
        if ic.cls in NO_PAPERDOLL_CLASSES:
            continue
        stem = path.rsplit("/", 1)[1][:-4] + ".256"
        if not any(GFS.exists("graphics/equipment/%s/%s/%s" % (b, d, stem))
                   for b in BODIES for d in ("primary", "secondary")):
            no_layer.append((hex(code), stem))
    fail("item codes without an inventory icon", no_icon)
    fail("equipment codes without a paper-doll layer", no_layer)


def test_every_item_definition_is_named(assets):
    items = assets.items()
    named = {(ic.kind, ic.index) for ic in map(E.decode_item, items.names) if ic}
    unnamed = {(d.kind, d.index): d.name for d in items if (d.kind, d.index) not in named}
    fail("item definitions with no named item code and not excluded",
         [(k, n) for k, n in unnamed.items() if k not in EXCLUDED_UNNAMED_ITEMS])
    fail("excluded item definitions that are now named", [k for k in EXCLUDED_UNNAMED_ITEMS if k not in unnamed])


# --- spell -> effect record ----------------------------------------------------------------------

def test_spells_have_effect_records(assets):
    recs = projectiles.load_projectile_records(GFS)
    bad, excluded_present = [], []
    for s in assets.spells():
        has = s.effect_id in recs
        if s.number in SPELLS_WITHOUT_EFFECT_RECORD:
            if has:
                excluded_present.append((s.number, s.name))
        elif s.missile and not has:
            bad.append((s.number, s.name, s.effect_id))
    fail("missile spells without a projectiles.reg record", bad)
    fail("excluded spells that now have a record (shrink the exclusion list)", excluded_present)


# --- campaign maps ---------------------------------------------------------------------------------

def test_map_units_resolve(assets, maps):
    stats = assets.unit_stats()
    no_stats, no_set = [], []
    for path, m in maps:
        for u in m.units:
            if stats.lookup(u.is_human, u.server_id) is None:
                no_stats.append((path, u.uid, u.is_human, u.server_id))
            if assets.unit_set(u.type) is None:
                no_set.append((path, u.uid, u.type))
    fail("map units without a data.bin record", no_stats)
    fail("map units without a units.reg set", no_set)


def test_map_item_groups_resolve(assets, maps):
    items = assets.items()
    n_stats, bad = len(items.stats), []
    for path, m in maps:
        records = m.item_records
        for gi, g in enumerate(m.item_groups, 1):
            for mem in g.members:
                ic = E.decode_item(mem.code)
                if ic is None:                                    # class 0 / 15: the game builds no item
                    continue
                d = items.lookup(ic)
                if d is None:
                    bad.append((path, gi, hex(mem.code & 0xFFFF), "no item definition"))
                elif not GFS.exists(icon_path(mem.code)):
                    bad.append((path, gi, hex(mem.code & 0xFFFF), "no icon"))
                if mem.record:
                    if mem.record > len(records):
                        bad.append((path, gi, mem.record, "record out of range"))
                        continue
                    r = records[mem.record - 1]
                    for sid, _ in r.props:                        # claimed record: pairs = stat indices
                        if not 0 < sid < n_stats or not items.stats[sid].id:
                            bad.append((path, gi, mem.record, "stat id %d" % sid))
    fail("map item groups / properties that do not resolve", bad)


def test_map_spell_ids_resolve(assets, maps):
    """Spell ids carried by claimed item records (castSpell/teachSpell) and by building casters, and the
    spells of the unit types placed on the maps (slots and known_spells masks)."""
    n_spells = len(assets.spells())
    stats = assets.unit_stats()
    bad = []
    for path, m in maps:
        claimed = {mem.record for g in m.item_groups for mem in g.members if mem.record}
        for i, r in enumerate(m.item_records, 1):
            spell = r.c & 0xFFFF
            if spell and (i in claimed or r.flags[0] & 4) and not 1 <= spell <= n_spells:
                bad.append((path, "record", i, spell))
        for u in m.units:
            t = stats.lookup(u.is_human, u.server_id)
            slots = [t.get("spell_%d" % k, 0) for k in (1, 2, 3)]
            slots = [s for s in slots if s > 0]   # 0 and -1 = empty slot
            mask = t.get("known_spells", 0)
            if mask and mask != -1:
                slots += [b for b in range(32) if mask >> b & 1 and not 1 <= b <= n_spells]
            bad += [(path, u.uid, t.name, s) for s in slots if not 1 <= s <= n_spells]
    fail("spell ids that do not resolve", bad)
