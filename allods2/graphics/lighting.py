"""Time of day and light levels; spec: docs/mechanics/lighting.md.

Light values are shade-table row numbers: row 0 is the brightest
(see palette.shade_table).  Terrain uses 96-row BRIGHT32 tables, objects
16-row BRIGHT2 tables.
"""

import math
from dataclasses import dataclass

import numpy as np

# Doubles as stored in allods2.exe .rdata (not exact pi fractions).
_PI = 3.1415926                  # 0x5d79c8
_QUARTER = 0.78539815            # 0x5d79f0 / -0x5d79e0
_SUN_ELEVATION = 0.5235987666666667   # 0x5d8c38, ~pi/6
_CELL = 32.0                     # 0x5d8c30
_LIGHT_MAX = 94.0                # 0x5d8c40


@dataclass(frozen=True)
class Daylight:
    """Globals set by FUN_0047a208 (addresses in allods2.exe)."""
    tint: tuple        # 0x62c888..a, (R, G, B) added before palette conversion
    ambient: int       # 0x62c88c
    diffuse: int       # 0x62c890
    shadow1: int       # 0x62c894, shadow darkness level (dst * (16 - k) / 16)
    shadow2: int       # 0x62c898, lighter shadow level
    angle: float       # 0x62c8a0, sun azimuth in radians


def daylight(minutes, enabled=True):
    """Lighting state at game time `minutes` (0 = midnight).  `enabled` is
    the day/night option (DAT_0062c938); off gives the fixed default."""
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
    """Per-vertex terrain light rows (FUN_004ad552) from a (h, w) array of
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
    (FUN_00404ad1): ambient >> 2."""
    return ambient >> 2


# --- light map (view + 0xa8): 0 = brightest, 0xFF = no light ----------------

NO_LIGHT = 0xFF

# FUN_004040e2: static map light value by animation phase (flags >> 1), radius 1.
STATIC_LIGHT_PHASES = (0x24, 0x18, 0x0C, 0, 0x0C, 0, 0x0C, 0, 0x14, 0x1C, 0x24)
# The list view+0xa94 holds burning cells (fire explosion / server message
# 0x4155cd), not static lights: the same table, by counter >> 1.
BURNING_LIGHT_PHASES = STATIC_LIGHT_PHASES
BURN_TICKS = 0x16           # FUN_0040c199 drops an entry when its counter reaches 22


def structure_light_value(pulse, clock):
    """Light-map value a structure with LightRadius writes (FUN_00467725):
    0x20 without LightPulse, else a pulse of period 2 * pulse ticks of the
    view clock."""
    if not pulse:
        return 0x20
    m = clock % (2 * pulse)
    if m >= pulse:
        return 0x20 + ((pulse - m) >> 1) - clock % pulse
    return 0x20 - ((pulse - m) >> 1) + clock % pulse


def structure_light_vertices(x0, y0, x1, y1, radius):
    """Light-map vertices FUN_00467725 writes for a structure whose view
    cell rectangle is (x0, y0)-(x1, y1): x in [x0 + R - 1, x1 + R], y the
    same.  With R = 1 (every record in the data) these are exactly the
    footprint's corner vertices; the range is not centred for other R."""
    return [(x, y) for y in range(y0 + radius - 1, y1 + radius + 1)
            for x in range(x0 + radius - 1, x1 + radius + 1)]

# FUN_00472562: projectile type (projectiles.reg ID) -> (radius, value).
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
    """FUN_004063c5: write `value` at every vertex (cx+dx, cy+dy) with
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
    """FUN_00405d9b: a lit vertex uses the brighter of the terrain light
    and the light map."""
    return terrain if light == NO_LIGHT else min(terrain, light)


def object_light_row_lit(corners, ambient):
    """FUN_00404ad1 step 3: row for a cell from its four light-map corners,
    or None when all four are 0xFF (the cell keeps its default)."""
    vals = [max(v - 32, 0) for v in corners]
    if sum(vals) == 4 * 223:
        return None
    total = sum(ambient if v == 223 else v for v in vals)
    return min(ambient >> 2, total >> 4)


# --- shadows (FUN_0045a33f, FUN_004abba9) ------------------------------------

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
_FOG_K = 0x10000           # DAT_00625650: entries per blend-table row (bytes = 2·K)


def fog_level(bits):
    """FUN_004040e2: a cell's fog level from its tile visibility bits."""
    b = bits & 0xC000
    return FOG_SEEN if b == 0xC000 else FOG_EXPLORED if b == 0x8000 else FOG_UNSEEN


def fog_shade(px, k, bits=(5, 6, 5)):
    """Blend-table row k (FUN_0045752b) on 16-bit pixels: every channel
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
    """One fog quad as FUN_0045d22b draws it: yields (c, y_top, rows) for
    each column with pixels; rows[i] is the blend row at y_top + i.

    Edges step like the terrain blit (terrain.edge_offsets).  The levels
    (tl, tr, bl, br) walk linearly along x on the top and bottom edges,
    then down each column; a pixel takes the row its walk value + ½ falls
    in.  Uniform levels give that level everywhere, so this also describes
    the solid fast paths (FUN_0045cc14/cd1d black, FUN_0045d58c/d7a0 half)
    and the flat variant FUN_0045d077."""
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
    """The fog pass of the view draw (0x40a111-0x40a663) as a list of
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
