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
    shadow1: int       # 0x62c894, passed to sprite shadow draws (meaning open)
    shadow2: int       # 0x62c898
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
