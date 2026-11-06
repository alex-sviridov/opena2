"""Object drawing (spec 2026-10-16-object-drawing-design.md, docs/engine/rendering.md):
the draw list (synthetic, always runs), the backend blends, and pixel parity with the
E4 reference (`map render --relief --layers terrain,objects,structures`) on the install."""

import functools
import importlib.util
import json
import math
import os

import numpy as np
import pytest

from allods2.anim import ObjectSet
from allods2.anim.structures import BridgeSet, StructureSet
from allods2.graphics import lighting as lt
from engine.ui import DebugFlags
from engine.view import (Camera, DrawOptions, build_draw_list, in_window, view_window)
from engine.view import drawlist as dl
from engine.world import FLAG_DESTROYED, MapObject, World

from helpers import GFS, needs_graphics, sprite_file

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W = H = 40


class FakeAssets:
    """AssetCache stand-in: sets by id, built from in-memory sprite files."""

    def __init__(self, objects=None, structures=None):
        self.objects, self.structures = objects or {}, structures or {}

    def object_set(self, oid):
        return self.objects.get(oid)

    def projectile_set(self, pid):
        return None

    def structure_set(self, tid, size=None):
        s = self.structures.get(tid)
        if isinstance(s, BridgeSet) and size:
            s.w, s.h = size
        return s


def orec(**kw):
    rec = dict(ID=5, file="tree", Index=0, Width=4, Height=1, CenterX=2, CenterY=1,
               seq=[], DeadObject=-1)
    rec.update(kw)
    return rec


def srec(**kw):
    rec = dict(ID=100, File="x\\house", TileWidth=2, TileHeight=1, FullHeight=2, Phases=1,
               seq=[], mask="", Indestructible=0, ShadowY=40)
    rec.update(kw)
    return rec


def flat_world(objs=()):
    w = World(np.zeros((H, W), np.uint16), np.zeros((H, W), np.int8))
    for o in objs:
        w.add_object(o)
    return w


def obj(n, x, y, type_id=5):
    return MapObject(0x10000 + n, "object", type_id, x, y)


def struct(uid, x, y, type_id=100, fp=((0, 0, True),), **kw):
    return MapObject(0x6000 + uid, "structure", type_id, x, y, uid=uid, footprint=fp, hp=10,
                     hp_max=10, **kw)


def cam(x=0, y=0, w=1280, h=800):
    return Camera(w, h, W, H, x, y)


def assets(**kw):
    return FakeAssets(objects={5: ObjectSet(orec(), sprites={"main": sprite_file(4), "main_b": sprite_file(4)})},
                      structures={100: StructureSet(srec(**kw), sprites={"main": sprite_file(8), "main_b": sprite_file(8)}),
                                  101: StructureSet(srec(ID=101, Flat=1), sprites={"main": sprite_file(8)})})


PLAIN = DrawOptions(shadows=False, lit=False, smoothing=False)
E4 = DrawOptions(shadows=False, lit=False, units=False)    # parity with E4: smoothing stays on
E5 = DrawOptions(shadows=False, lit=False)                  # parity with E5: units and piles too


def sprites_of(items, kind="sprite"):
    return [i for i in items if i.kind == kind]


# --- order -----------------------------------------------------------------------

def test_rows_top_to_bottom_columns_right_to_left():
    w = flat_world([obj(1, 10, 12), obj(2, 12, 10), obj(3, 11, 10), obj(4, 5, 11)])
    items = build_draw_list(w, cam(), 0, assets(), PLAIN)
    got = [(i.depth[1], -i.depth[2]) for i in items]
    assert got == [(10, 12), (10, 11), (11, 5), (12, 10)]


def test_items_are_sorted_by_depth_and_deterministic():
    w = flat_world([obj(n, 3 + n % 7, 4 + n % 5) for n in range(30)] + [struct(1, 8, 8)])
    a = build_draw_list(w, cam(), 0, assets(), DrawOptions())
    b = build_draw_list(w, cam(), 0, assets(), DrawOptions())
    assert a == b and [i.depth for i in a] == sorted(i.depth for i in a)


def test_build_never_mutates_the_world():
    w = flat_world([obj(1, 5, 5), struct(1, 8, 8)])
    before = w.dump_hash()
    build_draw_list(w, cam(), 3, assets(), DrawOptions(), DebugFlags(True, True, True))
    assert w.dump_hash() == before and w.tick == 0


