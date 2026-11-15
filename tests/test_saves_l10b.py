"""L10b synthetic tests (docs/formats/saves.md 6.1-6.3, 6.10): MFC archive layer, typed client tail, container."""

import struct

import pytest

from allods2.formats import saves as S
from allods2.formats.mfc import ArchiveError, MfcClass, MfcReader, MfcWriter
from allods2.reg import build_reg, parse_reg

# --- MFC primitives and tags ---------------------------------------------------------------------------------------------

THING = MfcClass("Thing")
OTHER = MfcClass("Other")


class Obj:
    def __init__(self, v=0, child=None):
        self.v, self.child = v, child


def body(o):
    def f(w):
        w.u32(o.v)
        w.object(o.child, THING, body(o.child)) if o.child is not None else w.object(None)
    return f


def test_primitives_and_cstring():
    w = MfcWriter()
    w.u8(1), w.u16(2), w.u32(3), w.count(4), w.cstring("abc"), w.cstring("x" * 300), w.raw(b"zz")
    raw = w.getvalue()
    assert raw[:11] == bytes([1, 2, 0, 3, 0, 0, 0, 4, 0, 0, 0]) and raw[11] == 3
    assert raw[15] == 0xFF and raw[16:18] == struct.pack("<H", 300)
    r = MfcReader(raw)
    assert (r.u8(), r.u16(), r.u32(), r.count(), r.cstring(), r.cstring(), r.raw(2)) == (1, 2, 3, 4, "abc", "x" * 300, b"zz")
    with pytest.raises(ArchiveError):
        r.u8()


def test_null_pointer():
    w = MfcWriter()
    w.object(None)
    assert w.getvalue() == b"\0\0"
    assert MfcReader(b"\0\0").object({}) is None


def test_new_class_then_known_class_and_backref():
    a, b = Obj(7), Obj(8)
    w = MfcWriter()
    w.object(a, THING, body(a))
    w.object(b, THING, body(b))
    w.object(a)                                             # back-reference
    raw = w.getvalue()
    # new class: 0xffff, schema 1, name length 5, "Thing"; class index 1, object a = index 2 (class + object share the counter)
    assert raw[:11] == b"\xff\xff\x01\x00\x05\x00Thing"
    assert raw[11:] == struct.pack("<I", 7) + b"\0\0" + struct.pack("<HI", 0x8001, 8) + b"\0\0" + struct.pack("<H", 2)
    # b took index 3: next tag is the back-reference to it
    w.object(b)
    assert w.getvalue()[-2:] == struct.pack("<H", 3)


def test_object_index_taken_before_body():
    parent = Obj(1)
    child = Obj(2)
    parent.child = child
    # parent = 2 (class 1), child = 3; a child pointing back at the parent writes u16 2
    w2 = MfcWriter()
    def pbody(wr):
        wr.u32(1)
        wr.object(child, THING, lambda x: x.object(parent))
    w2.object(parent, THING, pbody)
    assert w2.getvalue().endswith(struct.pack("<I", 1) + struct.pack("<HH", 0x8001, 2))


def make_classes(seen):
    def create():
        return Obj()

    def load(o, r):
        o.v = r.u32()
        o.child = r.object(classes)
        seen.append(o)
    classes = {"Thing": MfcClass("Thing", create=create, load=load)}
    return classes


def test_reader_roundtrip_with_backref_and_parent_reference():
    leaf = Obj(3)
    mid = Obj(2, leaf)
    top = Obj(1, mid)
    w = MfcWriter()
    w.object(top, THING, body(top))
    w.object(mid)                                           # later back-reference
    w.object(None)
    r = MfcReader(w.getvalue())
    seen = []
    cl = make_classes(seen)
    t = r.object(cl)
    assert (t.v, t.child.v, t.child.child.v) == (1, 2, 3)
    assert r.object(cl) is t.child                         # same object back
    assert r.object(cl) is None and r.pos == len(w.getvalue())
    assert [o.v for o in seen] == [3, 2, 1]


def test_back_reference_to_parent_resolves_during_body():
    parent = Obj(1)
    child = Obj(2)
    w = MfcWriter()
    def pbody(wr):
        wr.u32(1)
        wr.object(child, THING, lambda x: (x.u32(2), x.object(parent)))
    w.object(parent, THING, pbody)
    got = {}
    def create():
        return Obj()
    def load(o, r):
        o.v = r.u32()
        if o.v == 1:
            o.child = r.object({"Thing": cls})
        else:
            got["up"] = r.object({"Thing": cls})
    cls = MfcClass("Thing", create=create, load=load)
    top = MfcReader(w.getvalue()).object({"Thing": cls})
    assert got["up"] is top


