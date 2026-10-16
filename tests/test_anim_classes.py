"""Structures, bridges, objects, projectiles and the lens (animation.md §4):
synthetic rules always, the full install when present."""

import math
import os

import numpy as np
import pytest

from allods2 import anim as A
from allods2.anim.structures import BridgeSet, StructureSet
from allods2.common import DATA

from helpers import needs_data, projectile, sprite_file


# -- structures ----------------------------------------------------------------

def structure(**kw):
    rec = dict(ID=100, File="x\\house", TileWidth=2, TileHeight=1, FullHeight=2, Phases=3,
               seq=[1, 1, 2, 0], mask="-+-+", Indestructible=0)
    rec.update(kw)
    return rec


def test_structure_pieces_follow_mask_and_phase():
    s = StructureSet(structure(), sprites={"main": sprite_file(2 * 2 + 2 * 2 + 4)})
    ref = s.frame_at("intact", 0, 0)                # k = seq[0] = 1
    assert [p.index for p in ref.parts] == [0, 4, 2, 5]
    ref = s.frame_at("intact", 0, 2)                # k = 2: W*FH + A + rank
    assert [p.index for p in ref.parts] == [0, 6, 2, 7]
    assert [p.index for p in s.frame_at("intact", 0, 3).parts] == [0, 1, 2, 3]
    assert [p.index for p in s.frame_at("intact", 0, 0, animate=False).parts] == [0, 1, 2, 3]


def test_structure_layout_and_destroyed_block():
    s = StructureSet(structure(), sprites={"main": sprite_file(12)})
    ref = s.frame_at("destroyed", 0, 0)
    assert [p.index for p in ref.parts] == [8, 9, 10, 11]
    # FH - TH = 1 row above the footprint; anchor = footprint top-left
    assert [(p.dx, p.dy) for p in ref.parts] == [(0, -32), (32, -32), (0, 0), (32, 0)]
    assert "destroyed" not in StructureSet(structure(Indestructible=1),
                                           sprites={"main": sprite_file(8)}).actions


def test_bridge_pieces():
    b9 = BridgeSet(structure(ID=0x21, Phases=1, seq=[], mask=""), w=3, h=3,
                   sprites={"main": sprite_file(9)})
    assert [p.index for p in b9.frame_at("bridge", 0, 0).parts] == list(range(9))
    b14 = BridgeSet(structure(ID=0x25, Phases=1, seq=[], mask=""), w=4, h=3,
                    sprites={"main": sprite_file(14)})
    rows = lambda t: [p.index for p in b14.frame_at("bridge", 0, t).parts]
    assert rows(0) == [0, 2, 1, 3, 4, 5, 5, 6, 7, 12, 8, 13]
    assert rows(5)[10] == 9 and rows(7)[10] == 11


# -- objects ---------------------------------------------------------------------

def object_rec(**kw):
    rec = dict(ID=5, file="tree", Index=3, Width=128, Height=128, CenterX=64, CenterY=100,
               seq=[0, 0, 1, 2], DeadObject=-1)
    rec.update(kw)
    return rec


def test_object_phase_uses_clock_and_cell():
    o = A.ObjectSet(object_rec(), sprites={"main": sprite_file(8)})
    assert o.frame_at("anim", 0, 0).index == 3
    assert o.frame_at("anim", 0, 3).index == 5
    assert o.frame_at("anim", 0, 0, x=2, y=0).index == 4          # (0 + 2 + 0) % 4 = 2
    assert o.frame_at("anim", 0, 1, x=1, y=1).index == 5          # (1 + 1 + 1) % 4 = 3
    assert o.frame_at("still", 0, 7).index == 3
    assert o.frame_at("anim", 0, 3, animate=False).index == 0     # option off: frame 0, not Index


def test_object_dead_frame_and_anchor():
    dead = object_rec(ID=6, file="dead")
    o = A.ObjectSet(object_rec(DeadObject=6), dead,
                    sprites={"main": sprite_file(8), "dead": sprite_file(1)})
    ref = o.frame_at("dead", 0, 0)
    assert (ref.source, ref.index) == ("dead", 0)
    assert ref.hotspot == (2, 36)               # (64 - 64 + 4/2, 100 - 64 + 1/2)


# -- projectiles -------------------------------------------------------------------

def test_projectile_default_phase_two_ticks_per_frame():
    p = projectile(10)
    assert [p.phase(t, age0=-1) for t in range(9)] == [0, 0, 1, 1, 2, 2, 3, 3, 0]
    assert [p.phase(t, age0=0) for t in range(4)] == [0, 1, 1, 2]


def test_projectile_special_phase_rules():
    assert [projectile(0x1c).phase(t, age0=-1) for t in range(13)] == \
        [0, 4, 3, 2, 1, 0, 1, 2, 1, 0, 1, 2, 3]
    assert [projectile(0x36, Phases=21).phase(t, age0=0) for t in range(3)] == [0, 1, 2]
    assert [projectile(0x2c).phase(t, age0=-1) for t in range(3)] == [0, 1, 2]


def test_projectile_directions_and_flip():
    p = projectile(12, Flip=1)
    assert p.frame_at("flight", 8, 0).index == 0
    r = p.frame_at("flight", 4, 0, age0=-1)       # d = 12 -> 16 - 12 = 4, mirrored
    assert (r.index, r.mirrored) == (16, True)
    assert projectile(21, RotationPhases=1).frame_at("flight", 4, 2, age0=-1).index == 1
    assert p.frame_at("flight", 8, 0).hotspot == (32, 32)


