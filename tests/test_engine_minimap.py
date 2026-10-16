"""Minimap: size rule, colours, geometry, camera rectangle, panel clicks (synthetic, always run)
and the install's maps and goldens (skipped without it).  Spec 2026-10-16-minimap-design.md."""

import json
import os

import numpy as np
import pytest

from allods2.common import campaign_maps
from allods2.minimap import BORDER, load_color_table, minimap_rgb, minimap_size, scale_shift
from engine.ui import MinimapPanel
from engine.view import Camera, Minimap, MinimapGeometry, draw_camera_rect
from engine.world import World

from helpers import GFS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def table():
    t = np.zeros((14, 52, 3), np.uint8)
    t[..., 0] = np.arange(52)[None, :]
    t[..., 1] = np.arange(14)[:, None]
    t[..., 2] = 7
    return t


@pytest.mark.parametrize("m,k", [(48, 2), (49, 1), (80, 1), (81, 0), (144, 0), (145, -1), (256, -1)])
def test_scale_thresholds(m, k):
    assert scale_shift(m, 20) == k == scale_shift(20, m)


def test_size_rule():
    assert minimap_size(80, 80) == (128, 128) == minimap_size(144, 144)
    assert minimap_size(48, 48) == (128, 128)
    assert minimap_size(200, 200) == (92, 92)
    assert minimap_size(100, 90) == (84, 74)
    for w, h in ((48, 40), (64, 64), (90, 100), (160, 150), (256, 256)):
        k = scale_shift(w, h)
        assert minimap_rgb(np.zeros((h, w), np.uint16), table()).shape[:2][::-1] == minimap_size(w, h)


def test_colour_rule_border_and_ignored_bits():
    cells = np.zeros((60, 60), np.uint16)
    cells[BORDER + 3, BORDER + 5] = (7 << 4) | 5 | 0x2000 | 0xc000      # strip id 7, row 5, dirt, fog
    img = minimap_rgb(cells, table())                                      # k = 1
    assert img.shape == (88, 88, 3)
    for dy in (0, 1):
        for dx in (0, 1):
            assert tuple(img[6 + dy, 10 + dx]) == (7, 13 - 5, 7)
    assert tuple(img[0, 0]) == (0, 13, 7)                                   # id 0, row 0
    assert tuple(img[6, 12]) == (0, 13, 7)


def test_downscale_takes_every_second_pixel():
    cells = np.zeros((150, 150), np.uint16)
    cells[BORDER + 2, BORDER + 4] = 9 << 4
    img = minimap_rgb(cells, table())
    assert img.shape == (67, 67, 3) and tuple(img[1, 2]) == (9, 13, 7)


