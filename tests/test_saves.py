"""Character files, hall of fame and saved games (docs/formats/saves.md).  The install holds only a famehall.dat; the .a2c and
.sav layouts are built from the decoded code, so these tests are synthetic (the real-file test skips without the install)."""

import os
import random
import struct

import pytest

from allods2.common import INSTALL
from allods2.formats import saves as S

from test_reg_units import entry, reg_file

FAMEHALL = os.path.join(INSTALL, "famehall.dat")


# --- byte layer ---------------------------------------------------------------------------------------------------------

def test_checksum_is_double_and_add():
    assert S.checksum(b"") == 0 and S.checksum(b"\x01") == 1 and S.checksum(b"\x01\x02") == 4     # 1*2 + 2
    assert S.checksum(b"\xff" * 40) == (sum(0xFF << i for i in range(40))) & 0xFFFFFFFF


def test_xor_stream_key_zero_is_identity_and_the_cipher_is_an_involution():
    data = bytes(range(64))
    assert S.xor_stream(data, 0) == data
    for key in (1, 0x1234, 0x7FFF):
        c = S.xor_stream(data, key)
        assert c != data and S.xor_stream(c, key) == data


def test_xor_stream_first_bytes():
    # key 0x0100: r = 0x01000100; byte 0 ^= 0x00 (bits 16..23 of r), then r <<= 1 = 0x02000200; byte 1 ^= 0x00 ...
    # the key bit reaches bits 16..23 after 8 shifts: byte 8 is xored with 0x01 (r = 0x01000100 << 8 = 0x00010000 + ...)
    out = S.xor_stream(bytes(10), 0x0100)
    assert out[:8] == bytes(8) and out[8] == 0x01 and out[9] == 0x02


@pytest.mark.parametrize("unit", (1, 2))
def test_rle_roundtrip_and_ops(unit):
    rng = random.Random(3)
    for n in (0, 1, 2, 3, 127, 128, 300, 1000):
        a = bytes(rng.choice((0, 0, 0, 1, 2)) for _ in range(n * unit))
        assert S.rle_decode(S.rle_encode(a, unit), unit) == a
    assert S.rle_decode(S.rle_encode(bytes(2560))) == bytes(2560)


def test_rle_byte_stream_layout():
    # header = number of units; 0x80|n = run of n copies of the next unit; n < 0x80 = literal of n units
    assert S.rle_decode(struct.pack("<I", 7) + bytes((0x85, 9, 2, 1, 2))) == bytes((9,) * 5 + (1, 2))
    w = struct.pack("<I", 4) + bytes((0x84, 0x34, 0x12))
    assert S.rle_decode(w, 2) == b"\x34\x12" * 4
    with pytest.raises(ValueError):
        S.rle_decode(struct.pack("<I", 9) + bytes((0x82, 1)))


def test_rle_run_and_literal_limits():
    enc = S.rle_encode(bytes(300))                  # runs of at most 0x7f
    assert enc[4] == 0x80 | 0x7F and enc[6] == 0x80 | 0x7F
    enc = S.rle_encode(bytes(i % 2 for i in range(300)))    # literals: 0x7e units (count - 1 with count capped at 0x7f)
    assert enc[4] == 0x7E


# --- items ---------------------------------------------------------------------------------------------------------------

def test_item_stack_forms():
    assert S.encode_item(S.Item(0x1234, 5)) == bytes.fromhex("341285")
    assert S.encode_item(S.Item(0x1234, 0x3F)) == bytes.fromhex("3412bf")
    assert S.encode_item(S.Item(0x1234, 100)) == bytes.fromhex("3412006400")
    assert S.encode_item(S.Item(0, 0)) == bytes.fromhex("000080")
    assert S.encode_item(S.Item(0x1234, 5, new=True)) == bytes.fromhex("3412c5")
    for it in (S.Item(0x1234, 5), S.Item(0x1234, 100), S.Item(0, 0), S.Item(0x1234, 5, new=True)):
        assert S.decode_item(S.encode_item(it))[0] == it


def test_item_with_modifiers_layout():
    # flag 0x20 | 0x10 (a castSpell record) | units: castSpell 2 + min/spread 2 + plain 1 = 5; then price u32 and the records
    it = S.Item(0x0E41, 1, 600, ((41, 3, 7), (44, 10, 4), (12, 9, 0)))
    raw = S.encode_item(it)
    assert raw == bytes.fromhex("410e35") + struct.pack("<I", 600) + bytes((41, 3, 0x32, 7, 44, 10, 44, 4, 12, 9))
    assert S.decode_item(raw) == (it, len(raw))
    # kind 1 is not written; the reader consumes 2 units for the min/max kinds ',' '-' '.' '/' '0'
    raw = S.encode_item(S.Item(1, 1, 5, ((1, 1, 0), (48, 1, 2))))
    assert raw == bytes.fromhex("010022") + struct.pack("<I", 5) + bytes((48, 1, 48, 2))


def test_item_code_fields():
    it = S.Item((3 << 12) | (2 << 8) | (4 << 5) | 17)
    assert (it.material, it.cls, it.quality, it.index) == (3, 2, 4, 17)


