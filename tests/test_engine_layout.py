import pytest

from allods2.graphics.terrain import TILE
from engine.ui.layout import Layout, Rect
from engine.ui.scroll import ScrollInput
from engine.view.camera import Camera

MODES = [((640, 480), (15, 15)), ((800, 600), (20, 18)), ((1024, 768), (27, 24))]


def rects(lay):
    out = [lay.viewport, lay.minimap, lay.bar_panel.rect, lay.info_panel.rect, lay.bottom_bar]
    if lay.extra_panel:
        out.append(lay.extra_panel.rect)
    return out


def test_rect_basics():
    r = Rect(10, 20, 30, 40)
    assert (r.right, r.bottom) == (40, 60)
    assert r.contains(10, 20) and r.contains(39, 59) and not r.contains(40, 20) and not r.contains(10, 60)
    assert r.intersects(Rect(39, 59, 5, 5)) and not r.intersects(Rect(40, 20, 5, 5))
    assert r.translate(1, 2) == Rect(11, 22, 30, 40)


@pytest.mark.parametrize("size,cells", MODES)
def test_layout_geometry(size, cells):
    w, h = size
    lay = Layout.for_size(w, h)
    assert lay.size == size and lay.screen == Rect(0, 0, w, h)
    assert lay.viewport == Rect(0, 0, w - 160, h // 32 * 32)
    assert lay.cells == cells
    assert lay.minimap == Rect(w - 160, 0, 160, 158) and lay.crystal.rect == lay.minimap
    assert Layout.MINIMAP_CENTER == (72, 82)
    for r in rects(lay) + [s.rect for s in lay.strips]:
        assert lay.screen.x <= r.x and r.right <= w and r.bottom <= h
    column = [lay.minimap, lay.bar_panel.rect, lay.info_panel.rect] + ([lay.extra_panel.rect] if lay.extra_panel else [])
    for i, a in enumerate(column):
        assert a.x == w - 160 and a.w == 160
        for b in column[i + 1:]:
            assert not a.intersects(b)
        assert not a.intersects(lay.viewport)
    assert [(p.rect.y, p.rect.h) for p in (lay.crystal, lay.bar_panel, lay.info_panel)] == [(0, 158), (158, 80), (238, 242)]
    assert lay.bottom_bar == Rect(0, h - 90, w - 160, 90)


@pytest.mark.parametrize("size,cells", MODES)
def test_strips_adjoin_viewport(size, cells):
    w, h = size
    lay = Layout.for_size(w, h)
    for s in lay.strips:
        assert s.rect.x == w - 176 and s.rect.w == 16 and s.rect.right == lay.viewport.right
    a, b, c = lay.strips[:3]
    assert (a.rect.y, a.rect.h, b.rect.y, b.rect.h, c.rect.y, c.rect.h) == (0, 158, 158, 80, 238, 242)
    assert a.graphics == ("graphics/interface/CrystalL.bmp",)
    assert b.graphics == ("graphics/interface/HeadsL.bmp", "graphics/interface/CommandBarL.bmp")
    assert c.graphics[0] == "graphics/interface/HumanBackL.bmp"
    assert lay.crystal.graphics == ("graphics/interface/CrystalR.bmp",)


def test_extra_panels():
    assert Layout.for_size(640, 480).extra_panel is None and len(Layout.for_size(640, 480).strips) == 3
    l8, l10 = Layout.for_size(800, 600), Layout.for_size(1024, 768)
    assert l8.extra_panel.rect == Rect(640, 480, 160, 96) and l8.strips[3].rect == Rect(624, 480, 16, 96)
    assert l10.extra_panel.rect == Rect(864, 480, 160, 46) and l10.strips[3].rect == Rect(848, 480, 16, 46)
    assert l8.extra_panel.graphics == ("graphics/interface/extra800r.bmp",)
    assert l10.strips[3].graphics == ("graphics/interface/extra1024l.bmp",)


@pytest.mark.parametrize("size", [(320, 200), (1280, 720), (640, 481), (480, 640)])
def test_unknown_size_raises(size):
    with pytest.raises(ValueError):
        Layout.for_size(*size)


def test_bar_graphics_rule():
    lay = Layout.for_size(640, 480)
    assert lay.bar_graphics("none") == ("graphics/interface/HeadsL.bmp", "graphics/interface/HeadsR.bmp")
    assert lay.bar_graphics("foreign") == lay.bar_graphics("none")
    assert lay.bar_graphics("own") == ("graphics/interface/CommandBarL.bmp", "graphics/interface/CommandBarR.bmp")


@pytest.mark.parametrize("pos,expect", [
    ((0, 50), (-1, 0)), ((1, 50), (0, 0)), ((637, 50), (0, 0)), ((638, 50), (1, 0)), ((639, 50), (1, 0)),
    ((50, 0), (0, -1)), ((50, 1), (0, 0)), ((50, 477), (0, 0)), ((50, 478), (0, 1)), ((50, 479), (0, 1)),
    ((0, 0), (-1, -1)), ((639, 479), (1, 1)), ((500, 100), (0, 0)),
])
def test_edge_rule(pos, expect):
    assert ScrollInput().direction(set(), pos, 640, 480) == expect


def test_no_edge_scroll_without_mouse_and_keys():
    s = ScrollInput()
    assert s.direction(set(), None, 640, 480) == (0, 0)
    assert s.direction({"left", "up"}, None, 640, 480) == (-1, -1)
    assert s.direction({"left", "right"}, None, 640, 480) == (0, 0)
    assert s.direction({"left"}, (0, 50), 640, 480) == (-1, 0)


def test_one_tile_per_period_with_carry():
    s = ScrollInput(period_ms=62)
    c = Camera(160, 160, 40, 40, 320, 320)
    size = (640, 480)
    s.update(c, 61, set(), (639, 0), size)
    assert (c.x, c.y) == (320, 320)
    s.update(c, 1, set(), (639, 0), size)
    assert (c.x, c.y) == (320 + TILE, 320 - TILE)
    s.update(c, 62 * 3 + 30, set(), (639, 0), size)
    assert (c.x, c.y) == (320 + 4 * TILE, 320 - 4 * TILE)
    s.update(c, 32, set(), (639, 0), size)
    assert c.x == 320 + 5 * TILE
    s.update(c, 500, set(), None, size)
    assert c.x == 320 + 5 * TILE


def test_keys_move_camera():
    s = ScrollInput(period_ms=62)
    c = Camera(160, 160, 40, 40, 320, 320)
    s.update(c, 62, {"down", "left"}, None, (640, 480))
    assert (c.x, c.y) == (320 - TILE, 320 + TILE)


def test_border_clamp():
    c = Camera(160, 160, 40, 40, 0, 0, border=256)
    assert (c.x, c.y) == (256, 256)
    c.move_to(10 ** 6, 10 ** 6)
    assert (c.x, c.y) == (40 * TILE - 256 - 160,) * 2
    s = ScrollInput()
    c.move_to(256, 256)
    s.update(c, 62 * 5, {"left", "up"}, None, (640, 480))
    assert (c.x, c.y) == (256, 256)


def test_border_falls_back_when_range_empty():
    c = Camera(160, 160, 10, 10, 0, 0, border=256)
    assert (c.min_x, c.max_x) == (0, 160)
