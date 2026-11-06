"""The C blends (engine/native/blend.c) must equal the numpy blends of engine/backend_pygame/sprites.py word for word.

Random sparse entries are drawn at random places (inside, across the frame edge, outside) with and without a clip box onto a random
frame (the X byte random too: the shadow leaves it alone); both paths run on copies of the same frame.  The switch tests always run."""

import random

import numpy as np
import pytest

from engine import native
from engine.backend_pygame import sprites as S

LIB = native.load_blend()
needs_lib = pytest.mark.skipif(LIB is None, reason="native blend unavailable: %s" % native.error("blend"))


def _frame(rs, w, h):
    f = S.Frame(w, h)
    f.arr[:] = rs.randint(0, 1 << 32, (h, w), dtype=np.uint64).astype(np.uint32)
    return f


def _entry(rs, half):
    w, h = rs.randint(1, 40), rs.randint(1, 40)
    mask = rs.rand(h, w) < rs.choice([0.1, 0.5, 1.0])
    vals = None
    if half:
        vals = S.pack_rgb(rs.randint(0, 128, (h, w, 3)).astype(np.uint8))
    return S.SparseMask(mask, rs.randint(-6, 6), vals)


def _both(monkeypatch, fn, frame, *args):
    a, b = S.Frame(frame.w, frame.h), S.Frame(frame.w, frame.h)
    a.arr[:] = b.arr[:] = frame.arr
    monkeypatch.setattr(S, "_BLEND", None)
    fn(a, *args)
    monkeypatch.setattr(S, "_BLEND", LIB)
    fn(b, *args)
    return a.arr, b.arr


@needs_lib
@pytest.mark.parametrize("half", [False, True])
def test_native_blend_equals_numpy(monkeypatch, half):
    rnd = random.Random(7 + half)
    rs = np.random.RandomState(11 + half)
    for _ in range(300):
        w, h = rnd.randint(8, 90), rnd.randint(8, 90)
        frame = _frame(rs, w, h)
        entry = _entry(rs, half)
        x, y = rnd.randint(-50, w + 50), rnd.randint(-50, h + 50)
        clip = None
        if rnd.random() < 0.5:
            x0, y0 = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
            clip = (x0, y0, rnd.randint(x0 + 1, w), rnd.randint(y0 + 1, h))
        if half:
            py, nat = _both(monkeypatch, S.frame_half, frame, x, y, entry, clip)
        else:
            py, nat = _both(monkeypatch, S.frame_shadow, frame, x, y, entry, rnd.randint(0, 16), clip)
        assert np.array_equal(nat, py), (x, y, clip, w, h)


def test_native_switch(monkeypatch):
    monkeypatch.setenv("ALLODS2_NATIVE", "0")
    assert native.blend() is None
    monkeypatch.setenv("ALLODS2_NATIVE", "")
    assert native.blend() is LIB