def test_packet_roundtrip_and_header():
    items = [S.Item(0x1234, 5), S.Item(0, 0), S.Item(0x2345, 1, 77, ((12, 3, 0),))]
    p = S.ItemPacket(items, head=b"\1\2\3", count=3)
    raw = p.pack()
    assert raw[:9] == b"\1\2\3" + struct.pack("<HHH", 3, 0, len(raw) - 9)
    assert S.ItemPacket.parse(raw).items == items
    assert S.ItemPacket.parse(raw, fixed=3).items == items


# --- the character file --------------------------------------------------------------------------------------------------

def sample():
    hot = S.pack_hotkeys([(i, 2 * i, bytes(range(i))) for i in range(9)])
    return S.Character(
        identity=S.Identity((7, 99), 5, "Alex|Mage", 0xC0, 4, 2, 4, 1, b"\1\2\3"),
        stats=S.Stats(11, 2, 33, 4, 1000, (40, 30, 20, 10), 0b101010, 3, (1000, 20, 30, 40, 50)),
        settings=bytes(2560), equipment=S.ItemPacket([S.Item(0x1234, 1, 500, ((41, 3, 2),))] + [S.Item(0, 0)] * 11),
        pack=S.ItemPacket([S.Item(0x0E11, 5), S.Item(0x1111, 100)], count=2), hotkeys=hot)


def test_a2c_roundtrip_is_byte_exact_through_the_layout():
    raw = S.build_a2c(sample(), random.Random(5))
    ch = S.parse_a2c(raw)
    assert ch.stats == sample().stats and ch.identity == sample().identity and ch.settings == bytes(2560)
    assert ch.equipment.items[0].mods == ((41, 3, 2),) and len(ch.equipment.items) == 12
    assert [i.count for i in ch.pack.items] == [5, 100] and ch.hotkey_records()[3] == (3, 6, b"\0\1\2")
    assert ch.order == [S.TAG_ID, S.TAG_STATS, S.TAG_BLOB, S.TAG_EQUIP, S.TAG_PACK, S.TAG_HOTKEYS]
    assert S.build_a2c(ch) == raw


def test_a2c_header_and_cipher():
    raw = S.build_a2c(sample(), random.Random(5))
    assert struct.unpack_from("<I", raw, 0)[0] == 0x04507989
    tag, ln, zero, flags, csum = struct.unpack_from("<IIHHI", raw, 4)
    assert tag == 0xAAAAAAAA and ln == 0x34 and zero == 0 and flags < 0x8000
    plain = sample().identity.pack()
    assert csum == S.checksum(plain) and raw[20:20 + 0x34] == S.xor_stream(plain, flags)


@pytest.mark.parametrize("flags", (0, 0x7FFF, 0x2000, 0x0001, 0x4000, 0x0555))
def test_stats_chunk_junk_bytes_follow_the_flag_bits(flags):
    ch = sample()
    ch.layout = {S.TAG_STATS: (flags, bytes(range(1, 17)), 0)}
    ch.order = [S.TAG_STATS]
    raw = S.build_a2c(ch)
    tag, ln, _, fl, csum = struct.unpack_from("<IIHHI", raw, 4)
    # the header length counts the set bits; the shared bit 0x2000 writes two junk bytes (word +0x1c and pool 4), so the body is one longer
    assert fl == flags and ln == 0x34 + bin(flags).count("1") and len(raw) == 20 + ln + (1 if flags & 0x2000 else 0)
    back = S.parse_a2c(raw)
    assert back.stats == ch.stats and back.layout[S.TAG_STATS][0] == flags


def test_stats_chunk_field_transforms():
    # first fields of the stored image for the all-zero plain stats (FUN_004ee7cb inverse): w0 = v0 ^ 0x01529251,
    # w1 = v1 - (v0 * 5 + 0x13141516), w2 = v2 - (v1 * 7 + 0xabcdef), w3 = v3 ^ 0x17ff12aa
    st = S.Stats(0, 0, 0, 0, 0, (0, 0, 0, 0), 0, 0, (0, 0, 0, 0, 0))
    stored = S._stats_encode(st.pack())
    assert struct.unpack_from("<4I", stored) == (0x01529251, (-0x13141516) & 0xFFFFFFFF, (-0xABCDEF) & 0xFFFFFFFF, 0x17FF12AA)
    assert struct.unpack_from("<I", stored, 0x18)[0] == 0x10121974
    assert struct.unpack_from("<I", stored, 0x20)[0] == 0xDADEDADE
    rng = random.Random(9)
    for _ in range(20):
        plain = bytes(rng.randrange(256) for _ in range(0x34))
        assert S._stats_decode(S._stats_encode(plain)) == plain


