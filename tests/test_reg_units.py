"""Synthetic tests for docs/formats/reg.md and docs/formats/units.md."""

import os
import struct

import pytest

from allods2 import units as U
from allods2.common import DATA
from allods2.reg import parse_reg, load_reg

UNITS_REG = os.path.join(DATA, "graphics", "units", "units.reg")


def entry(name, typ, a=0, b=0, raw=None):
    val = raw if raw is not None else struct.pack("<II", a & 0xFFFFFFFF, b)
    return struct.pack("<I", 0) + val + struct.pack("<I", typ) + name.encode().ljust(16, b"\0")


def reg_file(entries, roots, blob=b""):
    head = struct.pack("<6I", 0x31415926, 0, roots, 0x11, len(entries), 0)
    return head + b"".join(entries) + struct.pack("<I", len(blob)) + blob


def sample():
    blob = b"hello\0" + struct.pack("<3i", 1, 2, 3)
    ents = [entry("A", 1, 2, 4),                 # root child 0: section A -> entries 2..5
            entry("B", 2, 7),                    # root child 1: int
            entry("Name", 0, 0, 6),
            entry("Num", 3, 42),                 # type 3 reads as int too
            entry("F", 4, raw=struct.pack("<d", 0.5)),
            entry("Arr", 6, 6, 12)]
    return parse_reg(reg_file(ents, 2, blob))


def test_reg_values():
    r = sample()
    assert r["B"] == 7
    assert r["A/Name"] == "hello" and r["A/Num"] == 42
    assert r["A/F"] == 0.5 and r["A/Arr"] == [1, 2, 3]


def test_root_is_sorted_strcmp_children_strnicmp():
    r = sample()
    assert r.get("b") is None                    # root: case-sensitive
    assert r["A/name"] == "hello"                # sections: case-insensitive


def test_trailing_space_name_never_matches():
    ents = [entry("S", 1, 1, 1), entry("File0 ", 2, 5)]
    r = parse_reg(reg_file(ents, 1))
    assert r.get("S/File0") is None


def test_bad_signature_and_size():
    data = reg_file([entry("B", 2, 7)], 1)
    with pytest.raises(ValueError):
        parse_reg(b"\0\0\0\0" + data[4:])
    with pytest.raises(ValueError):
        parse_reg(data + b"x")


# --- unit animation ----------------------------------------------------------

def unit(**kw):
    vals = {k: d for k, _, d in U.INT_FIELDS}
    vals.update({k: [] for k in U.ARRAY_FIELDS})
    vals.update(MovePhases=8, MoveBeginPhases=2, AttackPhases=7, DyingPhases=4,
                BonePhases=3, Width=128, Height=128, CenterX=64, CenterY=78, Dying=1)
    vals.update(kw)
    return U.UnitType(0, 1, -1, vals, "x")


def test_directions():
    assert U.dir16(8, False) == (0, False) and U.dir16(7, False) == (15, False)
    assert U.dir16(7, True) == (1, True)                     # 15 -> mirrored 1
    assert U.dir8(8, False) == (0, False) and U.dir8(9, False) == (0, False)
    assert U.dir8(4, True) == (2, True)                      # 6 -> mirrored 2


def test_block_offsets():
    t = unit()
    assert U.move_frame(t, 8, 0) == (16 + 2, False)
    assert U.move_frame(t, 10, 3) == (16 + 10 + 2 + 3, False)
    assert U.attack_frame(t, 8, 0)[0] == 16 + 80
    assert U.dying_frame(t, 10, 1)[0] == 16 + 80 + 56 + 4 + 1
    assert U.corpse_frame(t, 8)[0] == 16 + 80 + 56 + 3
    assert U.bones_frame(t, 10, 2)[0] == 16 + 80 + 56 + 32      # idle 0: direction ignored
    assert U.expected_frames(t) == 16 + 8 * (10 + 7 + 4 + 3)


def test_flip_layout():
    t = unit(Flip=1)
    assert t.stand_frames == 9 and t.dirs == 5
    assert U.move_frame(t, 8, 0)[0] == 9 + 2
    assert U.attack_frame(t, 8, 0)[0] == 9 + 50


def test_dying_elsewhere_drops_blocks():
    t = unit(Dying=99)
    assert U.expected_frames(t) == 16 + 8 * (10 + 7)


def test_sequence_and_placement():
    t = unit(MoveAnimTime=[2, 1], MoveAnimFrame=[0, 1])
    assert t.sequence("Move") == [0, 0, 1]
    assert U.placement(t, 100, 100, 40, 60) == (100 - (0 + 20), 100 - (14 + 30))


def test_facing_is_clockwise_from_north():
    assert U.step(0) == (0, -1) and U.step(4) == (1, 0)
    assert U.step(8) == (0, 1) and U.step(12) == (-1, 0)
    assert U.step(2) == (1, -1) and U.step(3) == (0, 0)      # odd facings never move
    assert U.dir16(8, False) == (0, False)                   # sprite direction 0 = facing down


def test_hero_files_without_death_blocks():
    t = unit(Dying=1)
    assert U.hero_expected_frames(t, "swordsman_") == 16 + 8 * (10 + 7)
    assert U.hero_expected_frames(t, "unarmed") == U.expected_frames(t)


def test_event_phase():
    t = unit(AttackAnimTime=[2, 3, 1], AttackAnimFrame=[0, 1, 2])  # 0 0 1 1 1 2
    assert U.event_phase(t, 0) == 0 and U.event_phase(t, 4) == 1
    assert U.event_phase(t, 5) == 2 and U.event_phase(t, 6) is None


@pytest.mark.skipif(not os.path.exists(UNITS_REG), reason="game files not available")
def test_game_units_reg():
    types = U.load_unit_types(UNITS_REG)
    assert len(types) == load_reg(UNITS_REG)["Global/UnitCount"] == 62
    assert types[0].file == ""                               # "File0 " is not found
    assert types[1].MovePhases == 8                          # inherited from Parent 3
    ok = sum(os.path.isfile(t.sprite_paths(DATA)[0]) and t.file and
             __import__("allods2.graphics", fromlist=["x"]).SpriteFile.load(t.sprite_paths(DATA)[0]).__len__()
             == U.expected_frames(t) for t in types)
    assert ok == 59
