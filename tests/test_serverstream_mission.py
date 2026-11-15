"""L10e-A: the typed mission branch of the server stream (loaded flag 1) and the field layouts of its raw blocks
(`allods2/formats/serverstream.py`, `serverblocks.py`; docs/formats/saves.md 6.8-6.12).  Synthetic, one test per rule; always runs."""

import struct

import pytest

from allods2.formats import serverblocks as B
from allods2.formats import serverstream as SS
from allods2.formats.mfc import ArchiveError, MfcReader, MfcWriter
from test_savegame_town import eff, hero, item, synthetic


# --- layouts --------------------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("layout", [B.POSITION, B.MOVER, B.BRAIN, B.BLK_A6, B.BLK_114, B.BLK_BE, B.BLK_D4, B.GROUP_AI, B.CELL_RECORD, B.EFFECT6])
def test_layouts_do_not_overlap_and_fit(layout):
    assert layout.overlaps() == []
    assert all(f.off + f.size <= layout.size for f in layout.fields.values())
    assert all(f.tag in "CI" for f in layout.fields.values())


def test_block_sizes_are_the_serialiser_sizes():
    # FUN_005595a8 / FUN_00574452 / FUN_00515bea / FUN_005157ee / FUN_005114bc / FUN_00574560 / FUN_0054ffd1
    assert (B.MOVER.size, B.BRAIN.size, B.BLK_A6.size, B.BLK_BE.size, B.BLK_D4.size, B.GROUP_AI.size, B.POSITION.size) == (0xB4, 0xB8, 0x18, 0x16, 0x40, 0x50, 12)
    assert B.CELL_RECORD.size == 0x3C


def test_set_changes_only_the_named_field_and_keeps_unknown_bytes():
    raw = bytes(range(0xB4))
    out = B.MOVER.set(raw, facing=0x30, dx=-3)
    assert out[0] == 0x30 and out[0xB0] == 0xFD and B.MOVER.get(out, "dx") == -3
    assert out[1:0xB0] == raw[1:0xB0] and out[0xB1:] == raw[0xB1:]
    assert B.MOVER.get(B.MOVER.set(raw, step_len=0x1FFFF), "step_len") == 0xFFFF          # unsigned fields wrap
    with pytest.raises(ValueError):
        B.MOVER.get(raw[:-1], "facing")


def test_position_is_the_first_twelve_bytes_of_every_object():
    raw = B.position_raw(10, 20, 0x40, 0xC0, 0x670E48)
    assert len(raw) == 12 and raw[0] == 10 and raw[1] == 20
    assert B.POSITION.get(raw, "packed") == (20 << 8) + 10                                   # FUN_0054ff9e
    b = SS.Base(raw12=raw)
    assert b.pos == {"cell_x": 10, "cell_y": 20, "packed": 20 * 256 + 10, "sub_x": 0x40, "sub_y": 0xC0, "world": 0x670E48}
    b.with_pos(sub_x=0x80)
    assert b.pos["sub_x"] == 0x80 and b.raw12[6:8] == bytes(2)
    w = MfcWriter()
    b.write(w)
    assert w.getvalue()[:12] == b.raw12                                                        # written first (FUN_0052cf8d)


# --- the object families --------------------------------------------------------------------------------------------------------------

def body_round_trip(cls, obj, klass, load):
    w = MfcWriter()
    w.object(obj, klass, obj.write_body)
    raw = w.getvalue()
    r = MfcReader(raw)
    back = r.object(SS.CLASSES, klass.name)
    assert r.pos == len(raw) and back == obj
    w2 = MfcWriter()
    w2.object(back, klass, back.write_body)
    assert w2.getvalue() == raw
    return back


def test_building_codec_FUN_0052029c():
    b = SS.BuildingObj(SS.Base(B.position_raw(5, 6), 0x6001, 12, 3, 2, 0, 9, 0x4000, 0x500), bytes(range(0x16)), 7, 0x101, 0x102, 0x103, 4, 5, 6, 0xAABBCCDD, 0x11223344)
    back = body_round_trip(SS.BuildingObj, b, SS.C_BUILDING, None)
    assert back.base.pos["cell_x"] == 5 and back.w46 == 0x103 and back.d68 == 0x11223344