def test_a2c_errors():
    raw = bytearray(S.build_a2c(sample(), random.Random(5)))
    with pytest.raises(ValueError):
        S.parse_a2c(b"\0\0\0\0" + bytes(raw[4:]))               # magic
    bad = bytearray(raw)
    bad[20 + 50] ^= 1                                              # one of the last 32 payload bytes of the first chunk: checksum
    with pytest.raises(ValueError, match="checksum"):
        S.parse_a2c(bytes(bad))
    early = bytearray(raw)
    early[20 + 5] ^= 1      # quirk: `h = 2h + b` shifts a byte out after 32 steps, so the first bytes of a long chunk are not protected
    S.parse_a2c(bytes(early))
    unk = bytearray(raw)
    struct.pack_into("<I", unk, 4, 0x12345678)
    with pytest.raises(ValueError):
        S.parse_a2c(bytes(unk))


def test_identity_template_and_filename():
    for flags, name in ((0, "Start_MF"), (0x40, "Start_MM"), (0x80, "Start_FF"), (0xC0, "Start_FM"), (0x3F, "Start_MF")):
        assert S.Identity(flags=flags).template == name
    assert S.Identity(ids=(12, 345)).filename == "12345.a2c"
    assert S.Stats(spells=0b1000110).spell_ids == [1, 2, 6]


# --- famehall.dat ---------------------------------------------------------------------------------------------------------

def test_famehall_roundtrip():
    es = [S.HallEntry("Ann", 100, 1, 2), S.HallEntry("Bob", 50, 0, 0)]
    raw = S.build_famehall(es)
    assert raw[:4] == struct.pack("<I", 2) and raw[4:8] == struct.pack("<I", 4) and raw[8:12] == b"Ann\0"
    assert S.parse_famehall(raw) == es
    with pytest.raises(ValueError):
        S.parse_famehall(raw + b"\0")


@pytest.mark.skipif(not os.path.isfile(FAMEHALL), reason="famehall.dat not in the install")
def test_install_famehall():
    raw = open(FAMEHALL, "rb").read()
    es = S.parse_famehall(raw)
    assert [e.name for e in es][:3] == ["Diamond", "Glazz", "Gella"] and len(es) == 10
    assert [e.a for e in es] == sorted((e.a for e in es), reverse=True)
    assert S.build_famehall(es) == raw


# --- saved games ----------------------------------------------------------------------------------------------------------

def server_stream(rest=b"\1\2\3\4"):
    head = S.ServerHead(1234, 77, "Scenario Map", tuple(range(100, 111)) + (5, 2), rest)
    return head.pack()


def tail():
    reg = reg_file([entry("CurrentState", 1, 1, 1), entry("InBattle", 2, 0)], 1)
    sc = S.ScenarioState(tuple(i for i in range(1024)), bytes(range(256)) + bytes(64), [(10, 1, b"Mission"), (1, 2, b"Town")], 1)
    return S.ClientTail("a saved game", S.parse_reg(reg), reg, [(1, 2), (3, 4)], (9, 8), sc, [(i, 0, b"x" * i) for i in range(9)])


def test_server_head_fields_and_counters():
    h = S.ServerHead.parse(server_stream())
    assert (h.tick, h.block, h.map_name) == (1234, 77, "Scenario Map")
    assert h.words[:3] == (100, 101, 102) and h.scenario == 5 and h.difficulty == 2 and h.rest == b"\1\2\3\4"
    long = S.ServerHead(1, 2, "x" * 300, (0,) * 13, b"").pack()
    assert S.ServerHead.parse(long).map_name == "x" * 300 and long[8] == 0xFF


def test_save_roundtrip_and_layout():
    sg = S.SaveGame(server_stream(), tail())
    raw = sg.pack()
    magic, end, version, ln = struct.unpack_from("<IIII", raw, 0)
    assert magic == 0x26677342 and version == 0x0BAD0002 and end == 16 + ln
    assert struct.unpack_from("<I", raw, 16)[0] == (len(server_stream()) + 1) // 2           # the word count heads the RLE image
    back = S.parse_save(raw)
    assert back.head.tick == 1234 and back.stream.rstrip(b"\0") == server_stream().rstrip(b"\0")
    t = back.tail
    assert t.description == "a saved game" and t.reg["CurrentState"] is not None and t.reg_bytes == tail().reg_bytes
    assert t.missions == [(1, 2), (3, 4)] and t.mission_tail == (9, 8)
    assert t.scenario.variables[1000] == 1000 and t.scenario.locations[0][:2] == (10, 1) and t.scenario.current == 1
    assert t.hotkeys[4] == (4, 0, b"xxxx")
    assert back.pack() == raw


def test_save_errors():
    raw = S.SaveGame(server_stream(), tail()).pack()
    with pytest.raises(ValueError, match="Invalid"):
        S.parse_save(b"\0\0\0\0" + raw[4:])
    old = bytearray(raw)
    struct.pack_into("<I", old, 8, 0x0BAD0001)
    with pytest.raises(ValueError, match="Outdated"):
        S.parse_save(bytes(old))
    with pytest.raises(ValueError):
        S.parse_save(raw + b"\0")                                   # bytes after the client block


def test_scenario_block_size():
    sc = S.ScenarioState()
    assert len(sc.pack()) == 0x1000 + 0x140 + 4 + 4
    assert len(S.ScenarioState(locations=[(1, 2, b"a")]).pack()) == 0x1000 + 0x140 + 4 + 24 + 4
    assert S.reg_length(tail().reg_bytes) == len(tail().reg_bytes)
