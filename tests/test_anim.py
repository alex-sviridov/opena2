"""allods2.anim against docs/formats/animation.md: synthetic rules always,
the full install when samples/ (or ALLODS2_DATA) is present."""

import os

import numpy as np
import pytest

from allods2 import anim as A
from allods2 import cli
from allods2 import units as U
from allods2.common import DATA
from allods2.graphics import Canvas

from helpers import aset_of, needs_data, unit_type

# -- timing ----------------------------------------------------------------

def test_tick_period_by_speed():
    assert [A.period_ms(s) for s in range(9)] == [125, 100, 83, 71, 62, 50, 41, 35, 31]
    assert A.tick_at_ms(61) == 0 and A.tick_at_ms(62) == 1 and A.tick_at_ms(1000, 8) == 32


def test_walk_ticks_per_cell():
    assert A.walk_ticks_per_cell(18) == 15
    assert A.walk_ticks_per_cell(18, diagonal=True) == 22
    assert A.walk_ticks_per_cell(24) == 11


def test_walk_odometer_one_orthogonal_cell_is_256_units():
    odo, moved = A.walk_odometer(12, 14, 15)
    assert odo == 256 and moved == (-256, 0)
    odo, moved = A.walk_odometer(12, 29, 15)                # two cells
    assert odo == 512 and moved == (-512, 0)


# -- actions and frame_at ----------------------------------------------------

def test_actions_present_by_type_fields():
    a = aset_of(unit_type())
    assert list(a.actions) == ["stand", "move", "attack", "dying", "corpse", "bones1"]
    assert a.actions["attack"].phases == [0, 1, 1, 2]
    assert a.actions["dying"].phases == [0, 0, 1, 1]
    b = aset_of(unit_type(IdlePhases=2, IdleAnimTime=[1, 1], IdleAnimFrame=[0, 1], BonePhases=-1))
    assert "idle" in b.actions and "bones1" not in b.actions and b.idle_action == "idle"


def test_idle_loops_from_counter_plus_one():
    a = aset_of(unit_type(IdlePhases=3, IdleAnimTime=[1, 1, 1], IdleAnimFrame=[0, 1, 2]))
    assert [a.frame_at("idle", 8, k).phase for k in range(7)] == [1, 2, 0, 1, 2, 0, 1]
    assert a.frame_at("idle", 8, 0, start=2).phase == 0


def test_attack_once_then_stand():
    a = aset_of(unit_type())
    shown = [(r.action, r.phase) for r in (a.frame_at("attack", 8, k) for k in range(6))]
    assert shown == [("attack", 0), ("attack", 1), ("attack", 1), ("attack", 2),
                     ("stand", 0), ("stand", 0)]


def test_attack_then_idle_continues_counter():
    a = aset_of(unit_type(IdlePhases=3, IdleAnimTime=[1, 1, 1], IdleAnimFrame=[0, 1, 2]))
    # attack length 4 leaves the counter at 4; next idle element (4 + 1) % 3
    assert [a.frame_at("attack", 8, k).phase for k in (3, 4, 5)] == [2, 2, 0]
    assert a.frame_at("attack", 8, 4).action == "idle"


def test_dying_two_ticks_per_frame_then_corpse_held():
    a = aset_of(unit_type())
    refs = [a.frame_at("dying", 8, k) for k in range(7)]
    assert [(r.action, r.phase) for r in refs] == [("dying", 0), ("dying", 0), ("dying", 1),
                                                    ("dying", 1), ("corpse", 1), ("corpse", 1),
                                                    ("corpse", 1)]
    assert refs[3].index == refs[4].index


def test_events_only_inside_sequence():
    a = aset_of(unit_type(Projectile=1, ShootDelay=3, AttackDelay=1))
    assert a.actions["attack"].events == {"impact": 1, "release": 3}
    assert [a.frame_at("attack", 8, k).events for k in range(4)] == [(), ("impact",), (), ("release",)]
    assert aset_of(unit_type(Projectile=1)).actions["attack"].events == {"impact": 1}   # 9 >= len
    assert aset_of(unit_type(ShootDelay=2)).actions["attack"].events == {"impact": 1}   # no projectile
    assert aset_of(unit_type(ShootDelay=2)).attack_events("cast") == {"impact": 1, "release": 2}


