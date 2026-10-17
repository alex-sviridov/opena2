"""Rectangle picking and the unit pick rects / selection bars of the draw list (G3b).
Spec: docs/engine/ui-layout.md sections 7 and 9; synthetic tests always run, the map test needs the install."""

import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.view import Camera, DrawOptions, build_draw_list
from engine.view.pick import PickRect, pick_at, pick_in_rect
from engine.world import World

from helpers import GFS


def test_later_rect_wins_on_overlap():
    picks = [PickRect(1, 0, 0, 20, 20), PickRect(2, 10, 10, 30, 30)]
    assert pick_at(picks, 15, 15) == 2
    assert pick_at(picks, 5, 5) == 1


def test_point_outside_top_rect_picks_the_one_behind():
    picks = [PickRect(1, 0, 0, 50, 50), PickRect(2, 10, 10, 20, 20)]
    assert pick_at(picks, 40, 40) == 1
    assert pick_at(picks, 60, 60) is None


def test_box_edges_are_half_open():
    r = [PickRect(1, 10, 10, 20, 20)]
    assert pick_at(r, 9, 15) is None            # box x 8..10 touches x1 only
    assert pick_at(r, 10, 15) == 1              # box x 9..11 overlaps
    assert pick_at(r, 21, 15) is None            # box x 20..22 starts at x2: empty
    assert pick_at(r, 22, 15) is None
    assert pick_at(r, 20, 15) == 1


def test_area_threshold_10_vs_11():
    picks = [PickRect(1, 0, 0, 100, 100)]
    assert pick_in_rect(picks, (0, 0, 5, 2)) == []
    assert pick_in_rect(picks, (0, 0, 11, 1)) == [1]
    assert pick_in_rect(picks, (0, 0, 10, 1)) == []


def test_pick_in_rect_keeps_draw_order():
    picks = [PickRect(3, 0, 0, 10, 10), PickRect(1, 0, 0, 10, 10), PickRect(2, 50, 50, 60, 60)]
    assert pick_in_rect(picks, (0, 0, 20, 20)) == [3, 1]


# --- draw list -----------------------------------------------------------------------------

from test_engine_unit_draw import uassets, unit, world_with      # noqa: E402
from test_engine_objects import cam                              # noqa: E402

OPTS = DrawOptions(shadows=False)


def test_pick_rect_offsets_and_draw_order():
    from helpers import unit_type
    a, b = unit(1, 10, 10), unit(2, 10, 9)
    assets = uassets()
    t = assets.units[1].t
    t.SelectionX1, t.SelectionY1, t.SelectionX2, t.SelectionY2 = -10, -40, 10, 0
    dlist = build_draw_list(world_with(a, b), cam(), 0, assets, OPTS)
    assert [p.entity for p in dlist.picks] == [b.id, a.id]
    p = dlist.picks[1]
    assert (p.x2 - p.x1, p.y2 - p.y1) == (20, 40)
    px, py = 10 * 32 + 16 if False else None, None


def test_selection_bar_tiers_and_widths():
    u = unit(1, 10, 10)
    u.hp_max = 100
    assets = uassets()
    t = assets.units[1].t
    t.SelectionX1, t.SelectionY1, t.SelectionX2, t.SelectionY2 = 0, 0, 28, 30
    w = world_with(u)
    for hp, want in ((100, (20, 20, 0)), (49, (9, 20, 1)), (24, (4, 20, 2)), (1, (1, 20, 2))):
        u.hp = hp
        d = build_draw_list(w, cam(), 0, assets, OPTS, selection=(u.id,))
        bars = [i for i in d if i.kind == "bar"]
        assert len(bars) == 1 and bars[0].bar == want and (bars[0].w, bars[0].h) == (28, 4)
        assert bars[0].sy == d.picks[0].y1 - 2 and bars[0].sx == d.picks[0].x1
    assert not [i for i in build_draw_list(w, cam(), 0, assets, OPTS) if i.kind == "bar"]
    d = build_draw_list(w, cam(), 0, assets, DrawOptions(shadows=False, health_bars=True))
    assert len([i for i in d if i.kind == "bar"]) == 1
    assert d[-1].kind == "bar"


# --- real units ----------------------------------------------------------------------------

@pytest.mark.skipif(not GFS, reason="game files not present")
def test_map10_pick_rects_follow_the_unit_sprites():
    a = AssetCache(GFS)
    w = World.from_map(open_map("scenario/10.alm", GFS), a)
    u = next(iter(w.units.values()))
    cam_ = Camera(640, 480, w.width, w.height, u.x * 32 - 300, u.y * 32 - 220)
    mine = [x.id for x in w.units.values() if x.owner == u.owner][:1]
    d = build_draw_list(w, cam_, 0, a, DrawOptions(), selection=mine)
    assert d.picks
    sprites = []
    for i in d:
        if i.kind == "sprite" and i.sprite[0] == "unit" and i.blend != "half" and i.entity not in sprites:
            sprites.append(i.entity)
    onscreen = [p.entity for p in d.picks]
    assert [e for e in onscreen if e in sprites] == sprites
    assert all(p.x2 > p.x1 and p.y2 > p.y1 for p in d.picks)
    first = {i.entity: i for i in d if i.kind == "sprite" and i.sprite[0] == "unit"}
    for p in d.picks:
        s = first.get(p.entity)
        if s is not None:
            assert p.x1 < s.sx + s.w and s.sx < p.x2 and p.y1 < s.sy + s.h and s.sy < p.y2
    bars = [i for i in d if i.kind == "bar"]
    assert len(bars) == (1 if mine[0] in onscreen else 0)
