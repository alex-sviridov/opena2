"""Time of day and light levels; spec: docs/mechanics/lighting.md.

Light values are shade-table row numbers: row 0 is the brightest
(see palette.shade_table).  Terrain uses 96-row BRIGHT32 tables, objects
16-row BRIGHT2 tables.
"""

import math
from dataclasses import dataclass

import numpy as np

# Doubles as stored in allods2.exe .rdata (not exact pi fractions).
_PI = 3.1415926                  # 0x5cd818
_QUARTER = 0.78539815            # 0x5cd840 / -0x5cd830
_SUN_ELEVATION = 0.5235987666666667   # 0x5cea70, ~pi/6
_CELL = 32.0                     # 0x5cea68
_LIGHT_MAX = 94.0                # 0x5cea78


@dataclass(frozen=True)
class Daylight:
    """Globals set by FUN_00474d98 (addresses in allods2.exe)."""
    tint: tuple        # 0x6226c0..a, (R, G, B) added before palette conversion
    ambient: int       # 0x6226c4
    diffuse: int       # 0x6226c8
    shadow1: int       # 0x6226cc, shadow darkness level (dst * (16 - k) / 16)
    shadow2: int       # 0x6226d0, lighter shadow level
    angle: float       # 0x6226d8, sun azimuth in radians


