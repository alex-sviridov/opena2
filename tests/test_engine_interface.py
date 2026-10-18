"""Interface frame, bars, cursor drawing, full-window screenshot (G3b test 7).

Headless (SDL dummy driver).  The golden is tied to the pinned pygame-ce version: the info panel
text uses the game's fonts (engine/backend_pygame/text.py).
"""

import importlib.util
import json
import os

import numpy as np
import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
pygame = pytest.importorskip("pygame")

from engine.backend_pygame import render
from engine.backend_pygame.cursor import CursorSprites, draw_cursor
from engine.backend_pygame.interface import Interface, InterfaceArt, selection_state
from engine.backend_pygame.text import draw_text
from engine.ui import CursorState, Layout
from engine.view import DrawItem
from engine.world import Player, Unit, World

from helpers import GFS, needs_graphics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class FakeArt:
    """Every panel path is a flat colour of its panel size."""
    def __init__(self, layout):
        self.sizes = {}
        for p in list(layout.strips) + [layout.crystal, layout.bar_panel, layout.info_panel, layout.extra_panel]:
            if p:
                for g in p.graphics:
                    self.sizes[g] = (p.rect.w, p.rect.h)

    def get(self, path):
        if path not in self.sizes:
            return None
        s = pygame.Surface(self.sizes[path])
        s.fill((10 + len(path) % 200, 20, 30))
        return s


def bar_item(x1, y, w, fill, track, tier):
    return DrawItem("bar", 1, None, 0, x1, y - 2, w, 4, bar=(fill, track, tier))


def test_bar_rows_fill_and_tiers():
    s = pygame.Surface((60, 20))
    s.fill((0, 0, 0))
    render.draw_bar(s, bar_item(10, 8, 40, 12, 32, 0))
    g = lambda x, y: tuple(s.get_at((x, y)))[:3]          # noqa: E731
    assert [g(14, 6 + r) for r in range(4)] == [(0, 128, 0), (0, 255, 0), (0, 192, 0), (0, 128, 0)]
    assert g(14 + 12, 7) == (0x80,) * 3 and g(14 + 11, 7) == (0, 255, 0)           # fill ends at 12 px
    assert [g(40, 6 + r) for r in range(4)] == [(0x40,) * 3, (0x80,) * 3, (0x60,) * 3, (0x40,) * 3]
    assert g(13, 7) == (0, 0, 0) and g(46, 7) == (0, 0, 0)                          # caps' columns untouched
    for tier, bright in ((1, (255, 255, 0)), (2, (255, 0, 0))):
        render.draw_bar(s, bar_item(10, 8, 40, 32, 32, tier))
        assert g(14, 7) == bright


def test_bar_caps_use_ball():
    s = pygame.Surface((60, 20))
    ball = pygame.Surface((4, 4))
    ball.fill((1, 2, 3))
    render.draw_bar(s, bar_item(10, 8, 40, 1, 32, 0), ball)
    assert tuple(s.get_at((10, 6)))[:3] == (1, 2, 3) and tuple(s.get_at((49, 9)))[:3] == (1, 2, 3)


@pytest.mark.parametrize("size", Layout.SIZES)
def test_frame_black_window_panels_at_layout_rects(size):
    lay = Layout.for_size(*size)
    win = pygame.Surface(size)
    ui = Interface(lay, FakeArt(lay))
    w = World(np.zeros((40, 40), np.uint16), np.zeros((40, 40), np.int8))
    w.players[1] = Player(1, 0, "me", human=True)
    from engine.view import Camera
    ui.draw(win, render.Caches(None), [], [], Camera(lay.viewport.w, lay.viewport.h, 40, 40), w, 1)
    at = lambda x, y: tuple(win.get_at((x, y)))[:3]     # noqa: E731
    assert at(5, 5) == (0, 0, 0)                          # empty viewport = black
    for p in (lay.strip_a, lay.crystal, lay.info_panel):
        assert at(p.rect.x + 1, p.rect.y + 1) != (0, 0, 0)
        assert at(p.rect.x + 1, p.rect.y + 1) != (0, 0, 0)
    if size[1] % 32:                                    # rows under the viewport stay black (800x600: 576..600)
        assert at(5, lay.viewport.bottom + 1) == (0, 0, 0)


def test_bar_panel_choice_follows_selection():
    w = World(np.zeros((40, 40), np.uint16), np.zeros((40, 40), np.int8))
    w.players[1], w.players[2] = Player(1, 0, "a"), Player(2, 1, "b")
    w.add_unit(Unit(1, 1, 1, 5, 5, hp=1, hp_max=1))
    w.add_unit(Unit(2, 1, 2, 6, 5, hp=1, hp_max=1))
    assert selection_state(w, 1) == "none"
    w.players[1].selection = (1,)
    assert selection_state(w, 1) == "own"
    w.players[1].selection = (2,)
    assert selection_state(w, 1) == "foreign"


