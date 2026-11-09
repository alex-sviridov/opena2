"""Positional mix and volume maths (docs/engine/audio.md 3.2-3.3, formats/sound.md 3.1).  Pure, no pygame."""

import math
from typing import NamedTuple

MIN_MB = -10000                 # DirectSound's silence floor; a play at -10000 still takes a voice
UI_PRIORITY = 0xDC              # UI sounds beat every positional priority (max 100) and the speech 0x80 (`0x45aa2f` callers)
DEFAULT_MB = -700               # registry default of the three bus values (`0x476130`)


class View(NamedTuple):
    """The camera in cells: top-left `x`, `y` and the size `w`, `h` (view +0x5c..+0x68)."""
    x: int
    y: int
    w: int
    h: int


class Mix(NamedTuple):
    att: int                    # attenuation, mB, <= 0
    pan: int                    # -10000..10000 (screen edge +-2000)
    priority: int               # (10000 - |att|) / 100, 0..100


def positional(X, Y, view):
    """`0x41b1f8(X, Y)` (CONFIRMED): world position in 1/256 cell against the view's centre; no cutoff, no visibility test."""
    cx = (view.x << 8) + (view.w << 7)
    cy = (view.y << 8) + (view.h << 7)
    dx, dy = X - cx, Y - cy
    pan = int(dx * 4000 / (view.w << 8)) if view.w else 0
    pan = max(-10000, min(10000, pan))
    att = int(max(-(math.exp(math.sqrt(dx * dx + dy * dy) / 2048) - 1) * 100, MIN_MB)) if (dx * dx + dy * dy) < 1e9 else MIN_MB
    return Mix(att, pan, (10000 - abs(att)) // 100)


def flat(priority=UI_PRIORITY):
    """A non-positional play: pan 0, no attenuation."""
    return Mix(0, 0, priority)


def volume_mb(att, bus_mb):
    """`0x45aa2f`: attenuation plus the bus value, clamped to -10000..0."""
    return max(MIN_MB, min(0, att + bus_mb))


def gain(mb):
    """Linear gain of a millibel value (`10^(mB / 2000)`: amplitude, 100 mB = 1 dB... = 10^(mB/2000))."""
    return 10.0 ** (max(MIN_MB, min(0, mb)) / 2000.0)


def pan_gains(mb, pan):
    """(left, right) linear gains: the louder side keeps the volume, the other is cut by `|pan|` mB (DirectSound's pan law, INFERRED audio.md 5)."""
    g = gain(mb)
    return g * 10.0 ** (-max(pan, 0) / 2000.0), g * 10.0 ** (-max(-pan, 0) / 2000.0)


def percent_to_mb(p):
    """Slider percent -> bus mB: `-10000 * ((100 - p) / 100)^2` (`0x45b3a3`, INFERRED); 74 % = -676 mB, about the exe's -700 default."""
    p = max(0, min(100, p))
    return int(round(-10000 * ((100 - p) / 100.0) ** 2))


def mb_to_percent(mb):
    """Inverse of `percent_to_mb` (rounded)."""
    return int(round(100 - 100 * math.sqrt(min(10000, max(0, -mb)) / 10000.0)))