def test_spell_effect_codec_FUN_0051c6b5():
    e = SS.SpellEffectObj(SS.Base(B.position_raw(1, 2), 0x30, 6, 0, 0, 0, 0, 0x4100, 0x500), 3, 4)
    assert body_round_trip(SS.SpellEffectObj, e, SS.C_SPELLEFFECT, None).b41 == 4


def test_virtual_caster_codec_FUN_0052db3e():
    c = SS.VirtualCasterObj(SS.Base(B.position_raw(1, 2), 0, 0, 0, 0, 0, 0, 0x4200, 0x500), 9, B.EFFECT6.encode(spell=0x17, dest_x=30, dest_y=40))
    back = body_round_trip(SS.VirtualCasterObj, c, SS.C_CASTER, None)
    assert B.EFFECT6.decode(back.sub) == {"spell": 0x17, "dest_x": 30, "dest_y": 40}
    assert len(back.sub) == 6


def test_sack_codec_and_item_lists_FUN_0052d8de():
    sack = SS.SackObj(SS.Base(B.position_raw(8, 9), 0, 0, 0, 0, 0, 0, 0x4300, 0), 5,
                      SS.Pack([item(0x104, 0x7000, [eff(41, 0x1405, 0x7001)]), item(0xE05, 0x7020, count=3)], 0x7FFF, 0))
    back = body_round_trip(SS.SackObj, sack, SS.C_SACK, None)
    assert [i.code for i in back.pack.items] == [0x104, 0xE05] and back.pack.items[0].effects[0].kind == 41 and back.pack.items[1].count == 3


# --- units: the container, back-references, embedded lists, raw blocks ----------------------------------------------------------------------

def test_unit_container_back_references_and_orphans():
    s = synthetic()
    orphan = hero(9, 0x9000, 0x500, humanoid=False)
    s.container.append(orphan)                                  # a unit that is in no group: written in full inside the container
    raw = s.pack()
    t = SS.ServerStream.parse(raw)
    assert t == s and t.pack() == raw
    assert t.container[0] is t.players[0].groups[0].units[0]
    assert t.container[3] is not None and t.container[3] not in t.units
    assert t.container[3].number == 9


def test_embedded_lists_1c8_1e4_and_brain_list_use_the_mfc_count():
    u = hero(1, 0x1000, 0x500)
    u.list1c8 = [0x0102, 0x0304]
    w = MfcWriter()
    SS.write_cells(w, u.list1c8)
    assert w.getvalue() == struct.pack("<HHH", 2, 0x0102, 0x0304)
    big = [i & 0xFFFF for i in range(0xFFFF + 2)]
    w = MfcWriter()
    SS.write_cells(w, big)
    raw = w.getvalue()
    assert raw[:6] == struct.pack("<HI", 0xFFFF, 0xFFFF + 2)                                   # 0xffff + u32 form
    assert SS.read_cells(MfcReader(raw)) == big


def test_unit_lists_round_trip_in_a_stream():
    s = synthetic()
    h = s.players[0].groups[0].units[0]
    h.list1c8, h.list1e4, h.brain_list = [0x0102, 0x0304, 0x0506], [0x0A0B], [0x0C0D, 0x0E0F]
    raw = s.pack()
    t = SS.ServerStream.parse(raw)
    u = t.players[0].groups[0].units[0]
    assert (u.list1c8, u.list1e4, u.brain_list) == ([0x0102, 0x0304, 0x0506], [0x0A0B], [0x0C0D, 0x0E0F]) and t.pack() == raw


def test_raw_unit_blocks_have_fixed_sizes():
    for name, n in (("blk_a6", 0x18), ("blk_be", 0x16), ("blk_114", 0x18), ("blk_d4", 0x40), ("mover", 0xB4), ("brain", 0xB8)):
        u = hero(1, 0x1000, 0x500)
        setattr(u, name, bytes(n - 1))
        w = MfcWriter()
        with pytest.raises(ValueError):
            u.write_body(w)


