"""K11: positional mix and volume maths (docs/engine/audio.md 3.2, 3.3, 6)."""

import math

from engine.audio.mix import (Mix, View, flat, gain, mb_to_percent, pan_gains, percent_to_mb, positional, volume_mb)

V = View(10, 10, 20, 15)                  # centre = (20 cells, 17.5 cells)
CX, CY = (10 << 8) + (20 << 7), (10 << 8) + (15 << 7)


def test_at_the_centre_nothing_is_attenuated():
    assert positional(CX, CY, V) == Mix(0, 0, 100)


def test_distance_attenuation_known_points():
    assert positional(CX + 8 * 256, CY, V).att == -171                  # 8 cells: -1.7 dB
    assert positional(CX, CY + 16 * 256, V).att == -638                 # 16 cells: -6.4 dB
    assert positional(CX + 30 * 256, CY, V).att == int(-(math.exp(30 * 256 / 2048) - 1) * 100) and -4200 < positional(CX + 30 * 256, CY, V).att < -4100
    assert positional(CX + 37 * 256, CY, V).att == -10000 and positional(CX + 100 * 256, CY, V).att == -10000
    assert positional(CX + 5000 * 256, CY, V).att == -10000


def test_dy_is_not_scaled_and_priority_follows_the_attenuation():
    a = positional(CX, CY + 8 * 256, V)
    assert a.att == positional(CX + 8 * 256, CY, V).att and a.pan == 0
    assert positional(CX + 8 * 256, CY, V).priority == (10000 - 171) // 100 == 98
    assert positional(CX + 40 * 256, CY, V).priority == 0


def test_pan_edge_is_2000_and_clamps_at_10000():
    assert positional(CX + (V.w << 7), CY, V).pan == 2000
    assert positional(CX - (V.w << 7), CY, V).pan == -2000
    assert positional(CX + (V.w << 8) * 5, CY, V).pan == 10000
    assert positional(CX - (V.w << 8) * 9, CY, V).pan == -10000


def test_flat_and_volume_clamp():
    assert flat() == Mix(0, 0, 0xDC) and flat(100).priority == 100
    assert volume_mb(-171, -700) == -871 and volume_mb(-9500, -700) == -10000 and volume_mb(500, 0) == 0


def test_mb_to_gain_and_pan_law():
    assert gain(0) == 1.0 and abs(gain(-2000) - 0.1) < 1e-9 and gain(-20000) == gain(-10000)
    left, right = pan_gains(-600, 0)
    assert left == right == gain(-600)
    left, right = pan_gains(0, 2000)
    assert right == 1.0 and abs(left - 0.1) < 1e-9                       # pan right: the left side loses |pan| mB
    left, right = pan_gains(0, -4000)
    assert left == 1.0 and abs(right - 0.01) < 1e-9


def test_slider_curve():
    assert percent_to_mb(100) == 0 and percent_to_mb(0) == -10000
    assert percent_to_mb(74) == -676 and -750 < percent_to_mb(74) < -650         # about the exe's -700 default
    assert all(mb_to_percent(percent_to_mb(p)) == p for p in range(0, 101))
    assert percent_to_mb(150) == 0 and percent_to_mb(-5) == -10000