def test_extended_index_0x7fff():
    w = MfcWriter(first_index=0x7FFE)
    a, b, c = Obj(1), Obj(2), Obj(3)
    w.object(a, THING, body(a))                            # class 0x7ffe, object 0x7fff (extended)
    w.object(b, THING, body(b))                            # known class 0x7ffe; object 0x8000
    w.object(a)
    w.object(c, OTHER, lambda x: x.u8(9))                  # new class 0x8001 (counter), object 0x8002
    raw = w.getvalue()
    assert raw[:6] == b"\xff\xff\x01\x00\x05\x00" and raw[11:15] == struct.pack("<I", 1)
    # known class index 0x7ffe < 0x7fff: plain tag
    assert struct.pack("<H", 0x8000 | 0x7FFE) in raw
    # back-reference to a (index 0x7fff) uses the extended form: 0x7fff + u32
    assert struct.pack("<HI", 0x7FFF, 0x7FFF) in raw
    # reader mirrors it
    r = MfcReader(raw, first_index=0x7FFE)
    cl = make_classes([])
    cl["Other"] = MfcClass("Other", create=Obj, load=lambda o, rr: setattr(o, "v", rr.u8()))
    x = r.object(cl)
    assert r.object(cl).v == 2 and r.object(cl) is x and r.object(cl).v == 9


def test_extended_class_tag():
    w = MfcWriter(first_index=0x7FFF)                      # the class itself lands on index 0x7fff
    a, b = Obj(1), Obj(2)
    w.object(a, THING, lambda x: x.u8(0))
    w.object(b, THING, lambda x: x.u8(0))
    raw = w.getvalue()
    assert struct.pack("<HI", 0x7FFF, 0x80000000 | 0x7FFF) in raw
    r = MfcReader(raw, first_index=0x7FFF)
    cl = {"Thing": MfcClass("Thing", create=Obj, load=lambda o, rr: rr.u8())}
    assert isinstance(r.object(cl), Obj) and isinstance(r.object(cl), Obj) and r.pos == len(raw)


def test_reader_errors():
    cl = make_classes([])
    with pytest.raises(ArchiveError, match="outside the map"):
        MfcReader(struct.pack("<H", 5)).object(cl)
    with pytest.raises(ArchiveError, match="unknown class"):
        MfcReader(b"\xff\xff\x01\x00\x01\x00Q").object(cl)
    w = MfcWriter()
    w.object(Obj(), OTHER, lambda x: None)
    with pytest.raises(ArchiveError, match="required"):
        MfcReader(w.getvalue()).object({"Other": MfcClass("Other", create=Obj, load=lambda o, r: None)}, expect="Thing")
    with pytest.raises(ArchiveError, match="names a class"):
        r = MfcReader(b"\xff\xff\x01\x00\x05\x00Thing" + struct.pack("<I", 1) + b"\0\0" + struct.pack("<H", 1))
        r.object(cl)
        r.object(cl)


# --- the reg builder -----------------------------------------------------------------------------------------------------

def test_build_reg_roundtrip():
    tree = {"B": {"x": -1, "s": "hi", "a": [1, 2], "f": 0.5}, "A": 3, "E": {}}
    r = parse_reg(build_reg(tree))
    assert r.to_dict() == tree and r.root_entry.type == 0x11
    assert r.root.keys() == ["A", "B", "E"]                # root sorted by strcmp


# --- typed client tail ---------------------------------------------------------------------------------------------------

def battle_state():
    prj = {k: i for i, k in enumerate(S.PRJ_FIELDS)}
    return S.ClientState(in_battle=1, name="Hero", options=dict(zip(S.OPTION_KEYS, range(1, 7))), view_x=10, view_y=-20,
                         spellbook_open=1, spellbook_pressed=3, spellbook_shortcuts=[5, 6, 7], selection=[100, 101],
                         groups={0: [100], 3: [101, 102]}, inventory_open=1, projectile_free_index=4,
                         projectile_ids=[2, 5], projectiles={2: prj, 5: dict(prj, x=99)}, fog_first_state=1,
                         fog_data=[4, 4, 8])


def test_client_state_town_keys_only():
    st = S.ClientState(name="Town", view_x=3)
    reg = parse_reg(st.to_reg_bytes())
    assert reg["CurrentState/InBattle"] == 0 and reg["Character/Name"] == "Town" and reg["View/X"] == 3
    assert "Projectiles" not in reg.root.keys() and "Fog" not in reg.root.keys()
    assert S.ClientState.from_reg(reg) == st


def test_client_state_battle_roundtrip_and_key_layout():
    st = battle_state()
    reg = parse_reg(st.to_reg_bytes())
    assert reg["GameOptions/ShowHP"] == 2 and reg["Objects/Group3"] == [101, 102] and "Group1" not in reg["Objects"].keys()
    assert reg["Prj5/x"] == 99 and reg["Prj2/actionspell"] == 15 and reg["Projectiles/IDs"] == [2, 5]
    assert reg["Fog/Data"] == [4, 4, 8] and reg["SpellBook/Shortcuts"] == [5, 6, 7]
    assert S.ClientState.from_reg(reg) == st


def test_client_state_ignores_battle_keys_when_not_in_battle():
    t = battle_state().to_tree()
    t["CurrentState"]["InBattle"] = 0
    st = S.ClientState.from_reg(parse_reg(build_reg(t)))
    assert st.projectiles == {} and st.fog_data == []


