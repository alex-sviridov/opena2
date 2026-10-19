"""docs/formats/map.md part 6: section 7 (instants, checks, triggers), 10 (repop), 11 (inns, shops, signposts), 12 (music)."""

import struct

import pytest

from allods2.common import campaign_maps
from allods2.formats import Map
from allods2.formats import scenario as S

from helpers import GFS

MAPS = campaign_maps(GFS) if GFS else []
needs_maps = pytest.mark.skipif(not MAPS, reason="game files not present")


def record(name, t, rid, values=(), kinds=(), labels=(), flag=0):
    vals = (list(values) + [0] * 10)[:10]
    kins = (list(kinds) + [0] * 10)[:10]
    labs = b"".join(struct.pack("64s", s) for s in (list(labels) + [b"<None>"] * 10)[:10])
    return struct.pack("<64siii10i10i", name, t, rid, flag, *vals, *kins) + labs


def trigger(name, pairs=((0, 0),) * 3, instants=(0, 0, 0, 0), ops=(0, 0, 0), once=1, junk=b"\xAA" * 64):
    flat = [c for p in pairs for c in p]
    return struct.pack("<64s64s6i4i3ii", name, junk, *flat, *instants, *ops, once)


def section7(instants=(), checks=(), triggers=()):
    out = b""
    for lst in (instants, checks, triggers):
        out += struct.pack("<I", len(lst)) + b"".join(lst)
    return out


# --- synthetic: one test per rule ---------------------------------------------

def test_record_layout():
    r = S.parse_record(record(b"Send message 1", 2, 7, [1], [S.K_INT], [b"Message number"], flag=1))
    assert (r.name, r.type, r.id, r.flag) == ("Send message 1", 2, 7, 1)
    assert r.values[0] == 1 and r.kinds[0] == S.K_INT and r.labels[:2] == ("Message number", "<None>")
    assert r.args() == [(S.K_INT, 1)]
    assert len(record(b"x", 1, 1)) == S.RECORD_SIZE


def test_trigger_layout():
    t = S.parse_trigger(trigger(b"Start", ((2, 3), (4, 5), (0, 0)), (1, 9, 0, 0), (5, 1, 0), once=0))
    assert (t.name, t.pairs, t.instants, t.ops, t.once) == ("Start", ((2, 3), (4, 5), (0, 0)), (1, 9, 0, 0), (5, 1, 0), 0)
    assert t.reserved == b"\xAA" * 64 and t.active
    assert not S.parse_trigger(trigger(b"off", ((0, 3), (0, 0), (0, 0)))).active
    assert len(trigger(b"x")) == S.TRIGGER_SIZE


def test_section7_three_counted_lists():
    sc = S.parse_scenario(section7([record(b"i", 4, 1)], [record(b"c", 0x10002, 1, [3]), record(b"d", 5, 2)],
                                   [trigger(b"t", ((1, 2), (0, 0), (0, 0)), (1, 0, 0, 0))]))
    assert [r.id for r in sc.instants] == [1] and [r.type for r in sc.checks] == [0x10002, 5]
    assert sc.triggers[0].instants[0] == 1


def test_section7_must_tile():
    raw = section7([record(b"i", 4, 1)])
    with pytest.raises(ValueError):
        S.parse_scenario(raw + b"\0")
    with pytest.raises(ValueError):
        S.parse_scenario(raw[:-1])
    with pytest.raises(ValueError):
        S.parse_scenario(b"\0" * 6)


def test_repop_record():
    r, = S.parse_repops(struct.pack("<iiIi", 4, 120, 5, 3), 1)
    assert (r.squad, r.delay, r.flags, r.instant) == (4, 120, 5, 3)
    with pytest.raises(ValueError):
        S.parse_repops(b"\0" * 15, 1)


def test_section11_lists():
    inn = struct.pack("<iIi", 7, 0x12, 40)
    shop = struct.pack("<21i", 9, *range(20))
    ptr = struct.pack("<iii", 42, 1, 25)
    inns, shops, ptrs = S.parse_section11(inn + shop + ptr, (1, 1, 1))
    assert inns[0] == S.Inn(7, 0x12, 40)
    assert (shops[0].uid, shops[0].a, shops[0].e) == (9, (0, 1, 2, 3), (16, 17, 18, 19))
    assert ptrs[0] == S.Pointer(42, 1, 25)
    with pytest.raises(ValueError):
        S.parse_section11(inn, (0, 1, 0))


def test_music_default_then_zones():
    raw = struct.pack("<7i", 0, 0, 0, 0, 1, 8, -1) + struct.pack("<7i", 14, 41, 6, 1, -1, -1, -1)
    d, zs = S.parse_music(raw, 1)
    assert d.is_default and d.themes == (0, 1, 8, -1)
    assert (zs[0].x, zs[0].y, zs[0].radius, zs[0].themes) == (14, 41, 6, (1, -1, -1, -1)) and not zs[0].is_default


def test_runtime_instant_index_skips_drop_locations():
    recs = [S.parse_record(record(b"", t, i + 1)) for i, t in enumerate((0x10002, 2, 0x10002, 4, 2))]
    assert [S.runtime_instant_index(recs, n) for n in range(5)] == [0, 0, 1, 1, 2]


# --- install ------------------------------------------------------------------

@needs_maps
def test_every_campaign_map_consumes_sections_7_10_11_12():
    totals = [0] * 6
    for path in MAPS:
        m = Map.load(path, GFS)
        sc = m.scenario
        assert len(sc.instants) + len(sc.checks) + len(sc.triggers) == m.header.n_sec7
        inns, shops, ptrs = m.section11
        default, zones = m.music
        assert default.is_default and len(zones) == m.header.n_sec12
        for i, x in enumerate((sc.instants, sc.checks, sc.triggers, m.repops, ptrs, zones)):
            totals[i] += len(x)
        assert not inns and not shops
    assert totals == [1334, 986, 715, 0, 40, 470]


@needs_maps
def test_install_kinds_and_ids():
    for path in MAPS:
        sc = Map.load(path, GFS).scenario
        for recs in (sc.instants, sc.checks):
            ids = [r.id for r in recs]
            assert len(set(ids)) == len(ids)
            assert all(0 <= k <= 9 for r in recs for k in r.kinds)
            # no shipped script uses a variable reference (8000..9999 with an object kind)
            assert not any(S.VAR_LOW <= v <= S.VAR_HIGH and k in S.OBJECT_KINDS for r in recs for k, v in r.args())
