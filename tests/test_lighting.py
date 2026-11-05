"""Synthetic tests, one per rule in docs/mechanics/lighting.md (sections 3-5)."""

import numpy as np
import pytest

from allods2 import graphics as gfx
from allods2.graphics.lighting import NO_LIGHT, STATIC_LIGHT_PHASES


def test_stamp_light_disk():
    m = np.full((9, 9), NO_LIGHT, np.uint8)
    gfx.stamp_light(m, 4, 4, 2, 7)            # dx^2 + dy^2 < 6
    lit = {(x - 4, y - 4) for y, x in zip(*np.nonzero(m == 7))}
    assert (2, 1) in lit and (0, 2) in lit
    assert (2, 2) not in lit                   # 8 >= 6
    assert len(lit) == 21


def test_stamp_light_radius_zero_and_clipping():
    m = np.full((3, 3), NO_LIGHT, np.uint8)
    gfx.stamp_light(m, 0, 0, 0, 5)
    assert m[0, 0] == 5 and (m == 5).sum() == 1
    gfx.stamp_light(m, 0, 0, 1, 6)            # partly outside: skipped, no error
    assert (m == 6).sum() == 3


def test_static_light_flicker_cycle():
    assert STATIC_LIGHT_PHASES == (36, 24, 12, 0, 12, 0, 12, 0, 20, 28, 36)


def test_projectile_lights():
    assert gfx.projectile_light(10) == (0, 16)            # firebolt
    assert gfx.projectile_light(12) == (1, 16)            # fireball
    assert gfx.projectile_light(13, 1) == (2, 8)          # fire explosion
    assert gfx.projectile_light(13, 2) == (3, 0)
    assert gfx.projectile_light(13, 10) == (3, 46)
    assert gfx.projectile_light(1) is None                # arrows: no light


def test_lit_terrain_corner():
    assert gfx.lit_terrain_corner(46, NO_LIGHT) == 46
    assert gfx.lit_terrain_corner(46, 16) == 16
    assert gfx.lit_terrain_corner(10, 16) == 10


def test_object_light_row_lit():
    assert gfx.object_light_row_lit([255] * 4, 32) is None
    assert gfx.object_light_row_lit([0, 0, 0, 0], 32) == 0        # torch: x2
    assert gfx.object_light_row_lit([46] * 4, 32) == 3             # 4 * 14 >> 4
    assert gfx.object_light_row_lit([0, 255, 255, 255], 32) == 6   # 3 * 32 >> 4
    assert gfx.object_light_row_lit([0, 255, 255, 255], 14) == 2   # 3 * 14 >> 4 = 2 < 14 >> 2


def test_shadow_angle_snaps_small_angles():
    assert gfx.shadow_angle(0.0) == 0.0
    assert gfx.shadow_angle(0.01) == 0.05 and gfx.shadow_angle(-0.01) == -0.05
    assert gfx.shadow_angle(0.6) == 0.6 / 1.5


def test_shadow_shear_and_rows():
    shear = gfx.shadow_shear(0.78539815)       # tan(pi/6) * 65536
    assert shear == int(np.tan(0.78539815 / 1.5) * 65536)
    rows = gfx.shadow_row_offsets(4, 0x8000)   # half a pixel per row
    assert rows == [2, 2, 1, 1]
    rows = gfx.shadow_row_offsets(3, -0x10000)
    assert rows == [-3, -2, -1]


def test_shadow_pixel():
    day, night = gfx.daylight(12 * 60), gfx.daylight(0)
    assert gfx.shadow_pixel((160, 80, 16), day.shadow1) == (120, 60, 12)
    assert gfx.shadow_pixel((160, 80, 16), night.shadow1) == (80, 40, 8)


def test_structure_light_pulse():
    from allods2.graphics.lighting import structure_light_value, structure_light_vertices
    assert structure_light_value(0, 123) == 32
    assert [structure_light_value(8, c) for c in range(16)] == \
        [28, 30, 31, 33, 34, 36, 37, 39, 32, 30, 29, 27, 26, 24, 23, 21]
    assert structure_light_value(8, 16) == 28
    assert structure_light_vertices(2, 3, 3, 4, 1) == [(2, 3), (3, 3), (4, 3), (2, 4), (3, 4),
                                                       (4, 4), (2, 5), (3, 5), (4, 5)]