def test_flat_structure_is_under_everything_and_shadows_come_first():
    # flat structure at row 12, a tree at row 5, a normal structure at row 6
    w = flat_world([struct(1, 8, 12, 101), obj(1, 8, 5), struct(2, 8, 6)])
    items = build_draw_list(w, cam(), 0, assets(), DrawOptions(smoothing=False))
    kinds = [(i.depth[0], i.kind, i.sprite[0]) for i in items]
    passes = [k[0] for k in kinds]
    assert passes == sorted(passes)
    assert passes[0] == dl.PASS_SHADOW and kinds[0][1] == "shadow"          # structure shadows, P0
    flat = [i for i in items if i.depth[0] == dl.PASS_FLAT]
    assert len(flat) and all(i.entity == 0x6001 for i in flat)
    assert all(i.depth[0] == dl.PASS_SHADOW for i in items if i.kind == "shadow" and i.sprite[0] == "structure")
    p3 = [i for i in items if i.depth[0] == dl.PASS_CELL]
    assert p3[0].entity != 0x6001 and max(i.depth[1] for i in flat) == 12
    assert p3[-1].depth[1] > p3[0].depth[1] - 1 and any(i.depth[1] == 12 for i in flat)


def test_structure_slice_precedes_object_in_the_same_cell_and_parts_go_bottom_up():
    # footprint (8, 8): W=2 TH=1 FH=2 -> cells (8,8) and (9,8); pieces bottom-up per cell
    w = flat_world([struct(1, 8, 8), obj(1, 8, 8)])
    items = build_draw_list(w, cam(), 0, assets(), PLAIN)
    cell = [i for i in items if (i.depth[1], -i.depth[2]) == (8, 8)]
    assert [i.sprite[0] for i in cell] == ["structure", "structure", "object"]
    assert [i.frame for i in cell[:2]] == [2, 0]                 # picture row 1 (bottom) first
    assert cell[0].sy > cell[1].sy                               # and drawn lower
    assert [i.depth[5] for i in cell[:2]] == [0, 1]
    cols = [-i.depth[2] for i in items if i.sprite[0] == "structure"]
    assert cols == [9, 9, 8, 8]                                  # right to left


def test_object_sub_order_shadow_main_shadow_b_sprite_overlay():
    w = flat_world([obj(1, 10, 10)])
    items = build_draw_list(w, cam(), 0, assets(), DrawOptions())
    assert [(i.kind, i.sprite[2], i.blend) for i in items] == [
        ("shadow", "main", "shadow"), ("shadow", "main_b", "shadow"),
        ("sprite", "main", "opaque"), ("sprite", "main_b", "half")]
    assert [i.shadow_level for i in items[:2]] == [4, 2]            # 0x6226cc, 0x6226d0 by day
    assert items[0].shadow and not items[2].shadow


def test_structure_pieces_main_then_b_and_two_shadow_levels():
    w = flat_world([struct(1, 8, 8)])
    items = build_draw_list(w, cam(), 0, assets(), DrawOptions())
    sh = [(i.frame, i.sprite[2], i.shadow_level) for i in items if i.kind == "shadow"]
    assert sh[:4] == [(3, "main", 4), (3, "main_b", 2), (1, "main", 4), (1, "main_b", 2)]   # column 9 first
    assert sh[4:6] == [(2, "main", 4), (2, "main_b", 2)]
    sp = [(i.frame, i.sprite[2], i.blend) for i in items if i.kind == "sprite" and i.frame == 2]
    assert sp[:2] == [(2, "main", "opaque"), (2, "main_b", "half")]


def test_options_switch_layers_off():
    w = flat_world([obj(1, 10, 10), struct(1, 3, 3)])
    a = assets()
    n = lambda **kw: build_draw_list(w, cam(), 0, a, DrawOptions(**kw))
    assert not [i for i in n(shadows=False) if i.kind == "shadow"]
    assert not [i for i in n(smoothing=False) if i.blend == "half" or i.shadow_level == 2]
    assert n(objects=False) == []
    assert {i.light_row for i in n(lit=False) if i.kind == "sprite"} == {None}
    day = lt.daylight(0, False)
    assert {i.light_row for i in n() if i.kind == "sprite"} == {day.ambient >> 2}
    assert all(i.light_row is None and i.remap is None for i in n() if i.kind == "shadow")
    assert all(i.remap is None for i in n())


def test_missing_sprites_are_counted_and_draw_nothing():
    w = flat_world([obj(1, 10, 10, type_id=99), obj(2, 11, 10), struct(1, 3, 3, 77)])
    items = build_draw_list(w, cam(), 0, assets(), PLAIN)
    assert items.missing == 2 and [i.entity for i in items] == [0x10002]
    a = FakeAssets(objects={5: ObjectSet(orec(Index=40), sprites={"main": sprite_file(4)})})
    assert build_draw_list(flat_world([obj(1, 10, 10)]), cam(), 0, a, PLAIN).missing == 1