def test_unit_mover_brain_and_stat_views_keep_the_rest_of_the_block():
    u = hero(1, 0x1000, 0x500)
    before_m, before_b = u.mover, u.brain
    u.base.with_pos(cell_x=40, cell_y=50, packed=50 * 256 + 40, sub_x=0x90, sub_y=0x70)
    u.mover_set(facing=0xC0, target_facing=0xC0, step_target=(51 << 8) | 40, steps=3, step_ticks=8)
    u.brain_set(mode=5, order=1, range=2, withdraw=12, target_ptr=0x2000)
    u.blk_a6 = B.BLK_A6.set(u.blk_a6, skill0=30, skill3=55)
    assert u.mover_get("facing") == 0xC0 and u.brain_get("mode") == 5 and u.brain_get("target_ptr") == 0x2000
    assert u.mover[0x20:0x70] == before_m[0x20:0x70] and u.brain[0x20:0x28] == before_b[0x20:0x28]     # untouched bytes stay
    t = SS.ServerStream.parse(self_stream_with(u))
    v = t.players[0].groups[0].units[0]
    assert v.mover == u.mover and v.brain == u.brain and v.base.pos["cell_x"] == 40
    assert (B.BLK_A6.get(v.blk_a6, "skill0"), B.BLK_A6.get(v.blk_a6, "skill3")) == (30, 55)


def self_stream_with(u):
    s = synthetic()
    s.players[0].groups[0].units[0] = u
    s.container[0] = u
    return s.pack()


def test_hp_mana_words_are_in_store_order():
    u = hero(1, 0x1000, 0x500)
    u.words = (30, 30, 30, 30, 16, 0, 0, 0, 111, 222, 3, 44, 55, 6)
    t = SS.ServerStream.parse(self_stream_with(u))
    v = t.players[0].groups[0].units[0]
    hp, hpmax, regen, mana, manamax, mregen = v.words[8:]
    assert (hp, hpmax, regen, mana, manamax, mregen) == (111, 222, 3, 44, 55, 6)


# --- groups ---------------------------------------------------------------------------------------------------------------------------------

def test_group_blocks_list20_ai_record_and_anchors():
    s = synthetic()
    g = s.players[0].groups[0]
    g.list20 = [1, 2, 3]
    g.ai = B.GROUP_AI.encode(g.ai, order=0x12, active=1, awake=1, pool_radius=20)
    g.ai_list = [0x0A0A, 0x0B0B]
    g.d1c = 7                                                                                   # squad number
    t = SS.ServerStream.parse(s.pack())
    h = t.players[0].groups[0]
    assert h.list20 == [1, 2, 3] and h.ai_list == [0x0A0A, 0x0B0B] and h.d1c == 7
    assert (B.GROUP_AI.get(h.ai, "order"), B.GROUP_AI.get(h.ai, "pool_radius"), B.GROUP_AI.get(h.ai, "awake")) == (0x12, 20, 1)
    g.ai = bytes(0x4F)
    with pytest.raises(ValueError):
        s.pack()


# --- map layer ------------------------------------------------------------------------------------------------------------------------------

def test_map_layer_sparse_cells_and_cell_record_map():
    rec = B.CELL_RECORD.encode(saved_cost=3, saved_block=1, slots_used=1, slot0=0x4100, trap_spell=0x17, trap_dest_x=60, trap_dest_y=70, index=0x2D0A)
    m = SS.MapLayer([SS.MapLayer.cell(0x0A2D, 0x20, 0x07), SS.MapLayer.cell(0x0A2E, 0x11, 0)], [(0x2D0A, rec), (0x0101, bytes(60))], 0x7777)
    w = MfcWriter()
    m.write(w)
    raw = w.getvalue()
    assert raw[:2] == struct.pack("<H", 2) and raw[2:6] == struct.pack("<I", 0x0A2D2007)       # MFC count, then (index << 16) | plane2 << 8 | plane1
    assert raw[10:12] == struct.pack("<H", 2) and raw[12:14] == struct.pack("<H", 0x2D0A)       # CMap: count, u16 key, 60-byte value
    assert raw[-4:] == struct.pack("<I", 0x7777)
    back = SS.MapLayer.read(MfcReader(raw))
    assert back == m and SS.MapLayer.split(back.cells[0]) == (0x0A2D, 0x20, 0x07)
    assert B.CELL_RECORD.decode(back.records[0][1])["trap_spell"] == 0x17
    with pytest.raises(ValueError):
        SS.MapLayer([], [(1, bytes(59))], 0).write(MfcWriter())


