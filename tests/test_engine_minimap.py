"""Minimap: size rule, colours, geometry, camera rectangle, panel clicks (synthetic, always run)
and the install's maps and goldens (skipped without it).  Spec 2026-10-16-minimap-design.md."""

import json
import os

import numpy as np
import pytest

from allods2.common import campaign_maps
from allods2.graphics.palette import pack16, unpack16
from allods2.minimap import BORDER, load_color_table, minimap_rgb, minimap_size, scale_shift
from engine.ui import MinimapPanel
from engine.ui.layout import Layout
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


def px(r, g, b):
    """The 5-6-5 round trip every minimap pixel goes through (the exe's 16-bit surfaces)."""
    return tuple(int(x) for x in unpack16(pack16(np.array([r, g, b], np.uint8))))


def test_colour_rule_border_and_ignored_bits():
    cells = np.zeros((60, 60), np.uint16)
    cells[BORDER + 3, BORDER + 5] = (7 << 4) | 5 | 0x2000 | 0xc000      # strip id 7, row 5, dirt, fog
    img = minimap_rgb(cells, table())                                      # k = 1
    assert img.shape == (88, 88, 3)
    for dy in (0, 1):
        for dx in (0, 1):
            assert tuple(img[6 + dy, 10 + dx]) == px(7, 13 - 5, 7)
    assert tuple(img[0, 0]) == px(0, 13, 7)                                   # id 0, row 0
    assert tuple(img[6, 12]) == px(0, 13, 7)


def test_downscale_averages_2x2_cells():
    """k = -1 (`0x4abe65`-`0x4ac01d`): sum of `(word >> 2) & 0x39e7` of the 2 x 2 cells (floor(c / 4) per channel)."""
    cells = np.zeros((150, 150), np.uint16)
    cells[BORDER + 2, BORDER + 4] = 9 << 4                              # one cell of the block (x 2, y 1)
    t = table()
    t[13, 9] = (200, 120, 80)
    img = minimap_rgb(cells, t)
    assert img.shape == (67, 67, 3)
    w = pack16(np.array([[200, 120, 80], [0, 13, 7], [0, 13, 7], [0, 13, 7]], np.uint8))
    q = (w.astype(np.uint32) >> 2) & 0x39e7
    assert tuple(img[1, 2]) == tuple(int(x) for x in unpack16(np.uint16(q.sum())))
    assert tuple(img[1, 2]) != px(200, 120, 80)


def test_light_pass_scales_each_channel():
    """`0x4ac030`: L = 0x60 - sum(4 light bytes) // 4, channel = min(max, (c * L) >> 5) on the 5-6-5 fields."""
    cells = np.zeros((60, 60), np.uint16)
    t = table()
    t[13, 0] = (80, 100, 200)
    light = np.full((60, 60), 64, np.uint8)
    assert tuple(minimap_rgb(cells, t, light)[0, 0]) == px(80, 100, 200)             # L = 32: x1
    light[:] = 46                                                                    # flat daylight: L = 50
    w = int(pack16(np.array([80, 100, 200], np.uint8)))
    want = (min(31, (w >> 11) * 50 >> 5), min(63, ((w >> 5) & 63) * 50 >> 5), min(31, (w & 31) * 50 >> 5))
    assert tuple(minimap_rgb(cells, t, light)[0, 0]) == tuple(int(x) for x in unpack16(np.uint16(want[0] << 11 | want[1] << 5 | want[2])))
    light[:] = 0                                                                     # L = 96: clamps at the field maximum
    assert tuple(minimap_rgb(cells, t, light)[0, 0])[2] == 255
    cells2 = cells.copy()
    light = np.full((60, 60), 64, np.uint8)
    light[BORDER + 1, BORDER] = 0                                                    # one of the 4 bytes of the cell (8, 8) is 0 -> avg 48
    assert minimap_rgb(cells2, t, light)[0, 0][0] > minimap_rgb(cells2, t, np.full((60, 60), 64, np.uint8))[0, 0][0]


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
    panel = MinimapPanel.from_layout(mm.geometry, Layout.for_size(1024, 768))
    assert (panel.left, panel.top) == (864 + 72 - 64, 82 - 64)
    px, py = panel.left + 60, panel.top + 80                       # image (60, 80) = cell (38, 48)
    assert panel.press(cam, px, py)
    assert (cam.x, cam.y) == (38 * 32 - 160, 48 * 32 - 96)
    panel.drag(cam, panel.left + 62, panel.top + 80)               # one cell right
    assert (cam.x, cam.y) == (39 * 32 - 160, 48 * 32 - 96)
    panel.release()
    panel.drag(cam, panel.left + 10, panel.top + 10)
    assert cam.x == 39 * 32 - 160                                  # not dragging
    assert not panel.press(cam, 5, 700)                            # outside: not taken
    assert panel.press(cam, panel.left, panel.top)                 # image corner = cell (8, 8)
    assert (cam.x, cam.y) == (BORDER * 32 - 160, BORDER * 32 - 96)   # cell (8, 8) centred


