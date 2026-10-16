"""Integration: the animation API against the whole install
(animation.md §5.1), plus synthetic checks of the checker and the
projectile trail rule."""

import pytest

from allods2 import anim as A
from allods2.anim import coverage as C
from allods2.anim.projectiles import ProjectileSet
from allods2.common import DATA
from allods2.graphics import Canvas

from helpers import aset_of, needs_data, projectile, sprite_file, unit_type


# -- the install -----------------------------------------------------------------

@pytest.fixture(scope="module")
def report():
    return C.verify(DATA)


@needs_data
def test_every_animated_asset_loads_and_draws(report):
    assert report.errors == []
    assert report.sets == 546
    assert report.out_of_range.keys() == C.KNOWN_OUT_OF_RANGE.keys()
    assert report.drawn > 49000


@needs_data
def test_every_multi_frame_sprite_file_is_used_or_excluded(report):
    assert report.unreached == []
    assert report.stale == []
    assert len(report.excluded) == 27 and report.multi == 695
    assert "projectiles/smoke0/sprites.16a" in report.reached
    assert "projectiles/smoke1/sprites.16a" in report.reached


# -- the checker -----------------------------------------------------------------

def test_check_set_accepts_a_good_set():
    r = C.Report()
    C.check_set(aset_of(unit_type()), "synthetic", r)
    assert r.errors == [] and r.refs > 0 and r.drawn > 0


def test_check_set_reports_missing_frames_and_bad_events():
    t = unit_type()
    a = A.UnitSet("short", t, t, sprites={"main": sprite_file(3), "death": sprite_file(3)})
    a.actions["attack"].events["impact"] = 99
    r = C.Report()
    C.check_set(a, "short", r)
    msgs = " ".join(m for _, m in r.errors)
    assert "past the end" in msgs and "event impact at 99" in msgs


def test_exclusion_categories():
    assert {c for _, c, _ in C.EXCLUSIONS} == {"not animated", "never loaded", "empty"}
    assert all(p == p.lower() for p, _, _ in C.EXCLUSIONS)


# -- projectile trails (10, 12) --------------------------------------------------

def trail_projectile(pid):
    return projectile(pid, {"main": sprite_file(64), "trail": sprite_file(6)})


def test_trail_keeps_six_pre_move_positions_oldest_first():
    pts = []
    for k in range(8):
        ProjectileSet.record_trail(pts, 800 + 8 * k, 960)
    assert len(pts) == 6
    p = trail_projectile(10)
    refs = p.trail(pts)
    assert [r.index for r, _ in refs] == list(range(6))
    assert [xy for _, xy in refs] == [(100 + k, 120) for k in range(2, 8)]
    assert refs[0][0].hotspot == (2, 0)                  # frame 0 is 4 x 1
    assert not trail_projectile(13).has_trail and p.has_trail


def test_trail_packing_is_16_bit():
    pts = ProjectileSet.record_trail([], 0x10008, 16)    # x overflows into y
    assert trail_projectile(12).trail(pts)[0][1] == (1, (16 + 1) >> 3)


def test_trail_draws_alpha_at_view_offset(monkeypatch):
    from allods2.anim import base
    calls = []
    monkeypatch.setattr(base, "blit", lambda cv, sf, i, x, y, pal, mode, *a: calls.append((i, x, y, mode)))
    pts = ProjectileSet.record_trail([], 8 * 20, 8 * 30)
    ProjectileSet.record_trail(pts, 8 * 21, 8 * 30)
    trail_projectile(10).draw_trail(Canvas(40, 40), pts, ox=10, oy=10, z=5)
    assert calls == [(0, 20 - 10 - 2, 30 - 10 - 0 - 5, "alpha"), (1, 21 - 10 - 2, 15, "alpha")]