def daylight(minutes, enabled=True):
    """Lighting state at game time `minutes` (0 = midnight).  `enabled` is
    the day/night option (DAT_00622770); off gives the fixed default."""
    if not enabled:
        return Daylight((0, 0, 0), 14, 32, 4, 2, _QUARTER)
    hour = (minutes // 60) % 24
    m = minutes % 120
    if 6 <= hour <= 17:
        angle = ((minutes + 360) % 720) * _PI / 2.0 / 720.0 + -_QUARTER
        return Daylight((0, 0, 0), 14, 32, 4, 2, angle)
    if hour < 2 or hour > 21:
        angle = _QUARTER - ((minutes + 120) % 240) * _PI / 2.0 / 240.0
        return Daylight((0, 12, 48), 32, 8, 8, 4, angle)
    if hour < 4:
        return Daylight((m * 24 // 120, 12, 48 - m * 48 // 120),
                        32 - m * 4 // 120, m * 12 // 120 + 8, 6, 3, -_QUARTER)
    if hour < 6:
        return Daylight((24 - m * 24 // 120, 12 - m * 12 // 120, 0),
                        28 - m * 14 // 120, m * 12 // 120 + 20, 6, 3, -_QUARTER)
    if hour < 20:
        return Daylight((m * 24 // 120, 0, m * 8 // 120),
                        m * 10 // 120 + 14, 32 - m * 12 // 120, 6, 3, _QUARTER)
    return Daylight((24 - m * 24 // 120, m * 12 // 120, m * 40 // 120 + 8),
                    m * 8 // 120 + 24, 20 - m * 12 // 120, 6, 3, _QUARTER)


def daylight_tint(minutes, enabled=True):
    """(R, G, B) bias added to palettes at game time `minutes`."""
    return daylight(minutes, enabled).tint


def _half_light(dz, run, ambient, diffuse):
    theta = math.atan2(dz, run)
    v = (ambient + diffuse // 2 + 32) - math.sin(_SUN_ELEVATION - theta) * diffuse
    if v > _LIGHT_MAX:
        v = _LIGHT_MAX
    if v < 0.0:
        v = 0.0
    return v


def terrain_light(heights, angle, ambient, diffuse):
    """Per-vertex terrain light rows (FUN_004a5dd2) from a (h, w) array of
    signed heights.  Cells with x in 1..w-2 and y in 1..h-2 are computed;
    the border keeps 0."""
    h = np.asarray(heights, np.int64)
    rows, cols = h.shape
    t = math.tan(abs(angle))
    run = _CELL / math.cos(abs(angle))
    out = np.zeros((rows, cols), np.uint8)
    for y in range(1, rows - 1):
        for x in range(1, cols - 1):
            c, s, n = h[y, x], h[y + 1], h[y - 1]
            if angle >= 0.0:
                d1 = s[x] - (s[x] - s[x - 1]) * t - c
                d2 = c - ((n[x + 1] - n[x]) * t + n[x])
            else:
                d1 = (s[x + 1] - s[x]) * t + s[x] - c
                d2 = c - (n[x] - (n[x] - n[x - 1]) * t)
            v = _half_light(d1, run, ambient, diffuse) + _half_light(d2, run, ambient, diffuse)
            out[y, x] = int(v / 2.0)
    return out


def object_light_row(ambient):
    """Default 16-row shade level for units and objects in an unlit cell
    (FUN_00404a2a): ambient >> 2."""
    return ambient >> 2


# --- light map (view + 0xa8): 0 = brightest, 0xFF = no light ----------------

NO_LIGHT = 0xFF

# FUN_0040403b: static map light value by animation phase (flags >> 1), radius 1.
STATIC_LIGHT_PHASES = (0x24, 0x18, 0x0C, 0, 0x0C, 0, 0x0C, 0, 0x14, 0x1C, 0x24)
# The list view+0xa94 holds burning cells (fire explosion / server message
# 0x414d1f), not static lights: the same table, by counter >> 1.
BURNING_LIGHT_PHASES = STATIC_LIGHT_PHASES
BURN_TICKS = 0x16           # FUN_0040c0b0 drops an entry when its counter reaches 22


def structure_light_value(pulse, clock):
    """Light-map value a structure with LightRadius writes (FUN_00462386):
    0x20 without LightPulse, else a pulse of period 2 * pulse ticks of the
    view clock."""
    if not pulse:
        return 0x20
    m = clock % (2 * pulse)
    if m >= pulse:
        return 0x20 + ((pulse - m) >> 1) - clock % pulse
    return 0x20 - ((pulse - m) >> 1) + clock % pulse


def structure_light_vertices(x0, y0, x1, y1, radius):
    """Light-map vertices FUN_00462386 writes for a structure whose view
    cell rectangle is (x0, y0)-(x1, y1): x in [x0 + R - 1, x1 + R], y the
    same.  With R = 1 (every record in the data) these are exactly the
    footprint's corner vertices; the range is not centred for other R."""
    return [(x, y) for y in range(y0 + radius - 1, y1 + radius + 1)
            for x in range(x0 + radius - 1, x1 + radius + 1)]

# FUN_0046d0ef: projectile type (projectiles.reg ID) -> (radius, value).
PROJECTILE_LIGHTS = {10: (0, 0x10), 18: (0, 0x10), 40: (0, 0x10), 12: (1, 0x10)}
# Type 13 (fireexpl): (radius, value) by phase; phases 2, 3 keep (3, 0).
_FIREEXPL = {0: (1, 0x10), 1: (2, 8), 4: (3, 8), 5: (3, 0x10), 6: (3, 0x18),
             7: (3, 0x20), 8: (3, 0x28), 9: (3, 0x2E), 10: (3, 0x2E)}


def projectile_light(type_id, phase=0):
    """(radius, value) a projectile stamps, or None.  Types 28 and 30
    (lightning, chain) instead write phase * 10 at each segment's 2x2
    vertices."""
    if type_id == 13:
        return _FIREEXPL.get(phase, (3, 0))
    return PROJECTILE_LIGHTS.get(type_id)


def stamp_light(light, cx, cy, radius, value):
    """FUN_0040631e: write `value` at every vertex (cx+dx, cy+dy) with
    dx^2 + dy^2 < r(r+1) (r = 0: just the centre).  Out-of-range vertices
    are skipped.  `light` is a (h, w) uint8 array indexed [y, x]."""
    limit = radius * (radius + 1) or 1
    h, w = light.shape
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            x, y = cx + dx, cy + dy
            if dx * dx + dy * dy < limit and 0 <= x < w and 0 <= y < h:
                light[y, x] = value


def lit_terrain_corner(terrain, light):
    """FUN_00405cf4: a lit vertex uses the brighter of the terrain light
    and the light map."""
    return terrain if light == NO_LIGHT else min(terrain, light)


def object_light_row_lit(corners, ambient):
    """FUN_00404a2a step 3: row for a cell from its four light-map corners,
    or None when all four are 0xFF (the cell keeps its default)."""
    vals = [max(v - 32, 0) for v in corners]
    if sum(vals) == 4 * 223:
        return None
    total = sum(ambient if v == 223 else v for v in vals)
    return min(ambient >> 2, total >> 4)


# --- shadows (FUN_0045506f, FUN_004a4429) ------------------------------------

def shadow_angle(angle):
    """Shadow lean from the sun angle: angle / 1.5, except that small
    non-zero angles snap to +-0.05."""
    if -0.05 < angle < 0.0:
        return -0.05
    if 0.0 < angle < 0.05:
        return 0.05
    return angle / 1.5


def shadow_shear(angle):
    """16.16 per-row horizontal shear passed to the shadow blitter."""
    return int(math.tan(shadow_angle(angle)) * 65536.0)


def shadow_row_offsets(height, shear):
    """Horizontal pixel offset of each sprite row in the shadow: the top row
    starts at trunc(shear * h / 65536) and each later row moves left by the
    whole part of an accumulating 16.16 sum."""
    p = shear * height
    off = -((-p) >> 16) if p < 0 else p >> 16
    acc, out = 0, []
    for _ in range(height):
        out.append(off)
        acc += shear
        off -= acc >> 16
        acc &= 0xFFFF
    return out


def shadow_pixel(dst_rgb, level):
    """Shadow darkening: blend table `level` scales the destination by
    (16 - level) / 16 per channel.  `level` is Daylight.shadow1 (or
    shadow2 for the lighter variant)."""
    return tuple(c * (16 - level) // 16 for c in dst_rgb)


# --- fog of war (§3 fog levels, §4.1 fog draw) -------------------------------

FOG_SEEN, FOG_EXPLORED, FOG_UNSEEN = 0, 8, 16
_FOG_K = 0x10000           # DAT_0061b488: entries per blend-table row (bytes = 2·K)


def fog_level(bits):
    """FUN_0040403b: a cell's fog level from its tile visibility bits."""
    b = bits & 0xC000
    return FOG_SEEN if b == 0xC000 else FOG_EXPLORED if b == 0x8000 else FOG_UNSEEN


def fog_shade(px, k, bits=(5, 6, 5)):
    """Blend-table row k (FUN_0045225b) on 16-bit pixels: every channel
    v -> v·(16 − k) >> 4 in its own bit width.  Row 8 equals the game's
    `(px >> 1) & mask` fast path, row 16 its black fill."""
    px = np.asarray(px, np.uint32)
    k = np.asarray(k, np.uint32)
    rb, gb, bb = bits
    out = np.zeros(np.broadcast(px, k).shape, np.uint32)
    for shift, n in ((gb + bb, rb), (bb, gb), (0, bb)):
        v = (px >> shift) & ((1 << n) - 1)
        out |= ((v * (16 - k)) >> 4) << shift
    return out.astype(np.uint16)


def fog_quad_columns(ytl, ytr, ybl, ybr, levels):
    """One fog quad as FUN_00457f5b draws it: yields (c, y_top, rows) for
    each column with pixels; rows[i] is the blend row at y_top + i.

    Edges step like the terrain blit (terrain.edge_offsets).  The levels
    (tl, tr, bl, br) walk linearly along x on the top and bottom edges,
    then down each column; a pixel takes the row its walk value + ½ falls
    in.  Uniform levels give that level everywhere, so this also describes
    the solid fast paths (FUN_00457944/cd1d black, FUN_004582bc/d7a0 half)
    and the flat variant FUN_00457da7."""
    from ..common import cdiv
    from .terrain import TILE, edge_offsets
    ftl, ftr, fbl, fbr = (int(v) for v in levels)
    top = ytl + edge_offsets(ytl, ytr)
    bot = ybl + edge_offsets(ybl, ybr, bottom=True)
    t, b = ftl * 2 * _FOG_K, fbl * 2 * _FOG_K
    for c in range(TILE):
        span = int(bot[c] - top[c])
        if span > 0:
            step = cdiv(b - t, span)
            i = np.arange(span, dtype=np.int64)
            yield c, int(top[c]), (t + _FOG_K + i * step) >> 17
        t += ((ftr - ftl) * _FOG_K * 2) >> 5
        b += ((fbr - fbl) * _FOG_K * 2) >> 5


def fog_runs(levels, vy, cols, rows):
    """The fog pass of the view draw (0x40a06a-0x40a5bc) as a list of
    (x, ytl, ytr, ybl, ybr, (tl, tr, bl, br), solid) quads in draw order.

    levels[r][c] = fog level of view cell (c, r) and vy[r][c] = screen y of
    vertex (c, r) (terrain vertex table), both at least (rows + 1) ×
    (cols + 1).  Columns go left to right, cells top to bottom.  Cell
    (c, r) is drawn over its own screen quad but its corners take the
    levels of cells (c, r), (c+1, r), (c, r+1), (c+1, r+1).  Cells whose
    left and right levels match the next cell's are merged into one tall
    quad; all-seen quads are skipped.  `solid` marks the flat 32-px-high
    uniform case that the game fills without an x clip test."""
    L = np.asarray(levels)
    out = []
    for c in range(cols):
        r = 0
        while r < rows:
            r0 = r
            while (r < rows - 1 and r + 2 < L.shape[0]
                   and L[r, c] == L[r + 1, c] == L[r + 2, c]
                   and L[r, c + 1] == L[r + 1, c + 1] == L[r + 2, c + 1]):
                r += 1
            ytl, ytr = int(vy[r0][c]), int(vy[r0][c + 1])
            ybl, ybr = int(vy[r + 1][c]), int(vy[r + 1][c + 1])
            lv = (int(L[r0, c]), int(L[r0, c + 1]), int(L[r + 1, c]), int(L[r + 1, c + 1]))
            r += 1
            if lv == (0, 0, 0, 0):
                continue
            uniform = lv[0] == lv[1] == lv[2] == lv[3] and lv[0] in (8, 16)
            flat = ytl == ytr and ybl == ybr and ytl + 32 == ybl
            out.append((32 * c, ytl, ytr, ybl, ybr, lv, uniform and flat))
    return out


def draw_fog(surface, levels, vy, cols, rows, clip=None, bits=(5, 6, 5)):
    """Darken a 16-bit view surface (H × W uint16, in place) with the fog
    pass.  Quads overlap where relief folds, and each draw darkens again.
    clip = (left, top, right, bottom), default the whole surface.  A quad
    is skipped unless x .. x+32 lies inside left .. right, except the
    solid flat case (the game does not test x there; here it is clamped)."""
    H, W = surface.shape
    left, top, right, bottom = clip or (0, 0, W, H)
    for x, ytl, ytr, ybl, ybr, lv, solid in fog_runs(levels, vy, cols, rows):
        if solid:
            y0, y1 = max(ytl, top), min(ybl, bottom)
            x0, x1 = max(x, 0), min(x + 32, W)
            if y0 < y1 and x0 < x1:
                surface[y0:y1, x0:x1] = fog_shade(surface[y0:y1, x0:x1], lv[0], bits)
            continue
        if x < left or x + 32 > right:
            continue
        if not ((ytl < bottom or ytr < bottom) and (ybl >= top or ybr >= top)):
            continue
        for c, y0, k in fog_quad_columns(ytl, ytr, ybl, ybr, lv):
            yy = y0 + np.arange(len(k))
            ok = (yy >= top) & (yy < bottom)
            col = surface[yy[ok], x + c]
            surface[yy[ok], x + c] = fog_shade(col, k[ok], bits)


_FOG_LUTS = {}


def fog_lut(bits=(5, 6, 5)):
    """(17, 65536) uint16: `fog_shade` of every 16-bit pixel at every blend row (row 0 = identity)."""
    if bits not in _FOG_LUTS:
        px = np.arange(65536, dtype=np.uint16)
        _FOG_LUTS[bits] = np.stack([fog_shade(px, k, bits) for k in range(17)])
    return _FOG_LUTS[bits]


_QUAD_CACHE = {}


def _quad_columns(ytl, ytr, ybl, ybr, lv):
    """`fog_quad_columns` memoised: the edges step by the height differences only, so a quad's columns are the same shifted by `ytl`
    wherever it is on the screen (a scrolled view reuses nearly every quad)."""
    key = (ytr - ytl, ybl - ytl, ybr - ytl, lv)
    cols = _QUAD_CACHE.get(key)
    if cols is None:
        if len(_QUAD_CACHE) > 50000:
            _QUAD_CACHE.clear()
        cols = _QUAD_CACHE[key] = list(fog_quad_columns(0, key[0], key[1], key[2], lv))
    return [(c, y0 + ytl, k) for c, y0, k in cols]


def fog_layers(levels, vy, cols, rows, shape, clip=None):
    """The same fog pass as `draw_fog`, as data: a list of (H, W) uint8 blend-row maps, applied in order by `apply_fog_layers`.

    Every quad column / solid rectangle goes to the first layer after the last one that touched any of its pixels, so the layers
    each hold disjoint pixels and the order of the overlapping draws (relief folds) is kept; row 0 = untouched.  The result of
    `apply_fog_layers` equals `draw_fog` bit for bit (`tests/test_lighting.py`).  The point is to build it once per fog / camera
    state and reuse it while the picture only changes inside."""
    H, W = shape
    left, top, right, bottom = clip or (0, 0, W, H)
    depth = np.zeros((H, W), np.int16)
    layers = []

    def put(ys, xs, k):
        layer = int(depth[ys, xs].max())
        depth[ys, xs] = layer + 1
        while len(layers) <= layer:
            layers.append(np.zeros((H, W), np.uint8))
        layers[layer][ys, xs] = k

    for x, ytl, ytr, ybl, ybr, lv, solid in fog_runs(levels, vy, cols, rows):
        if solid:
            y0, y1 = max(ytl, top), min(ybl, bottom)
            x0, x1 = max(x, 0), min(x + 32, W)
            if y0 < y1 and x0 < x1:
                put(slice(y0, y1), slice(x0, x1), lv[0])
            continue
        if x < left or x + 32 > right:
            continue
        if not ((ytl < bottom or ytr < bottom) and (ybl >= top or ybr >= top)):
            continue
        for c, y0, k in _quad_columns(ytl, ytr, ybl, ybr, lv):
            a = max(top - y0, 0)
            b = min(bottom - y0, len(k))
            if a < b:
                put(slice(y0 + a, y0 + b), x + c, k[a:b])
    return layers


def apply_fog_layers(surface, layers, bits=(5, 6, 5)):
    """Darken a 16-bit view surface (H x W uint16, contiguous, in place) with `fog_layers`."""
    lut = fog_lut(bits)
    flat = surface.reshape(-1)
    for k in layers:
        kf = k.reshape(-1)
        idx = np.flatnonzero(kf)
        if len(idx):
            flat[idx] = lut[kf[idx], flat[idx]]


_FOG_BYTE_LUTS = {}


def fog_byte_lut(bits=(5, 6, 5)):
    """(17, 3, 256) uint8: channel value c at blend row k -> the 8-bit channel after pack16, `fog_shade`, unpack16 (the channels are
    independent, so the 16-bit round trip of an RGB image is this table per channel)."""
    if bits not in _FOG_BYTE_LUTS:
        from .palette import pack16, unpack16
        c = np.arange(256, dtype=np.uint8)
        lut = np.zeros((17, 3, 256), np.uint8)
        for ch in range(3):
            rgb = np.zeros((256, 3), np.uint8)
            rgb[:, ch] = c
            px = pack16(rgb, bits)
            for k in range(17):
                lut[k, ch] = unpack16(fog_shade(px, k, bits), bits)[:, ch]
        _FOG_BYTE_LUTS[bits] = lut
    return _FOG_BYTE_LUTS[bits]


def quantize_words_565(words):
    """`unpack16(pack16(.))` of RGBX words (R, G, B, X bytes, little-endian uint32), in place: R and B keep 5 bits, G 6, the low bits
    repeat the high ones."""
    keep = np.uint32(0xFFF8FCF8)
    low = ((words >> 5) & np.uint32(0x00070007)) | ((words >> 6) & np.uint32(0x00000300))
    words &= keep
    words |= low


def apply_fog_layers_rgb(words, layers):
    """The 16-bit fog pass on an RGBX frame (`words` = its (h*w,) uint32 view, bytes R, G, B, X): the whole frame goes through the
    565 round trip as the game's 16-bit surface does, the fogged pixels take their blend rows.  Equals pack16 + `apply_fog_layers` +
    unpack16 (`tests/test_lighting.py`)."""
    quantize_words_565(words)
    lut = fog_byte_lut()
    lr, lg, lb = (lut[:, ch, :].astype(np.uint32).reshape(-1) << (8 * ch) for ch in range(3))
    for k in layers:
        kf = k.reshape(-1)
        idx = np.flatnonzero(kf)
        if len(idx):
            w = words[idx]
            base = kf[idx].astype(np.uint32) << 8
            out = lr[base | (w & 255)] | lg[base | ((w >> 8) & 255)] | lb[base | ((w >> 16) & 255)]
            words[idx] = out | (w & np.uint32(0xFF000000))


_QUAD_FLAT = {}
_QUAD_SPANS = {}


def _quad_flat(ytr, ybl, ybr, lv, width):
    """`fog_quad_columns` of a quad at (0, 0) as flat arrays for a frame `width` px wide: (pixel index, y, blend row) of every covered pixel,
    memoised by shape (the edges step by the height differences only, so the arrays shift by `ytl * width + x`)."""
    key = (ytr, ybl, ybr, lv, width)
    got = _QUAD_FLAT.get(key)
    if got is None:
        if len(_QUAD_FLAT) > 6000:
            _QUAD_FLAT.clear()
        cols = list(fog_quad_columns(0, ytr, ybl, ybr, lv))
        ys = np.concatenate([y0 + np.arange(len(k), dtype=np.int32) for _, y0, k in cols]) if cols else np.zeros(0, np.int32)
        cs = np.concatenate([np.full(len(k), c, np.int32) for c, _, k in cols]) if cols else np.zeros(0, np.int32)
        ks = np.concatenate([np.asarray(k, np.uint8) for _, _, k in cols]) if cols else np.zeros(0, np.uint8)
        got = _QUAD_FLAT[key] = (ys * width + cs, ys, ks)
    return got


def _quad_spans(ytr, ybl, ybr):
    """(columns, first y, past-last y) of the columns a quad of this shape covers (relative to its top-left corner)."""
    key = (ytr, ybl, ybr)
    got = _QUAD_SPANS.get(key)
    if got is None:
        if len(_QUAD_SPANS) > 6000:
            _QUAD_SPANS.clear()
        cols = list(fog_quad_columns(0, ytr, ybl, ybr, (0, 0, 0, 0)))
        got = _QUAD_SPANS[key] = (np.array([c for c, _, _ in cols], np.intp), np.array([y for _, y, _ in cols], np.intp),
                                  np.array([y + len(k) for _, y, k in cols], np.intp))
    return got


def fog_plan(levels, vy, cols, rows, shape, clip=None):
    """The fog pass of `fog_layers` in a form that applies faster: (black, layers).  `black` is the flat uint32 AND-mask of the frame words (None = nothing) for the pixels
    that end up black (a quad of level 16 all round, black rectangles included: black absorbs every other draw, so no order);
    `layers` (disjoint pixels each, applied in order) hold the uniform solid rectangles `(y0, y1, x0, x1, k)` (k = 8) and the other pixels
    as flat indices with their blend rows.  A quad goes whole to the first layer after the last one that touched any of its pixels, so the
    order of the overlapping draws is kept.  `apply_fog_plan_rgb` equals `apply_fog_layers_rgb` of `fog_layers` bit for bit
    (`tests/test_lighting.py`)."""
    H, W = shape
    left, top, right, bottom = clip or (0, 0, W, H)
    depth = np.zeros((H, W), np.int16)
    flat = depth.reshape(-1)
    layers = []
    diff = np.zeros((H + 1, W), np.int8)            # per-column +1 where a black run starts, -1 where it ends

    def layer(n):
        while len(layers) <= n:
            layers.append(([], [], []))
        return layers[n]

    for x, ytl, ytr, ybl, ybr, lv, solid in fog_runs(levels, vy, cols, rows):
        if solid:
            y0, y1 = max(ytl, top), min(ybl, bottom)
            x0, x1 = max(x, 0), min(x + 32, W)
            if y0 < y1 and x0 < x1:
                if lv[0] == 16:
                    diff[y0, x0:x1] += 1
                    diff[y1, x0:x1] -= 1
                    continue
                sl = depth[y0:y1, x0:x1]
                n = int(sl.max())
                sl[...] = n + 1
                layer(n)[0].append((y0, y1, x0, x1, lv[0]))
            continue
        if x < left or x + 32 > right:
            continue
        if not ((ytl < bottom or ytr < bottom) and (ybl >= top or ybr >= top)):
            continue
        if lv == (16, 16, 16, 16):
            cs, y0s, y1s = _quad_spans(ytr - ytl, ybl - ytl, ybr - ytl)
            y0s, y1s = np.minimum(np.maximum(y0s + ytl, top), bottom), np.minimum(np.maximum(y1s + ytl, top), bottom)
            diff[y0s, cs + x] += 1
            diff[y1s, cs + x] -= 1
            continue
        rel, ys, ks = _quad_flat(ytr - ytl, ybl - ytl, ybr - ytl, lv, W)
        if not len(ks):
            continue
        pix = rel + (ytl * W + x)
        if ytl + int(ys.min()) < top or ytl + int(ys.max()) >= bottom:
            ok = (ys + ytl >= top) & (ys + ytl < bottom)
            pix, ks = pix[ok], ks[ok]
            if not len(ks):
                continue
        n = int(flat[pix].max())
        flat[pix] = n + 1
        lay = layer(n)
        lay[1].append(pix)
        lay[2].append(ks)
    out = []
    for rects, pix, ks in layers:
        if pix:
            out.append((rects, np.concatenate(pix), np.concatenate(ks).astype(np.uint32) << 8))
        else:
            out.append((rects, np.zeros(0, np.intp), np.zeros(0, np.uint32)))
    for y in range(1, H):                           # running sum down the columns (a row-wise loop beats cumsum on int8)
        diff[y] += diff[y - 1]
    black = diff[:H] > 0
    return (np.where(black, np.uint32(0xFF000000), np.uint32(0xFFFFFFFF)).reshape(-1) if black.any() else None), out


_FOG_WORD_LUTS = []


def apply_fog_plan_rgb(words, plan, shape):
    """`apply_fog_layers_rgb` for a `fog_plan`: the black pixels are cleared by one mask, the solid rectangles go through the byte tables as
    2-D slices of the frame bytes, the other pixels as before.  `shape` = (h, w) of the frame."""
    H, W = shape
    black, layers = plan
    quantize_words_565(words)
    lut = fog_byte_lut()
    if not _FOG_WORD_LUTS:
        _FOG_WORD_LUTS.append(tuple(lut[:, ch, :].astype(np.uint32).reshape(-1) << (8 * ch) for ch in range(3)))
    lr, lg, lb = _FOG_WORD_LUTS[0]
    b8 = words.view(np.uint8).reshape(H, W, 4)
    for rects, idx, kbase in layers:
        for y0, y1, x0, x1, k in rects:
            for ch in range(3):
                v = b8[y0:y1, x0:x1, ch]
                v[...] = lut[k, ch][v]
        if len(idx):
            w = words[idx]
            out = lr[kbase | (w & 255)] | lg[kbase | ((w >> 8) & 255)] | lb[kbase | ((w >> 16) & 255)]
            words[idx] = out | (w & np.uint32(0xFF000000))
    if black is not None:
        words &= black