def test_cmap_hash_order_is_deterministic():
    keys = [0x0010, 0x0011, 0x0120, 0x0021]
    order = B.cmap_order(keys)
    assert sorted(order) == sorted(keys) and order == B.cmap_order(keys)


# --- script state ---------------------------------------------------------------------------------------------------------------------------

def test_script_state_blocks_and_counters():
    s = SS.ScriptState()
    s.variables = list(range(-5, 995))
    s.fired = bytes([1, 0] * 500)
    s.b30, s.b400 = bytes(range(0x30)), bytes(range(200)) * 2
    s.relations = B.set_relation(bytes(0x132C), 1, 2, 3)
    s.b_a48, s.b_a49, s.d_a4c, s.complete, s.d_be10, s.fail = 1, 2, 3, 4, 5, 6
    w = MfcWriter()
    s.write(w)
    raw = w.getvalue()
    assert len(raw) == 4000 + 1000 + 0x30 + 400 + 0x132C + 1 + 1 + 4 + 12
    t = SS.ScriptState.read(MfcReader(raw))
    assert t == s and t.variables[0] == -5 and t.variables[999] == 994 and t.fired_flags[:2] == (1, 0)
    assert B.relation(t.relations, 1, 2) == 3 and B.relation(t.relations, 2, 1) == 0
    assert (t.complete, t.fail) == (4, 6)
    s.values = bytes(3999)
    with pytest.raises(ValueError):
        s.write(MfcWriter())


# --- the whole mission stream ---------------------------------------------------------------------------------------------------------------

def mission():
    sack = SS.SackObj(SS.Base(B.position_raw(8, 9), 0, 0, 0, 0, 0, 0, 0x4300, 0), 5, SS.Pack([item(0x104, 0x7100, [eff(41, 0x1405, 0x7101)])], 0x7FFF, 0))
    return SS.Mission(
        buildings=[SS.BuildingObj(SS.Base(B.position_raw(5, 6), 0x6001, 12, 3, 2, 0, 9, 0x4000, 0x500), bytes(range(0x16)), 7, 1, 2, 3, 4, 5, 6, 7, 8),
                   SS.BuildingObj(SS.Base(B.position_raw(15, 16), 0x6002, 12, 3, 2, 0, 9, 0x4001, 0x500))],
        effects=[SS.SpellEffectObj(SS.Base(B.position_raw(1, 2), 0x30, 6, 0, 0, 0, 0, 0x4100, 0x500), 3, 4)],
        map=SS.MapLayer([SS.MapLayer.cell(0x0A2D, 0x20, 7)], [(0x2D0A, B.CELL_RECORD.encode(trap_spell=0x17, index=0x2D0A))], 0x7777),
        script=SS.ScriptState(complete=1, fail=0),
        sacks=[sack],
        casters=[SS.VirtualCasterObj(SS.Base(B.position_raw(3, 4), 0, 0, 0, 0, 0, 0, 0x4200, 0x500), 9, B.EFFECT6.encode(spell=0x17, dest_x=3, dest_y=4))])


def test_full_synthetic_mission_stream_round_trip():
    s = synthetic()
    s.loaded, s.mission = 1, mission()
    raw = s.pack()
    assert len(raw) % 2 == 0
    t = SS.ServerStream.parse(raw)
    assert t.mission is not None and t.mission_raw == b"" and t == s and t.pack() == raw
    assert len(t.mission.buildings) == 2 and t.mission.sacks[0].pack.items[0].code == 0x104
    assert t.mission.script.complete == 1 and t.mission.map.records[0][0] == 0x2D0A
    assert t.tail_words == (SS.BADFACE, SS.BADFACE) and len(t.debug) == SS.DEBUG_SIZE
    # the units of the groups are still shared with the container
    assert t.container[0] is t.players[0].groups[0].units[0]


@pytest.mark.parametrize("name", ["ab", "abc"])
def test_mission_stream_both_parities_keep_the_pad(name):
    s = synthetic()
    s.map_name, s.loaded, s.mission = name, 1, mission()
    raw = s.pack()
    t = SS.ServerStream.parse(raw)
    assert t.pack() == raw and t.mission == s.mission