def test_move_is_distance_driven():
    a = aset_of(unit_type())
    # 15 ticks per cell: steps 17 x 14 then 18, odometer 17, 34, ..., 238, 256
    # -> elements 1..14, 16 of the 8-element sequence 0,0,1,1,2,2,3,3
    phases = [a.frame_at("move", 4, k, ticks_per_cell=15).phase for k in range(15)]
    assert phases == [0, 1, 1, 2, 2, 3, 3, 0, 0, 1, 1, 2, 2, 3, 0]
    slow = [a.frame_at("move", 4, k, ticks_per_cell=30).phase for k in range(4)]
    assert slow == [0, 0, 0, 1]
    assert a.frame_at("move", 4, 0).index == U.move_frame(a.t, 4, 0)[0]   # begin phase skipped


def test_frame_indices_follow_layout():
    t = unit_type()
    a = aset_of(t)
    assert a.frame_at("stand", 12, 0).index == 4
    assert a.frame_at("attack", 12, 3).index == 16 + 5 * 8 + 2 * 3 + 2
    assert a.frame_at("dying", 12, 0).index == 16 + 8 * 8 + 2 * 2
    assert a.missing_frames() == []


# -- mirroring ----------------------------------------------------------------

@pytest.mark.parametrize("center_x", [64, 63])
def test_mirrored_direction_flips_in_place(center_x):
    t = unit_type(Flip=1, CenterX=center_x)
    a = aset_of(t)
    left = a.frame_at("attack", 12, 0)                      # stored direction 2
    right = a.frame_at("attack", 4, 0)                      # 8 - 6 = 2, mirrored
    assert (left.index, left.mirrored) == (right.index, False) and right.mirrored
    # the anchor stays: CenterX - Width/2 is not negated (animation.md §2.3)
    assert left.hotspot == right.hotspot == (center_x - 64 + 2, 70 - 64 + 0)

    def row(ref):
        cv = Canvas(12, 1)
        a.draw(cv, ref, 6, 6)
        return cv.pix[0, :, 0].tolist()
    x0 = 6 - left.hotspot[0]
    assert row(left)[x0:x0 + 4] == [0, 60, 120, 180]
    assert row(right)[x0:x0 + 4] == [180, 120, 60, 0]
    assert np.count_nonzero(row(left)) == np.count_nonzero(row(right)) == 3


def test_stand_mirrors_odd_facings_with_flip():
    a = aset_of(unit_type(Flip=1))
    refs = {d: a.frame_at("stand", d, 0) for d in range(16)}
    for d in range(1, 8):
        assert refs[d].mirrored and refs[d].index == refs[16 - d].index
    assert not any(refs[d].mirrored for d in (0, 8, 9, 15))


# -- the install --------------------------------------------------------------

@pytest.fixture(scope="module")
def types():
    return U.unit_types(DATA)


@needs_data
def test_every_unit_and_hero_set_is_in_range(types):
    keys = A.unit_keys(DATA, types)
    assert len(keys) == 61 + 30
    for k in keys:
        a = A.load_unit_set(k, DATA, types)
        assert "stand" in a.actions
        missing = a.missing_frames()
        if k == 2:      # Unit33: Flip file under a non-Flip type (animation.md §2.5)
            assert missing
        else:
            assert missing == [], (k, missing[:3])


@needs_data
def test_unreachable_unit0_file(types):
    with pytest.raises(FileNotFoundError):
        A.load_unit_set(3, DATA, types)


@needs_data
def test_death_type_shares_placement(types):
    ids = U.by_id(types)
    for t in types:
        td = ids.get(t.Dying)
        if td is not None:
            assert (t.CenterX, t.CenterY, t.Width, t.Height) == \
                (td.CenterX, td.CenterY, td.Width, td.Height), t.id


@needs_data
def test_hero_dies_with_unarmed_or_staff_mage(types):
    assert A.load_unit_set("heroes/swordsman", DATA, types).td.id == 24
    assert A.load_unit_set("heroes_l/archer", DATA, types).td.id == 1


@needs_data
def test_cli_preview(tmp_path):
    grid = tmp_path / "grid.png"
    assert cli.main(["anim", "preview", "monsters/bee", str(tmp_path / "gif"),
                     "--data", DATA, "--grid", str(grid)]) == 0
    gifs = sorted(os.listdir(tmp_path / "gif"))
    assert "attack_d08.gif" in gifs and len(gifs) == 8 * 6
    assert grid.is_file()