def test_hail_falls_then_shatters():
    p = projectile(0x17, Phases=9)
    refs = [p.frame_at("effect", 8, t, age0=-1) for t in (0, 7, 8, 9)]
    assert [r.index for r in refs] == [8, 8, 0, 1]
    assert refs[0].hotspot[1] - refs[1].hotspot[1] == 28


def test_lens_effect_and_heal_draw_nothing():
    assert projectile(7, A16=0).frame_at("flight", 8, 0).effect == "lens"
    assert projectile(0x38).frame_at("effect", 8, 0).index == -1


# -- lens --------------------------------------------------------------------------

def test_lens_table():
    t = A.lens_table()
    assert t.shape == (19, 19, 2)
    assert tuple(t[0, 0]) == (0, 0)
    k = lambda r: r / (20 * math.sin(math.atan(r / 4)))
    assert tuple(t[18, 0]) == (int(18 * k(18) + 0.5), 0) == (17, 0)
    assert tuple(t[3, 4]) == (int(3 * k(5) + 0.5), int(4 * k(5) + 0.5))
    assert tuple(t[18, 18]) == (18, 18)                 # r = 25 >= n: unchanged


def test_lens_magnifies_centre():
    pix = np.zeros((60, 60, 3), np.uint8)
    pix[30, 30] = 255
    A.apply_lens(pix, 30, 30)
    assert pix[30, 30, 0] == 255
    assert pix[30, 31, 0] == 255 and pix[30, 29, 0] == 255     # (1, 0) samples k(1)*1 -> 0
    assert pix[0, 0, 0] == 0


# -- the install -------------------------------------------------------------------

@needs_data
@pytest.mark.parametrize("kind,loader", [("structure", A.load_structure_records),
                                         ("object", A.load_object_records),
                                         ("projectile", A.load_projectile_records)])
def test_every_record_is_in_range(kind, loader):
    burning = {1, 4, 7, 10, 13, 16, 19}      # files absent (animation.md §1.7)
    for i in loader(DATA):
        s = A.load_set("%s:%d" % (kind, i), DATA)
        if kind == "object" and i in burning:
            assert s.sprites() is None
            continue
        assert s.sprites() is not None, (kind, i)
        assert s.missing_frames() == [], (kind, i)


@needs_data
def test_cli_preview_other_classes(tmp_path):
    from allods2 import cli
    for key, n in (("structure:11", 2), ("object:0", 3), ("projectile:12", 8)):
        d = tmp_path / key.replace(":", "_")
        assert cli.main(["anim", "preview", key, str(d), "--data", DATA,
                         "--grid", str(tmp_path / "g.png")]) == 0
        assert len(os.listdir(d)) == n


# -- terrain water, burning cells, cursors, UI ----------------------------------

def test_water_phase_per_cell():
    from allods2.graphics.terrain import cell_value
    w = A.WaterSet("w", None, np.array([[cell_value(8, 0, 0), cell_value(0, 0, 0)],
                                         [cell_value(9, 0, 0), cell_value(8, 0, 0)]]), x0=3, y0=1)
    # 8 + ((s + (x+1)*y + (clock >> 2)) & 3) with absolute x, y
    assert w.cell_sets(0).tolist() == [[8 + ((8 + 4 * 1) & 3), 0], [8 + ((9 + 4 * 2) & 3), 8 + ((8 + 5 * 2) & 3)]]
    assert w.cell_sets(4)[0, 0] == 8 + ((8 + 4 + 1) & 3)
    assert (w.cell_sets(5, animate=False)[[0, 1, 1], [0, 0, 1]] == 8).all()


def test_burning_cell_frames_and_light():
    rec = dict(Width=128, Height=128)
    b = A.BurningSet(rec, dict(Width=64, Height=96), sprites={"fire": sprite_file(11), "steam": sprite_file(9)})
    refs = [b.frame_at("fire", 0, t) for t in range(23)]
    assert [r.index for r in refs[:5]] == [0, 0, 1, 1, 2]
    assert refs[21].index == 10 and refs[22].index == -1
    assert refs[6].events == ("light=0",) and refs[0].events == ("light=36",)
    assert b.frame_at("steam", 0, 17).index == 8 and b.frame_at("steam", 0, 18).index == -1
    assert b.frame_at("steam", 0, 0).hotspot == (32, 48)


def test_cursor_frames():
    assert A.cursor_frame(0, 100, 10) == 0
    assert A.cursor_frame(100, 100, 10) == 0 and A.cursor_frame(101, 100, 10) == 1
    assert A.cursor_frame(1010, 100, 10) == 0
    assert A.cursor_frame(5000, 2000000000, 10) == 0
    c = A.CursorSet("move/sprites.16a", 2, 3, 100, sprites={"main": sprite_file(11)})
    assert c.frame_at("cursor", 0, 202).index == 2 and c.frame_at("cursor", 0, 0).hotspot == (2, 3)


@needs_data
def test_all_keys_load_and_cursor_files_exist():
    keys = A.all_keys(DATA)
    assert len(keys["cursors"]) == 28 and len(keys["projectiles"]) == 31
    for k in keys["cursors"] + keys["ui"] + keys["effects"]:
        s = A.load_set(k, DATA)
        for src in {a.source for a in s.actions.values()}:
            assert s.sprites(src) is not None, k
        assert s.missing_frames() == [], k
    w = A.load_set("water:auto", DATA)
    assert ((w.cell_sets(0) >= 8) & (w.cell_sets(0) < 12)).mean() >= 0.4