def test_draw_text_alignment():
    s = pygame.Surface((100, 30))
    w = draw_text(s, "HP 10/10", 50, 5, (255, 255, 255), "center")
    cols = np.nonzero(pygame.surfarray.array3d(s).sum(axis=(1, 2)))[0]
    assert cols.min() >= 50 - w // 2 and cols.max() < 50 + w - w // 2


@needs_graphics
def test_draw_text_uses_game_fonts_for_both_languages_and_wraps():
    from allods2.text import font_bytes
    from engine.backend_pygame.text import draw_text, game_font, render_text
    assert game_font(2) is not None
    for text in ("Attack the orcs", "Атака на орков"):
        s = pygame.Surface((200, 30))
        w = draw_text(s, text, 4, 4, "label")
        assert w == game_font(2).measure(font_bytes(text)) + 3
        assert pygame.surfarray.array3d(s).any()
    one = render_text("one two three four", font=2, width=60, wrap=True)
    assert one.get_height() > render_text("one", font=2).get_height()      # wrapped to several lines
    assert one.get_width() == 60 + 3                                         # block width + padding + shadow


@needs_graphics
def test_cursor_frames_and_hotspot():
    pygame.display.init()
    pygame.display.set_mode((64, 64))
    cs = CursorSprites(GFS)
    surf, hx, hy = cs.surface_at("default", 0)
    assert (hx, hy) == (4, 4) and surf.get_width() > 0
    win = pygame.Surface((64, 64))
    draw_cursor(win, cs, CursorState.DEFAULT, (30, 30), 0)
    assert pygame.surfarray.array3d(win).any()
    win.fill((0, 0, 0))
    draw_cursor(win, cs, CursorState.DEFAULT, None, 0)
    assert not pygame.surfarray.array3d(win).any()


@needs_graphics
@pytest.mark.parametrize("size", Layout.SIZES)
def test_cli_interface_screenshot(tmp_path, monkeypatch, size):
    from PIL import Image
    from engine.__main__ import main
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    dest = tmp_path / "i.png"
    assert main(["screenshot", "10", "1808", "912", str(dest), "--interface", "--select", "32",
                 "--size", "%dx%d" % size]) == 0
    assert Image.open(dest).size == size


@needs_graphics
def test_cli_rejects_other_sizes(tmp_path, monkeypatch):
    from engine.__main__ import main
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    with pytest.raises(SystemExit):
        main(["screenshot", "10", "0", "0", str(tmp_path / "x.png"), "--interface", "--size", "700x500"])


@needs_graphics
def test_interface_golden():
    spec = importlib.util.spec_from_file_location("update_golden", os.path.join(ROOT, "tools", "update_golden.py"))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    gold = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["interface"]
    assert tool.interface_hash(GFS) == gold, "interface changed (or pygame-ce font); run tools/update_golden.py"


@needs_graphics
def test_main_loop_click_selects_unit_and_right_click_clears():
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.backend_pygame import window
    from engine.view import Camera, DrawOptions, TerrainView, build_draw_list
    assets = AssetCache(GFS)
    w = World.from_map(open_map("10", GFS), assets)
    u = next(u for u in w.units.values() if u.human)
    lay = Layout.for_size(640, 480)
    v = lay.viewport
    cam = Camera(v.w, v.h, w.width, w.height, u.x * 32 - v.w // 2, u.y * 32 - v.h // 2, border=256)
    pick = next(r for r in build_draw_list(w, cam, 0, assets, DrawOptions()).picks if r.entity == u.id)
    x, y = (pick.x1 + pick.x2) // 2, (pick.y1 + pick.y2) // 2
    tv = TerrainView(w, assets.tileset())
    window.ensure_display(*lay.size)
    ev = pygame.event.Event
    pygame.event.post(ev(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=1))
    pygame.event.post(ev(pygame.MOUSEBUTTONUP, pos=(x, y), button=1))
    window.run(w, tv, cam, lay, assets=assets, max_frames=8)
    assert w.players[1].selection == (u.id,)
    window.ensure_display(*lay.size)
    pygame.event.post(ev(pygame.MOUSEBUTTONDOWN, pos=(x, y), button=3))
    pygame.event.post(ev(pygame.MOUSEBUTTONUP, pos=(x, y), button=3))
    window.run(w, tv, cam, lay, assets=assets, max_frames=8)
    assert w.players[1].selection == ()