def test_drag_outside_image_clamps():
    cam = Camera(320, 192, 80, 80, 0, 0)
    panel = MinimapPanel.from_layout(MinimapGeometry(80, 80), Layout.for_size(1024, 768))
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


def test_structure_dots():
    """`0x46213e`: a W x H rectangle at the structure's cell; k = -1 halves the position, not the size; the fog gate is the cell's four tiles."""
    from engine.view.minimap import draw_structure_dots
    from engine.world import MapObject, Player
    from allods2 import vision as v
    colors = np.arange(48, dtype=np.uint8).reshape(16, 3) + 100
    w = synthetic_world(80)                                                      # k = 1
    w.players[1] = Player(1, 3)
    w.objects[1] = MapObject(1, "structure", 5, 20, 30, owner=1)
    w.objects[2] = MapObject(2, "object", 5, 22, 32, owner=1)                    # map objects get none
    w.objects[3] = MapObject(3, "bridge", 33, 70, 70, owner=1, size=(4, 2))      # cropped at the image edge
    g = MinimapGeometry(80, 80)
    img = np.zeros((g.height, g.width, 3), np.uint8)
    draw_structure_dots(img, g, w, colors, {5: (3, 2)})
    mask = img.any(-1)
    assert mask[(30 - 8) * 2:(30 - 8) * 2 + 4, (20 - 8) * 2:(20 - 8) * 2 + 6].all() and mask.sum() == 6 * 4 + (128 - 124) * 4
    assert tuple(img[44, 24]) == tuple(colors[3])
    w.fog = v.new_fog(80, 80)                                                    # nothing seen: no dots
    img[:] = 0
    draw_structure_dots(img, g, w, colors, {5: (3, 2)})
    assert not img.any()
    v.reveal(w.fog, [(20, 30)])
    draw_structure_dots(img, g, w, colors, {5: (3, 2)})
    assert img.any(-1).sum() == 6 * 4
    g1 = MinimapGeometry(200, 200)                                               # k = -1
    w2 = synthetic_world(200)
    w2.players[1] = Player(1, 3)
    w2.objects[1] = MapObject(1, "structure", 5, 20, 30, owner=1)
    im = np.zeros((g1.height, g1.width, 3), np.uint8)
    draw_structure_dots(im, g1, w2, colors, {5: (3, 2)})
    ys, xs = np.nonzero(im.any(-1))
    assert (xs.min(), ys.min(), xs.max(), ys.max()) == ((20 - 8) >> 1, (30 - 8) >> 1, ((20 - 8) >> 1) + 2, ((30 - 8) >> 1) + 1)


# --- dot order, neutral colour, burnt ground, flying numbers in fog (open-question round, docs/engine/rendering.md 12) ---------------------

def test_object_map_walk_order_is_bucket_then_newest_first():
    """`view+0x9d0` is a CMap<word, obj*> with 17 buckets, hash `id >> 4`, new entries at the head of the chain."""
    from engine.view.objmap import bucket, walk_order
    ids = [0x6000, 0x6010, 0x6001, 0x6000 + 17 * 16, 0x6020]
    got = [i for i, _ in walk_order([(i, None) for i in ids])]
    assert [bucket(i) for i in got] == sorted(bucket(i) for i in ids)
    same = [i for i in got if bucket(i) == bucket(0x6000)]
    assert same == [0x6000 + 17 * 16, 0x6001, 0x6000]                   # newest registration first inside a bucket


def test_overlapping_dots_are_drawn_in_walk_order():
    from engine.view.minimap import exe_order
    a, b = (0x6000, "first"), (0x6001, "second")                         # one bucket: the later registration is walked first, so the earlier one overwrites it
    assert exe_order([a, b]) == [b, a]
    c = (0x6010, "other bucket")                                          # bucket of 0x6010 is one above: walked after
    assert exe_order([c, a, b])[-1] == c


def test_burnt_ground_is_set_once_and_bumps_the_cache_version():
    import numpy as np
    from engine.world import World
    w = World(np.zeros((12, 12), np.uint16), np.zeros((12, 12), np.int8))
    assert w.cells_version == 0
    w.scorch(5, 6)
    assert w.cells[6, 5] & 0x2000 and w.cells_version == 1
    w.scorch(5, 6)
    assert w.cells_version == 1                                           # never cleared, set once
    w.scorch(-1, 3)
    w.scorch(99, 3)                                                       # outside the map: ignored
    assert w.cells_version == 1


def test_neutral_structure_dot_takes_the_first_players_colour():
    """The structure builder defaults to the player with key 0 (section 5 record 1) when the owner matches no record (`0x4a4934`): owner 0 is drawn in the human's colour."""
    from engine.view.minimap import structure_dots
    from engine.world import MapObject, Player
    colors = np.arange(48, dtype=np.uint8).reshape(16, 3) + 100
    w = synthetic_world(80)
    w.players[1] = Player(1, 3)
    w.objects[1] = MapObject(1, "structure", 5, 20, 30, owner=0)
    (dot,) = structure_dots(MinimapGeometry(80, 80), w, colors, {5: (3, 2)})
    assert tuple(dot[2]) == tuple(colors[3])