@pytest.mark.parametrize("w", [48, 80, 144, 200])
def test_pixel_cell_round_trip(w):
    g = MinimapGeometry(w, w)
    for col, row in ((BORDER, BORDER), (BORDER + 5, w - BORDER - 3), (w // 2, w // 2)):
        px, py = g.cell_to_pixel(col, row)
        assert g.pixel_to_cell(px, py) == (col, row)
    assert g.pixel_to_cell(0, 0) == (BORDER, BORDER)
    assert g.pixel_to_cell(g.width, g.height) == (w - BORDER, w - BORDER)


def test_camera_rect_and_overlay():
    g = MinimapGeometry(80, 80)                                    # s = 2
    cam = Camera(320, 192, 80, 80, 8 * 32, 8 * 32)                 # starts at cell (8, 8)
    assert g.camera_rect(cam) == (0, 0, 19, 11)                    # 10 x 6 cells * 2 - 1
    cam.move_to(66 * 32, 66 * 32)                                  # partly past the image: clipped
    assert g.camera_rect(cam) == (116, 116, 127, 127)
    cam.move_to(1e9, 1e9)                                          # wholly in the border
    assert g.camera_rect(cam) is None
    cam.move_to(4 * 32, 4 * 32)                                    # half in the border: clipped
    assert g.camera_rect(cam) == (0, 0, 11, 3)
    img = draw_camera_rect(np.zeros((128, 128, 3), np.uint8), (2, 3, 9, 7))
    assert img[3, 2:10].all() and img[7, 2:10].all() and img[3:8, 2].all() and img[3:8, 9].all()
    assert not img[4:7, 3:9].any() and not img[0:3].any()


def synthetic_world(n=80):
    return World(np.zeros((n, n), np.uint16), np.zeros((n, n), np.int8))


def test_minimap_is_built_once_and_invalidate_rebuilds():
    mm = Minimap(synthetic_world(), table())
    cam = Camera(320, 192, 80, 80, 300, 300)
    a = mm.image(cam)
    mm.image(cam)
    assert mm.builds == 1 and a.shape == (128, 128, 3) and not mm.base.flags.writeable
    mm.invalidate()
    mm.image(cam)
    assert mm.builds == 2


def test_click_centres_camera_on_cell():
    world = synthetic_world()
    mm = Minimap(world, table())
    cam = Camera(320, 192, 80, 80, 0, 0)
    panel = MinimapPanel.at_top_right(mm.geometry, 1024)
    assert (panel.left, panel.top) == (1024 - 8 - 128, 8)
    px, py = panel.left + 60, panel.top + 80                       # image (60, 80) = cell (38, 48)
    assert panel.press(cam, px, py)
    assert (cam.x, cam.y) == (38 * 32 - 160, 48 * 32 - 96)
    panel.drag(cam, panel.left + 62, panel.top + 80)               # one cell right
    assert (cam.x, cam.y) == (39 * 32 - 160, 48 * 32 - 96)
    panel.release()
    panel.drag(cam, panel.left + 10, panel.top + 10)
    assert cam.x == 39 * 32 - 160                                  # not dragging
    assert not panel.press(cam, 5, 500)                            # outside: not taken
    assert panel.press(cam, panel.left, panel.top)                 # image corner = cell (8, 8)
    assert (cam.x, cam.y) == (BORDER * 32 - 160, BORDER * 32 - 96)   # cell (8, 8) centred


def test_drag_outside_image_clamps():
    cam = Camera(320, 192, 80, 80, 0, 0)
    panel = MinimapPanel.at_top_right(MinimapGeometry(80, 80), 1024)
    panel.press(cam, panel.left + 64, panel.top + 64)
    panel.drag(cam, 5000, 5000)
    assert (cam.x, cam.y) == (cam.max_x, cam.max_y)


# --- install ---------------------------------------------------------------------------------------

MAPS = campaign_maps(GFS) if GFS else []
needs_install = pytest.mark.skipif(not MAPS, reason="game files not present")


@needs_install
def test_size_rule_on_every_campaign_map():
    from allods2.formats import Map
    for path in MAPS:
        m = Map.load(path, GFS)
        img = minimap_rgb(m.runtime_terrain(), load_color_table(GFS))
        assert (img.shape[1], img.shape[0]) == minimap_size(m.width, m.height), path
        assert img.shape[1] == (128 if m.width in (80, 144) else 120), (path, m.width)


@needs_install
def test_table_covers_every_cell_value():
    from allods2.formats import Map
    for path in MAPS:
        m = Map.load(path, GFS)      # rows 14, 15 occur only in the cut-off border (map 74)
        v = m.runtime_terrain()[BORDER:m.height - BORDER, BORDER:m.width - BORDER] & 0x1fff
        assert (v >> 4).max() < 52 and (v & 15).max() < 14, path


@needs_install
def test_golden_minimaps():
    import importlib.util
    spec = importlib.util.spec_from_file_location("update_golden", os.path.join(ROOT, "tools", "update_golden.py"))
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    gold = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["minimaps"]
    assert set(gold) == {"10", "20", "52"}
    assert tool.minimap_hashes(os.environ.get("ALLODS2_INSTALL") or None) == gold, \
        "minimap changed; if intended run tools/update_golden.py"