# --- window and culling ---------------------------------------------------------------

def test_window_is_minus3_to_plus2_and_minus3_to_plus6():
    win = (10, 10, 20, 15)
    assert in_window(win, 7, 7) and not in_window(win, 6, 7) and not in_window(win, 7, 6)
    assert in_window(win, 10 + 20 + 2, 10 + 15 + 6) and not in_window(win, 10 + 20 + 3, 20)
    assert not in_window(win, 15, 10 + 15 + 7)
    c = Camera(100, 70, W, H, 70, 100)
    assert view_window(c) == (2, 3, 4, 3)          # ceil(170/32) = 6 - 2, ceil(170/32) = 6 - 3


def test_objects_outside_the_cell_window_are_not_drawn_and_counted():
    big = FakeAssets(objects={5: ObjectSet(orec(Width=4, Height=1), sprites={"main": sprite_file(4)})})
    c = Camera(64, 64, W, H, 320, 320)                        # window cells 10..11, 10..11
    inside = [obj(1, 10 - 3, 10), obj(2, 10 + 2 + 2, 10), obj(3, 10, 10 + 2 + 6)]
    outside = [obj(4, 10 - 4, 10), obj(5, 10 + 2 + 3, 10), obj(6, 10, 10 - 4), obj(7, 10, 10 + 2 + 7)]
    items = build_draw_list(flat_world(inside + outside), c, 0, big, PLAIN)
    assert {i.entity for i in items} <= {0x10001, 0x10002, 0x10003}        # window gate
    assert items.culled == 4


def test_extent_culling_keeps_overlapping_items_and_drops_the_rest():
    w = flat_world([obj(1, 10, 10), obj(2, 20, 20)])
    c = Camera(100, 100, W, H, 10 * 32 - 20, 10 * 32 - 20)
    items = build_draw_list(w, c, 0, assets(), PLAIN)
    assert [i.entity for i in items] == [0x10001]
    it = items[0]
    assert (it.sx, it.sy) == (10 * 32 + 16 - 2 - c.ix, 10 * 32 + 16 - 1 - c.iy)     # anchor (cell centre) - hotspot


def test_placement_with_relief_uses_cell_relief_and_ground_height():
    h = np.zeros((H, W), np.int8)
    h[10:12, 10:12] = 40
    w = World(np.zeros((H, W), np.uint16), h)
    w.add_object(obj(1, 10, 10))
    items = build_draw_list(w, cam(), 0, assets(), PLAIN)
    assert items[0].sy == 10 * 32 + 16 - 1 - int(np.mean([h[10, 10], h[10, 11], h[11, 10], h[11, 11]]))
    w.add_object(struct(1, 10, 10))
    st = [i for i in build_draw_list(w, cam(), 0, assets(), PLAIN) if i.sprite[0] == "structure"]
    from allods2.formats import objects as fobj
    g = fobj.ground_height(h, 10 * 256 + 128, 10 * 256 + 128, 2, 1)
    assert {i.sy for i in st} == {10 * 32 - g, 10 * 32 - g - 32}


def test_destroyed_structure_uses_the_destroyed_pieces():
    a = FakeAssets(structures={100: StructureSet(srec(), sprites={"main": sprite_file(8)})})
    w = flat_world([struct(1, 8, 8, flags=FLAG_DESTROYED), struct(2, 20, 8)])
    items = build_draw_list(w, cam(), 0, a, PLAIN)
    dead = sorted(i.frame for i in items if i.entity == 0x6001)
    ok = sorted(i.frame for i in items if i.entity == 0x6002)
    assert ok == [0, 1, 2, 3] and dead == [4, 5, 6, 7]           # count - W*FH + cell
    ind = FakeAssets(structures={100: StructureSet(srec(Indestructible=1), sprites={"main": sprite_file(8)})})
    assert sorted(i.frame for i in build_draw_list(w, cam(), 0, ind, PLAIN) if i.entity == 0x6001) == [0, 1, 2, 3]


def test_bridge_has_no_shadow_and_uses_its_size():
    rec = srec(ID=0x21, Flat=1, VariableSize=1, TileWidth=0, TileHeight=0, FullHeight=0)
    a = FakeAssets(structures={0x21: BridgeSet(rec, 3, 2, sprites={"main": sprite_file(9), "main_b": sprite_file(9)})})
    b = MapObject(0x6001, "bridge", 0x21, 10, 10, uid=1, size=(3, 2))
    w = flat_world([b])
    items = build_draw_list(w, cam(), 0, a, DrawOptions())
    assert not [i for i in items if i.kind == "shadow"]
    assert len([i for i in items if i.blend == "opaque"]) == 6 and {i.depth[0] for i in items} == {dl.PASS_FLAT}
    assert {i.sprite[0] for i in items} == {"bridge"}