# --- fog (lighting.md §3, fog draw) ------------------------------------------

def test_fog_level_bits():
    assert [gfx.fog_level(b) for b in (0xC000, 0x8000, 0x4000, 0, 0xC123)] == [0, 8, 16, 16, 0]


def test_fog_shade_rows():
    px = np.array([0xFFFF, 0x1234, 0xF81F], np.uint16)
    assert (gfx.fog_shade(px, 0) == px).all()
    assert (gfx.fog_shade(px, 16) == 0).all()
    assert (gfx.fog_shade(px, 8) == (px >> 1) & 0x7BEF).all()     # halving fast path
    assert int(gfx.fog_shade(0xFFFF, 4)) == (23 << 11) | (47 << 5) | 23


def test_fog_uniform_quad_is_constant():
    cols = list(gfx.fog_quad_columns(0, 0, 32, 32, (8, 8, 8, 8)))
    assert len(cols) == 32
    assert all(y0 == 0 and len(k) == 32 and set(k.tolist()) == {8} for _, y0, k in cols)


def test_fog_gradient_worked_example():
    cols = list(gfx.fog_quad_columns(0, 0, 32, 32, (16, 0, 0, 0)))
    assert cols[0][2].tolist() == [16 - i // 2 for i in range(32)]
    assert cols[1][2].tolist()[:3] == [16, 15, 15] and cols[1][2][-1] == 0
    assert cols[16][2][0] == 8
    assert cols[31][2].tolist() == [1] + [0] * 31


def test_fog_quad_follows_terrain_edges():
    # top edge rising 2 px to the right: same steps as the terrain blit
    cols = list(gfx.fog_quad_columns(0, -2, 32, 32, (16, 16, 16, 16)))
    assert [cols[c][1] for c in (0, 10, 11, 20, 21, 31)] == [0, 0, -1, -1, -2, -2]
    assert len(cols[21][2]) == 34


def test_fog_runs_merge_skip_and_corner_shift():
    L = np.zeros((4, 3), int)
    L[:, 1] = 16                          # column 1 never seen
    vy = np.arange(4)[:, None] * 32 + np.zeros((1, 3), int)
    runs = gfx.fog_runs(L, vy, 2, 3)
    # column 0 gets a TL=0/TR=16 gradient (corners shifted), merged over 3 rows
    assert runs[0] == (0, 0, 0, 96, 96, (0, 16, 0, 16), False)
    # column 1 uniform 16 but merged (96 px high) so not the flat fast path
    assert runs[1] == (32, 0, 0, 96, 96, (16, 0, 16, 0), False)
    L2 = np.zeros((3, 3), int)
    assert gfx.fog_runs(L2, vy, 2, 2) == []           # all in sight: nothing


def test_fog_last_row_does_not_merge():
    L = np.full((4, 2), 16)
    vy = np.arange(4)[:, None] * 32 + np.zeros((1, 2), int)
    runs = gfx.fog_runs(L, vy, 1, 2)
    assert [(r[1], r[3]) for r in runs] == [(0, 64)]   # rows 0-1 merged, stops at rows-1
    runs = gfx.fog_runs(L[:2], vy, 1, 1)
    assert runs == [(0, 0, 0, 32, 32, (16, 16, 16, 16), True)]


def test_draw_fog_clip():
    s = np.full((40, 40), 0xFFFF, np.uint16)
    L = np.full((2, 3), 8)
    vy = np.array([[0, 0, 0], [32, 32, 32]])
    gfx.draw_fog(s, L, vy, 2, 1, clip=(0, 0, 40, 40))
    assert s[0, 0] == 0x7BEF                      # flat uniform: no x clip test
    assert s[0, 39] == 0x7BEF
    s[:] = 0xFFFF
    L = np.array([[8, 0, 0], [8, 0, 0]])
    gfx.draw_fog(s, L, vy, 2, 1, clip=(0, 0, 40, 40))
    assert s[0, 0] != 0xFFFF and s[0, 33] == 0xFFFF   # mixed quad at x=32 sticks out: skipped


def test_fog_column_quads_overlap_only_on_63_and_127():
    from allods2.graphics.terrain import edge_offsets
    for n in range(1, 128):
        for a, b in ((0, n), (n, 0)):
            d = edge_offsets(a, b, bottom=True) - edge_offsets(a, b)
            assert set(d.tolist()) == ({1} if n in (63, 127) else {0})
    s = np.full((200, 32), 0xFFFF, np.uint16)
    L = np.array([[8, 8], [8, 8], [16, 16]])  # L[2] differs: no merge
    vy = np.array([[0, 0], [32, 95], [96, 160]])
    gfx.draw_fog(s, L, vy, 1, 2)
    assert s[31, 0] == 0x7BEF and s[32, 0] == 0x39E7 and s[33, 0] == 0x7BEF


@pytest.mark.parametrize("seed", range(6))
def test_fog_layers_equal_draw_fog(seed):
    """The cached layer form of the fog pass is bit-identical to the reference per-column draw (overlapping relief folds included)."""
    rng = np.random.default_rng(seed)
    cols, rows = 6, 7
    L = rng.choice([0, 0, 8, 16, 3, 11], size=(rows + 3, cols + 1))
    L[2:5, :] = np.where(rng.random((3, cols + 1)) < 0.5, 8, L[2:5, :])
    vy = np.arange(rows + 3)[:, None] * 32 + rng.choice([0, 0, 31, 63, 127, -40, 17], size=(rows + 3, cols + 1))
    H, W = 190, 200
    px = rng.integers(0, 65536, size=(H, W)).astype(np.uint16)
    for clip in (None, (0, 0, 190, 150), (10, 20, 170, 170)):
        a, b = px.copy(), px.copy()
        gfx.draw_fog(a, L, vy, cols, rows, clip=clip)
        gfx.apply_fog_layers(b, gfx.fog_layers(L, vy, cols, rows, (H, W), clip=clip))
        assert (a == b).all()
        assert not (a == px).all()


def test_fog_rgb_path_equals_the_16_bit_round_trip():
    from allods2.graphics.palette import pack16, unpack16
    rng = np.random.default_rng(3)
    cols, rows = 5, 6
    L = rng.choice([0, 8, 16, 5, 13], size=(rows + 3, cols + 1))
    vy = np.arange(rows + 3)[:, None] * 32 + rng.choice([0, 63, -20, 127], size=(rows + 3, cols + 1))
    H, W = 170, 160
    words = rng.integers(0, 2**32, size=H * W, dtype=np.uint64).astype(np.uint32)
    rgb = words.view(np.uint8).reshape(H, W, 4).copy()
    px = pack16(rgb[..., :3])
    gfx.draw_fog(px, L, vy, cols, rows)
    want = unpack16(px)
    w2 = words.copy()
    gfx.lighting.apply_fog_layers_rgb(w2, gfx.fog_layers(L, vy, cols, rows, (H, W)))
    assert (w2.view(np.uint8).reshape(H, W, 4)[..., :3] == want).all()
    assert (w2.view(np.uint8).reshape(H, W, 4)[..., 3] == rgb[..., 3]).all()      # the X byte is left alone


def _flow_view(time_flow):
    from allods2.graphics.terrain import TerrainSet
    from engine.view import TerrainView
    from engine.world import World
    w = World.__new__(World)
    w.heights = np.zeros((8, 8), np.int16)
    w.cells = np.zeros((7, 7), np.uint16)
    return TerrainView(w, TerrainSet({}, np.zeros((128, 32), np.uint8), np.zeros((256, 3), np.uint8)),
                       time_flow=time_flow)


def test_time_flow_off_never_recomputes():
    tv = _flow_view(False)
    v = tv.version
    assert not any(tv.set_clock(t) for t in range(0, 2000))
    assert tv.version == v and tv.day.ambient == 14 and tv.day.angle == pytest.approx(0.78539815)


def test_time_flow_cadence_every_320_ticks():
    tv = _flow_view(True)
    hits = [t for t in range(0, 6000) if tv.set_clock(t)]
    assert hits == list(range(0, 6000, 320))              # (tick >> 4) + 360 a multiple of 20; tick 0 steps off the seed value


def test_time_flow_night_light_and_toggle():
    tv = _flow_view(True)
    tv.set_clock((22 * 60 - 360) * 16)                    # 22:00: night
    assert (tv.day.ambient, tv.day.diffuse, tv.day.tint) == (32, 8, (0, 12, 48))
    assert tv.light[3, 3] == 64                           # flat: 68 - 8 * 0.5
    tv.set_time_flow(False, 0)
    assert tv.day.ambient == 14 and tv.light[3, 3] == 46