def test_mission_classes_share_one_mfc_counter_with_units():
    s = synthetic()
    s.loaded, s.mission = 1, mission()
    raw = s.pack()
    # one class record per class name; Building appears once for two objects (second takes 0x8000 | class index)
    assert raw.count(b"Building") == 1 and raw.count(b"SpellEffect") == 1 and raw.count(b"VirtualCaster") == 1 and raw.count(b"Sack") == 1


def test_mission_branch_that_is_not_the_layout_stays_raw():
    s = synthetic()
    s.loaded, s.mission_raw = 1, b"\x01\x02\x03"
    raw = s.pack()
    t = SS.ServerStream.parse(raw)
    assert t.mission is None and t.mission_raw == b"\x01\x02\x03" and t.pack() == raw


def test_mission_tail_words_are_not_checked_but_a_truncated_stream_is_refused():
    s = synthetic()
    s.loaded, s.mission = 1, mission()
    raw = s.pack()
    zeroed = raw.replace(struct.pack("<II", SS.BADFACE, SS.BADFACE), b"\0" * 8)          # the loader reads and ignores the pair
    t = SS.ServerStream.parse(zeroed)
    assert t.tail_words == (0, 0) and t.mission == s.mission
    with pytest.raises(ArchiveError):
        SS.ServerStream.parse(raw[:-20])


def test_mission_and_town_flags_are_exclusive():
    s = synthetic()
    s.mission = mission()
    with pytest.raises(ValueError):
        s.pack()


def test_empty_mission_branch_is_typed():
    s = synthetic()
    s.loaded, s.mission = 1, SS.Mission()
    raw = s.pack()
    t = SS.ServerStream.parse(raw)
    assert t.mission == SS.Mission() and t.pack() == raw


def test_unit_field_mapping_names_engine_fields():
    names = dict(B.UNIT_MAP)
    assert "Unit.hp" in names["words[8..13] (+0x94..)"] and "Unit.facing" == names["mover.facing"]


# --- the derived carrier classes (saves.md 6.12: PointEffect / AreaEffect / SpellTransport) ---------------------------------------------------

def test_derived_carrier_classes_round_trip_with_their_own_tails():
    s = synthetic()
    s.loaded, s.mission = 1, mission()
    unit = s.container[0]
    base = lambda k: SS.Base(B.position_raw(k, k), 0x30 + k, 6, 0, 0, 0, 0, 0x4100 + k, 0x500)
    s.mission.effects = [
        SS.SpellEffectObj(base(1), 0, 1, "PointEffect", {"o4c": unit, "p48": 0x4321}),
        SS.SpellEffectObj(base(2), 0, 1, "AreaEffect", {"b4c": 1, "b4d": 2, "b4e": 3, "b4f": 4, "h50": 99, "o48": unit}),
        SS.SpellEffectObj(base(3), 0, 1, "SpellTransport", {"o48": unit, "o4c": None, "h50": 7}),
        SS.SpellEffectObj(base(4), 1, 1),
    ]
    raw = s.pack()
    t = SS.ServerStream.parse(raw)
    assert t.mission_raw == b"" and t.pack() == raw
    kinds = [(e.kind, e.tail) for e in t.mission.effects]
    assert [k for k, _ in kinds] == ["PointEffect", "AreaEffect", "SpellTransport", "SpellEffect"]
    assert kinds[0][1]["o4c"] is t.container[0] and kinds[0][1]["p48"] == 0x4321
    assert kinds[1][1] == {"b4c": 1, "b4d": 2, "b4e": 3, "b4f": 4, "h50": 99, "o48": t.container[0]}
    assert kinds[2][1]["o4c"] is None and kinds[2][1]["h50"] == 7


def test_unit_block_layouts_name_the_armour_and_bonus_fields():
    be = B.BLK_BE.encode(defence=-5, absorb=3, prot2=7, res5=40)
    assert B.BLK_BE.get(be, "defence") == -5 and be[0x04 + 4] == 7 and be[0x15] == 40
    d4 = B.BLK_D4.encode(speed_bonus=-2, hp_max_bonus=10, skill_bonus5=9, scan_bonus=0x300)
    assert B.BLK_D4.get(d4, "speed_bonus") == -2 and struct.unpack_from("<h", d4, 0x08)[0] == 10 and struct.unpack_from("<h", d4, 0x1E)[0] == 9 and struct.unpack_from("<h", d4, 0x10)[0] == 0x300