# --- shadow geometry --------------------------------------------------------------------

def test_object_shadow_anchor_and_structure_shadow_anchor():
    rec = orec(Width=8, Height=6, CenterX=3, CenterY=5)
    sf = lambda: sprite_file(1)
    a = FakeAssets(objects={5: ObjectSet(rec, sprites={"main": sf(), "main_b": sf()})},
                   structures={100: StructureSet(srec(), sprites={"main": sprite_file(8), "main_b": sprite_file(8)})})
    day = lt.daylight(0, False)
    T = math.tan(lt.shadow_angle(day.angle))
    w = flat_world([obj(1, 10, 10), struct(1, 20, 20)])
    items = build_draw_list(w, cam(), 0, a, DrawOptions())
    sh = next(i for i in items if i.kind == "shadow" and i.entity == 0x10001 and i.sprite[2] == "main")
    dx = int(T * (1 // 2 + 6 // 2 - 5))
    assert sh.sx == 10 * 32 + 16 - ((3 - 4) + 4 // 2) - dx and sh.sy == 10 * 32 + 16 - ((5 - 3) + 1 // 2)
    assert sh.shear == lt.shadow_shear(day.angle)
    ss = [i for i in items if i.kind == "shadow" and i.entity == 0x6001 and i.sprite[2] == "main"]
    px = {i.frame: i.sx for i in ss}
    assert px[2] == 20 * 32 + int(T * ((2 - 1) * 32 - 40)) and px[0] == 20 * 32 + int(T * ((2 - 0) * 32 - 40))


def test_shadow_uses_frame_zero_size_for_placement_but_current_frame_for_shape():
    # frame 0 is 4x1, frame 1 is 8x2: the position uses w0/h0 of frame 0 (the exe's quirk)
    from helpers import container
    pal = bytes(1024)
    data = lambda w, h: (w, h, bytes([0x81, w - 1]) + bytes([1] * (w - 1)))
    sfile = __import__("allods2.graphics", fromlist=["SpriteFile"]).SpriteFile.parse(
        container([data(4, 1), (8, 1, bytes([0x81, 7] + [1] * 7))], pal))
    rec = orec(Width=8, Height=1, CenterX=4, CenterY=1, seq=[1], Index=0)
    a = FakeAssets(objects={5: ObjectSet(rec, sprites={"main": sfile, "main_b": sprite_file(1)})})
    w = flat_world([obj(1, 10, 10)])
    items = build_draw_list(w, cam(), 0, a, DrawOptions(smoothing=False))
    sh = next(i for i in items if i.kind == "shadow")
    sp = next(i for i in items if i.kind == "sprite")
    day = lt.daylight(0, False)
    dx = int(math.tan(lt.shadow_angle(day.angle)) * (1 // 2 + 1 // 2 - 1))
    assert sh.frame == sp.frame == 1 and sh.w == 8
    assert sh.sx == 10 * 32 + 16 - ((4 - 4) + 4 // 2) - dx           # w0 = 4 (frame 0)
    assert sp.sx == 10 * 32 + 16 - ((4 - 4) + 8 // 2)                # the draw uses frame 1 (w = 8)


# --- debug overlays -----------------------------------------------------------------------

def test_debug_flags_parse_and_toggle():
    f = DebugFlags.parse("passability, depth")
    assert (f.passability, f.markers, f.depth) == (True, False, True)
    f.toggle("markers")
    assert f.markers and f.any()
    with pytest.raises(ValueError):
        DebugFlags.parse("nope")
    with pytest.raises(ValueError):
        f.toggle("nope")
    assert not DebugFlags().any()


def test_overlay_items_exist_and_come_last():
    w = flat_world([obj(1, 10, 10), struct(1, 12, 12, fp=((0, 0, True), (1, 0, True)))])
    c = cam(0, 0, 640, 480)
    items = build_draw_list(w, c, 0, assets(), PLAIN, DebugFlags(True, True, True))
    kinds = [i.kind for i in items]
    first = min(k for k, v in enumerate(kinds) if v in ("passability", "marker", "depth"))
    assert all(k in ("sprite", "shadow") for k in kinds[:first])
    vx, vy, ww, hv = view_window(c)
    blocked = ~w.walkable(1)
    want = int(blocked[vy:vy + hv, vx:vx + ww].sum())
    assert len([i for i in items if i.kind == "passability"]) == want > 0
    cells = [i for i in items if i.kind == "marker" and i.text is None]
    assert len(cells) == 1 + 2                                    # tree cell + two structure cells
    assert len([i for i in items if i.kind == "marker" and i.text == "hotspot"]) == 2
    assert all(i.text.startswith("P") for i in items if i.kind == "depth")
    assert len([i for i in items if i.kind == "depth"]) == len(sprites_of(items))
    assert build_draw_list(w, c, 0, assets(), PLAIN, DebugFlags()) == build_draw_list(w, c, 0, assets(), PLAIN)


def test_view_has_no_pygame_and_default_options_are_the_games():
    o = DrawOptions()
    assert (o.shadows, o.lit, o.smoothing, o.animate) == (True, True, True, True)
    assert not hasattr(dl, "pygame")


# --- backend ---------------------------------------------------------------------------------

pygame = pytest.importorskip("pygame")

from allods2.graphics.canvas import Canvas                                # noqa: E402
from engine.backend_pygame import render                                  # noqa: E402
from engine.backend_pygame.sprites import SpriteCache                     # noqa: E402
from engine.backend_pygame.window import ensure_display                   # noqa: E402


def surface_with(bg):
    ensure_display(bg.shape[1], bg.shape[0])
    s = pygame.Surface((bg.shape[1], bg.shape[0]))
    pygame.surfarray.pixels3d(s)[...] = bg.transpose(1, 0, 2)
    return s


def rng_bg(h=12, w=24, seed=3):
    return np.random.default_rng(seed).integers(0, 256, (h, w, 3)).astype(np.uint8)


def test_half_blend_equals_canvas_translucent_and_clips():
    a = assets()
    cache = SpriteCache(a)
    sf = a.object_set(5).sprites("main_b")
    bg = rng_bg()
    for x, y in ((5, 4), (-2, -0), (22, 11), (-9, 3)):
        surf = surface_with(bg)
        item = dl.DrawItem("sprite", 1, ("object", 5, "main_b"), 0, x, y, 4, 1, blend="half")
        render.blend_half(surf, x, y, cache.get(item))
        cv = Canvas(24, 12)
        cv.pix[...] = bg
        cv.draw_256_translucent(sf[0], x, y, sf.palette)
        assert np.array_equal(render.surface_rgb(surf), cv.pix), (x, y)


@pytest.mark.parametrize("level", [2, 4, 8])
def test_unsheared_shadow_equals_canvas_darken(level):
    a = assets()
    cache = SpriteCache(a)
    sf = a.object_set(5).sprites("main")
    bg = rng_bg()
    surf = surface_with(bg)
    item = dl.DrawItem("shadow", 1, ("object", 5, "main"), 0, 6, 5, 4, 1, blend="shadow", shadow=True,
                       shadow_level=level, shear=0)
    render.blend_shadow(surf, 6, 5, cache.get(item), level)
    cv = Canvas(24, 12)
    cv.pix[...] = bg
    cv.draw_darken(sf[0], 6, 5, level)
    assert np.array_equal(render.surface_rgb(surf), cv.pix)


def test_sheared_shadow_follows_row_offsets_and_blend_row():
    # a 6 x 5 sprite, every pixel drawn
    from helpers import container
    from allods2.graphics import SpriteFile
    rows = b"".join(bytes([0x81, 5]) + bytes([1] * 5) for _ in range(5))
    sf = SpriteFile.parse(container([(6, 5, rows)], bytes(1024)))
    a = FakeAssets(objects={5: ObjectSet(orec(), sprites={"main": sf})})
    cache = SpriteCache(a)
    shear = lt.shadow_shear(lt.daylight(0, False).angle)
    off = lt.shadow_row_offsets(5, shear)
    bg = rng_bg(14, 30)
    surf = surface_with(bg)
    item = dl.DrawItem("shadow", 1, ("object", 5, "main"), 0, 8, 3, 6, 5, blend="shadow", shadow=True,
                       shadow_level=4, shear=shear)
    render.blend_shadow(surf, 8, 3, cache.get(item), 4)
    want = bg.copy()
    d = sf.decode(0)
    for r in range(5):
        for c in range(6):
            if d.mask[r, c]:
                want[3 + r, 8 + c + off[r]] = bg[3 + r, 8 + c + off[r]].astype(np.uint16) * 12 >> 4
    assert np.array_equal(render.surface_rgb(surf), want)
    assert min(off) >= 0 and max(off) > 0 and off[-1] <= 1


def test_lit_row_uses_bright2_table_of_the_main_palette():
    from allods2.graphics.palette import BRIGHT2, shade_table
    a = assets()
    cache = SpriteCache(a)
    pal = np.asarray(a.object_set(5).sprites("main").palette, np.uint8)
    t = shade_table(pal, 16, BRIGHT2)
    for row in (0, 3, 15):
        assert np.array_equal(cache.palette(("object", 5, "main"), row), t[row])
        assert np.array_equal(cache.palette(("object", 5, "main_b"), row), t[row])    # b: the main table
    assert np.array_equal(cache.palette(("object", 5, "main"), None), pal)
    item = dl.DrawItem("sprite", 1, ("object", 5, "main"), 0, 0, 0, 4, 1, light_row=3)
    surf = cache.get(item)
    assert tuple(surf.get_at((1, 0)))[:3] == tuple(t[3][1]) and surf.get_at((1, 0))[3] == 255
    assert surf.get_at((0, 0))[3] == 0                      # pixel 0 is transparent


def test_sprite_cache_hits_and_lru_and_missing_frame():
    a = assets()
    cache = SpriteCache(a, capacity=2)
    mk = lambda f: dl.DrawItem("sprite", 1, ("object", 5, "main"), f, 0, 0, 4, 1)
    cache.get(mk(0))
    cache.get(mk(0))
    assert (cache.hits, cache.misses) == (1, 1)
    cache.get(mk(1))
    cache.get(mk(2))
    assert len(cache._d) == 2
    assert cache.get(mk(99)) is None


def test_draw_frame_draws_list_order_and_overlays(tmp_path):
    from engine.backend_pygame.render import Caches, draw_frame
    from engine.backend_pygame.surfaces import SurfaceCache
    from engine.view import TerrainView, build_terrain_items
    from allods2.graphics.terrain import TerrainSet
    w = flat_world([obj(1, 2, 2)])
    tv = TerrainView(w, TerrainSet({}, np.zeros((128, 32), np.uint8), np.zeros((256, 3), np.uint8)))
    c = Camera(160, 160, W, H, 0, 0)
    a = assets()
    ensure_display(160, 160)
    surf = pygame.Surface((160, 160))
    caches = Caches(SurfaceCache(tv), SpriteCache(a))
    tis = build_terrain_items(tv, c, 0)
    draw_frame(surf, caches, tis, build_draw_list(w, c, 0, a, PLAIN), c)
    px = a.object_set(5).sprites("main").palette[1]
    at = (2 * 32 + 16 - 2 + 1, 2 * 32 + 16 - 1)
    assert tuple(surf.get_at(at))[:3] == tuple(px)
    draw_frame(surf, caches, tis, build_draw_list(w, c, 0, a, PLAIN, DebugFlags(True, True, True)), c)
    assert tuple(surf.get_at((2 * 32, 2 * 32 - 1)))[:3] != (0, 0, 0)            # a marker outline pixel
    ts = render.screenshot(tv, c, 0, str(tmp_path / "o.png"), assets=a, options=PLAIN)
    assert ts.shape == (160, 160, 3) and (tmp_path / "o.png").exists()


def test_cached_frame_equals_uncached(tmp_path):
    """The terrain layer cache and the per-object item memo change no pixel: a warm frame, a moved camera, a changed
    light and a frame with the memos cleared all equal the uncached path (terrain cell by cell, fresh caches)."""
    from engine.backend_pygame.render import Caches, draw_frame
    from engine.backend_pygame.surfaces import SurfaceCache
    from engine.view import TerrainView, build_terrain_items
    from allods2.graphics.terrain import TerrainSet

    class NoLayer(SurfaceCache):                                  # the pre-cache path: every cell blitted per frame
        layer = None

    w = flat_world([obj(1, 2, 2), obj(2, 3, 4), obj(3, 5, 3)])
    tv = TerrainView(w, TerrainSet({}, np.zeros((128, 32), np.uint8), np.zeros((256, 3), np.uint8)))
    a = assets()
    ensure_display(160, 160)
    sprites = SpriteCache(a)
    warm = Caches(SurfaceCache(tv), sprites)
    layered = Caches(SurfaceCache(tv), SpriteCache(a), scene=False)       # the terrain layer cache without the scene memo

    def frame(caches, x, y, tick, opts=DrawOptions()):
        c = Camera(160, 160, W, H, x, y)
        items = build_draw_list(w, c, tick, a, opts)
        surf = pygame.Surface((160, 160))
        draw_frame(surf, caches, build_terrain_items(tv, c, tick, items.lights), items, c)
        return pygame.image.tobytes(surf, "RGB")

    for opts in (DrawOptions(), PLAIN):
        for x, y, tick in ((0, 0, 0), (0, 0, 0), (13, 7, 0), (13, 7, 5), (0, 0, 0)):
            ref = frame(Caches(NoLayer(tv), SpriteCache(a)), x, y, tick, opts)
            w.__dict__.pop("_object_items", None)
            assert frame(warm, x, y, tick, opts) == ref
            assert frame(warm, x, y, tick, opts) == ref            # second time: scene and item memo hit
            assert frame(layered, x, y, tick, opts) == ref
            assert frame(layered, x, y, tick, opts) == ref         # layer hit
    assert layered.terrain.layer_hits > 0 and layered.terrain.layer_misses > 0 and warm.scene.incremental > 0
    w.cells_version = getattr(w, "cells_version", 0) + 1         # burnt ground: every cached cell and layer is stale
    frame(warm, 0, 0, 0)
    assert warm.terrain._version == tv.version and len(warm.terrain._layers) == 1


# --- install: parity with E4, goldens --------------------------------------------------------------

def _tool():
    spec = importlib.util.spec_from_file_location("update_golden", os.path.join(ROOT, "tools", "update_golden.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.lru_cache(maxsize=2)
def _e4(spec, tick, structures, units=False):
    """(reference image, top): E4 = render_3d + anim.scene.draw_scene, as `map render` does."""
    from allods2.anim.scene import Scene, draw_scene
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from allods2.graphics import terrain as tr
    a = AssetCache(GFS)
    m = open_map(spec)
    w = World.from_map(m, a)
    day = lt.daylight(0, False)
    light = lt.terrain_light(w.heights, day.angle, day.ambient, day.diffuse)
    img, top = tr.render_3d(w.cells, w.heights, a.tileset(), light, anim=tick, tint=day.tint)
    cv = Canvas(1, 1)
    cv.pix = np.ascontiguousarray(img)
    draw_scene(cv, m, Scene(a), top=top, relief=True, clock=tick, structures=structures,
               units=units, items=units)
    return cv.pix, top


@functools.lru_cache(maxsize=2)
def _env(spec):
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.view import TerrainView
    from engine.backend_pygame.surfaces import SurfaceCache
    a = AssetCache(GFS)
    w = World.from_map(open_map(spec), a, facing=8 << 4)          # E5 draws every unit at direction 8
    tv = TerrainView(w, a.tileset())
    return w, tv, a, SurfaceCache(tv), SpriteCache(a)


def _shot(spec, x, y, tick=0, opts=E4):
    w, tv, a, tc, sc = _env(spec)
    c = Camera(1024, 768, w.width, w.height, x, y)
    rgb = render.screenshot(tv, c, tick, None, tc, a, opts, None, sc)
    return rgb, c


def _positions():
    return _tool().PARITY


@needs_graphics
@pytest.mark.parametrize("name", sorted(_tool().PARITY))
def test_parity_with_e4_pixel_exact(name):
    spec, x, y, what = _tool().PARITY[name]
    ref, top = _e4(spec, 0, True)
    rgb, c = _shot(spec, x, y)
    assert np.array_equal(rgb, ref[top + c.iy:top + c.iy + 768, c.ix:c.ix + 1024]), name
    w, tv, a, tc, sc = _env(spec)
    items = build_draw_list(w, c, 0, a, E4)
    for kind in what:                                  # the position really shows what it is chosen for
        assert any(i.sprite and i.sprite[0] == kind for i in items), (name, kind)


@needs_graphics
@pytest.mark.parametrize("name", sorted(_tool().UNIT_PARITY))
def test_parity_with_e5_units_and_piles_pixel_exact(name):
    """`map render --relief --layers all` (E5) equals the engine with shadows and light off."""
    spec, x, y, what = _tool().UNIT_PARITY[name]
    ref, top = _e4(spec, 0, True, units=True)
    rgb, c = _shot(spec, x, y, opts=E5)
    assert np.array_equal(rgb, ref[top + c.iy:top + c.iy + 768, c.ix:c.ix + 1024]), name
    w, tv, a, tc, sc = _env(spec)
    items = build_draw_list(w, c, 0, a, E5)
    kinds = {i.sprite[0] for i in items if i.sprite}
    for kind in what:
        if kind == "flyer":
            assert any(i.depth[0] == dl.PASS_FLYER for i in items), name
        else:
            assert kind in kinds, (name, kind)


@needs_graphics
def test_parity_with_e4_animated_objects_at_tick_20():
    spec, x, y = "10", 256, 256
    w, tv, a, tc, sc = _env(spec)
    gone = World(w.cells, w.heights)
    for o in w.objects.values():
        if o.kind == "object":
            gone.add_object(MapObject(o.id, o.kind, o.type_id, o.x, o.y))
    ref, top = _e4(spec, 20, False)
    c = Camera(1024, 768, w.width, w.height, x, y)
    from engine.view import TerrainView
    from engine.backend_pygame.surfaces import SurfaceCache
    tv2 = TerrainView(gone, a.tileset())
    rgb = render.screenshot(tv2, c, 20, None, SurfaceCache(tv2), a, E4, None, sc)
    assert np.array_equal(rgb, ref[top + c.iy:top + c.iy + 768, c.ix:c.ix + 1024])
    other = render.screenshot(tv2, c, 0, None, SurfaceCache(tv2), a, E4, None, sc)
    assert not np.array_equal(rgb, other)                       # trees animate


@needs_graphics
def test_no_sprite_reaches_beyond_the_window_margin():
    """Data check behind the cull rule: an object anchored just outside the exe's window
    (3 cells left/right/top, 7 below) can show no pixel inside the viewport."""
    from allods2.assets import AssetCache
    a = AssetCache(GFS)
    left = right = up = down = 0
    for oid in a.objects_reg():
        s = a.object_set(oid)
        for src in ("main", "main_b"):
            sf = s and s.sprites(src)
            for i in range(len(sf) if sf else 0):
                ax, ay = s.anchor(sf[i].width, sf[i].height)
                left, right = max(left, ax), max(right, sf[i].width - ax)
                up, down = max(up, ay), max(down, sf[i].height - ay)
    assert max(left, right, down) < 3 * 32 + 16 and up < 7 * 32 + 16 - 127


@needs_graphics
def test_golden_screenshots():
    gold = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["screenshots"]
    tool = _tool()
    assert sorted(gold) == sorted(tool.SHOTS)
    got = tool.shot_hashes(GFS)                       # same worlds and options as the generator
    for name in sorted(tool.SHOTS):
        assert got[name] == gold[name], "%s changed; if intended run tools/update_golden.py" % name


@needs_graphics
def test_cli_screenshot_with_objects_and_debug(tmp_path, monkeypatch):
    from PIL import Image
    from engine.__main__ import main
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    dest = tmp_path / "s.png"
    assert main(["screenshot", "10", "1056", "740", str(dest), "--size", "320x200", "--no-shadows",
                 "--no-light", "--debug", "passability,markers,depth"]) == 0
    assert Image.open(dest).size == (320, 200)
    with pytest.raises(SystemExit):
        main(["screenshot", "10", "0", "0", str(dest), "--debug", "bogus"])


def test_main_loop_runs_with_objects_and_debug_keys():
    """window.run for a few frames with a synthetic world (also F1-F3 handling)."""
    from allods2.graphics.terrain import TerrainSet
    from engine.backend_pygame import window
    from engine.view import TerrainView
    w = flat_world([obj(1, 2, 2), struct(1, 4, 4)])
    tv = TerrainView(w, TerrainSet({}, np.zeros((128, 32), np.uint8), np.zeros((256, 3), np.uint8)))
    from engine.ui import Layout
    from engine.world import Player
    w.players[1] = Player(1, 0, "me", human=True)
    lay = Layout.for_size(640, 480)
    ensure_display(640, 480)
    for key in (pygame.K_F1, pygame.K_F2, pygame.K_F3):
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key))
    dbg = DebugFlags()
    a = assets()
    a.fs = None                                     # no game files: panels and cursors draw nothing
    window.run(w, tv, Camera(lay.viewport.w, lay.viewport.h, W, H), lay, assets=a, debug=dbg, max_frames=3)
    assert dbg.passability and dbg.markers and dbg.depth


def test_burnt_cell_draws_the_dead_object_frame_zero():
    """Tile bit 0x2000 + DeadObject != -1: the object is drawn from the DeadObject's file, frame 0 (CONFIRMED 0x408b0f / 0x408c10)."""
    dead = orec(ID=7, Index=0)
    s = ObjectSet(orec(Index=2, DeadObject=7), dead,
                  sprites={"main": sprite_file(4), "main_b": sprite_file(4), "dead": sprite_file(2), "dead_b": sprite_file(2)})
    a = FakeAssets(objects={5: s})
    w = flat_world([obj(1, 10, 10)])
    src = lambda: [i.sprite[2] for i in build_draw_list(w, cam(), 0, a, PLAIN) if i.kind == "sprite"]
    assert src() == ["main"]
    w.scorch(10, 10)
    items = [i for i in build_draw_list(w, cam(), 0, a, PLAIN) if i.kind == "sprite"]
    assert [(i.sprite[2], i.frame) for i in items] == [("dead", 0)]
    w.scorch(11, 11)                                                    # a different cell: unaffected