def test_client_state_defaults_for_missing_keys():
    st = S.ClientState.from_reg(parse_reg(build_reg({})))
    assert st.name == "No name" and st.in_battle == 0 and st.options == {k: 0 for k in S.OPTION_KEYS}


def make_tail():
    sc = S.ScenarioState(tuple(range(-512, 512)), bytes(range(256)) + bytes(64), [S.Location(10, 1, b"Mission".ljust(16, b"\0")), S.Location(1, 2, b"Town".ljust(16, b"\0"))], 1)
    return S.ClientTail.new("slot text", battle_state(), [(1, 2)], (3, 4), sc, [S.Hotkey(i, i + 1, bytes(i)) for i in range(9)])


def test_scenario_block_typed():
    sc = make_tail().scenario
    assert S.ScenarioState.parse(sc.pack())[0] == sc
    assert sc.locations[0].text == "Mission" and sc.locations[1].type == 2
    assert sc.shop_block(0, 1) == struct.unpack_from("<5I", sc.shops, 20)
    with pytest.raises(IndexError):
        sc.shop_block(4, 0)
    with pytest.raises(ValueError):
        S.ScenarioState(variables=(0,) * 3).pack()
    with pytest.raises(ValueError):
        S.ScenarioState(shops=b"").pack()


def test_tail_roundtrip_and_replace_state():
    t = make_tail()
    raw = S.pack_tail(t)
    back = S.parse_tail(raw, 0)
    assert back.description == "slot text" and back.state == battle_state() and back.hotkeys[3] == (3, 4, b"\0\0\0")
    assert S.pack_tail(back) == raw
    t2 = back.with_state(S.ClientState(name="B"))
    assert t2.state.name == "B" and t2.scenario == back.scenario
    with pytest.raises(ValueError):
        S.pack_tail(S.ClientTail.new(hotkeys=[S.Hotkey(0, 0, b"")] * 8))


def test_tail_truncations_are_value_errors():
    raw = S.pack_tail(make_tail())
    for cut in (10, 0x100 + 4, len(raw) - 1, len(raw) - 30):
        with pytest.raises(ValueError):
            S.parse_tail(raw[:cut], 0)


# --- container -----------------------------------------------------------------------------------------------------------

def stream():
    w = MfcWriter()
    th = Obj(5)
    w.object(th, THING, body(th))
    return S.ServerHead(10, 2, "Map", (0,) * 11 + (3, 2), w.getvalue()).pack()


def test_save_byte_exact_with_unknown_bytes_kept_raw():
    unknown = bytes(range(256)) * 3 + b"\x01"                 # odd length: padded to a word
    sg = S.SaveGame(S.ServerHead(1, 2, "M", (0,) * 13, unknown).pack(), make_tail())
    raw = sg.pack()
    back = S.parse_save(raw)
    assert back.head.rest.startswith(unknown) and back.pack() == raw
    assert S.parse_save(back.pack()).pack() == raw


def test_save_archive_reader_after_head():
    sg = S.parse_save(S.SaveGame(stream(), make_tail()).pack())
    r = sg.archive()
    o = r.object({"Thing": MfcClass("Thing", create=Obj, load=lambda o, rr: (setattr(o, "v", rr.u32()), rr.object({})))})
    assert o.v == 5


def test_container_error_messages():
    raw = S.SaveGame(stream(), make_tail()).pack()
    with pytest.raises(ValueError) as e:
        S.parse_save(b"\0\0\0\0" + raw[4:])
    assert str(e.value) == "Invalid save file"
    with pytest.raises(ValueError) as e:
        S.parse_save(raw[:7])
    assert str(e.value) == "Invalid save file"
    old = bytearray(raw)
    struct.pack_into("<I", old, 8, S.SAVE_VERSION - 1)
    with pytest.raises(ValueError) as e:
        S.parse_save(bytes(old))
    assert str(e.value) == "Outdated save file"
    newer = bytearray(raw)
    struct.pack_into("<I", newer, 8, S.SAVE_VERSION + 1)
    assert S.parse_save(bytes(newer)).version == S.SAVE_VERSION + 1      # a higher version loads, and is written back as stored
    with pytest.raises(ValueError):
        S.parse_save(raw + b"\0")
    with pytest.raises(ValueError):
        S.parse_save(raw[:-5])
    bad_end = bytearray(raw)
    struct.pack_into("<I", bad_end, 4, 99)
    with pytest.raises(ValueError, match="server block ends"):
        S.parse_save(bytes(bad_end))


def test_multiplayer_save_refused():
    raw = S.SaveGame(stream(), make_tail()).pack()
    end, = struct.unpack_from("<I", raw, 4)
    mp = raw[:end] + S.MP_HEADER.ljust(0x100, b"\0") + raw[end:]
    with pytest.raises(S.MultiplayerSave, match="multiplayer"):
        S.parse_save(mp)
    assert issubclass(S.MultiplayerSave, ValueError)
