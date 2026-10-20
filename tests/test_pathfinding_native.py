"""The C planner (engine/native/planner.c) must equal the Python planner field for field (spec simulation.md 7.5).

Every PathResult field is compared (cells, found, end, searched, limit, levels, reason).  The native cases
skip only when the library cannot be built here; the switch tests always run."""

import os
import random

import numpy as np
import pytest

from engine import native
from engine.sim import pathfinding as pf

from helpers import GFS, needs_data

LIB = native.load_planner()
needs_lib = pytest.mark.skipif(LIB is None, reason="native planner unavailable: %s" % native.error())


def _fields(r):
    return (r.cells, r.found, r.end, r.searched, r.limit, r.levels, r.reason)


def _both(monkeypatch, fn, *a, **k):
    """(Python result, native result) of one plan."""
    monkeypatch.setattr(native, "planner", lambda: None)
    py = fn(*a, **k)
    monkeypatch.setattr(native, "planner", lambda: LIB)
    nat = fn(*a, **k)
    return py, nat


def _check(monkeypatch, fn, *a, **k):
    py, nat = _both(monkeypatch, fn, *a, **k)
    assert _fields(nat) == _fields(py), (fn.__name__, a[1:], k)
    return py


def _grid(rnd, w, h):
    rs = np.random.RandomState(rnd.randrange(1 << 30))
    blocked = (rs.rand(h, w) < rnd.choice([0.0, 0.1, 0.3, 0.45])).astype(np.uint8)
    if rnd.random() < 0.4 and min(w, h) > 20:
        b = 8
        blocked[:b] = blocked[-b:] = 1
        blocked[:, :b] = blocked[:, -b:] = 1
    cost = None
    if rnd.random() < 0.6:
        cost = rs.randint(0, 256 if rnd.random() < 0.3 else 9, (h, w)).astype(np.uint8)
    return pf.PathGrid.from_arrays(blocked, cost)


@needs_lib
@pytest.mark.parametrize("seed", range(16))
def test_random_grids(monkeypatch, seed):
    rnd = random.Random(1000 + seed)
    for _ in range(8):
        w, h = rnd.choice([(12, 9), (30, 30), (64, 40), (100, 100), (160, 160), (256, 256)])
        g = _grid(rnd, w, h)
        size = rnd.choice([1, 1, 2, 3])
        walker = rnd.random() < 0.7
        for _ in range(3):
            s = (rnd.randrange(w), rnd.randrange(h))
            t = (rnd.randrange(w), rnd.randrange(h))
            if rnd.random() < 0.15:                                     # edges of the 256 grid / map
                s = (rnd.choice([0, w - 1, 255]), rnd.choice([0, h - 1, 255]))
            if rnd.random() < 0.1:
                t = (rnd.choice([0, 255, w - 1]), rnd.choice([0, 255, h - 1]))
            cfg = pf.PathConfig(static_scan_ahead=rnd.choice([5, 0, 40]), dynamic_scan_ahead=rnd.choice([3, 1, 30]))
            _check(monkeypatch, pf.plan_static, g, s, t, size=size, walker=walker, human=rnd.random() < 0.5, cfg=cfg)
            _check(monkeypatch, pf.plan_dynamic, g, s, t, size=size, walker=walker, cfg=cfg,
                   radius=rnd.choice([None, None, 0, 3, 12, 40]))
            f, tf = pf.Foot(*s, size, rnd.randrange(256), rnd.randrange(256)), pf.Foot(*t, rnd.choice([1, 2]))
            _check(monkeypatch, pf.plan_dynamic, g, s, t, size=size, walker=walker, follow=(f, tf))


@needs_lib
def test_wrapping_labels_and_too_long(monkeypatch):
    """Cost 255 snake: labels past 16 bits; a start outside the walk window 8..248 gives 'too long'."""
    w = h = 120
    blocked = np.zeros((h, w), np.uint8)
    for y in range(1, h, 2):
        blocked[y, :] = 1
        blocked[y, w - 1 if (y // 2) % 2 == 0 else 0] = 0
    for cost in (np.full((h, w), 255, np.uint8), np.full((h, w), 1, np.uint8), None):
        g = pf.PathGrid.from_arrays(blocked, cost)
        for t in ((w - 1, h - 2), (3, 5), (0, h - 1), (60, 100), (5, 118)):
            _check(monkeypatch, pf.plan_static, g, (0, 0), t, human=True)
            _check(monkeypatch, pf.plan_dynamic, g, (0, 0), t, radius=30)
    g = pf.PathGrid.from_arrays(np.zeros((64, 64), np.uint8))
    assert _check(monkeypatch, pf.plan_static, g, (3, 3), (30, 30)).reason == "too long"


@needs_lib
def test_open_256_grid_wraps_indices(monkeypatch):
    """No border at all: neighbour indices wrap round the 64 Ki cell space as in the exe."""
    g = pf.PathGrid.from_arrays(np.zeros((256, 256), np.uint8))
    for s, t in (((0, 0), (255, 255)), ((255, 0), (0, 255)), ((0, 128), (255, 128)), ((3, 255), (3, 0))):
        for size in (1, 2):
            _check(monkeypatch, pf.plan_static, g, s, t, size=size, walker=False, human=True)
            _check(monkeypatch, pf.plan_dynamic, g, s, t, size=size, walker=False)


@needs_lib
def test_live_layer_from_with_blocked_and_bytes_layers(monkeypatch):
    rnd = random.Random(5)
    g = _grid(rnd, 64, 64)
    live = g.with_blocked([(rnd.randrange(64), rnd.randrange(64)) for _ in range(200)])
    frozen = pf.PathGrid(bytes(live.blocked), None if live.cost is None else bytes(live.cost), 64, 64)
    for _ in range(20):
        s, t = (rnd.randrange(64), rnd.randrange(64)), (rnd.randrange(64), rnd.randrange(64))
        a = _check(monkeypatch, pf.plan_dynamic, live, s, t)
        b = _check(monkeypatch, pf.plan_dynamic, frozen, s, t)
        assert _fields(a) == _fields(b)


def test_out_of_grid_cells_use_python(monkeypatch):
    """Cells outside the 256 grid never reach the C code (the Python planner answers)."""
    calls = []

    class Spy:
        def a2_plan(self, *a):
            calls.append(a)
            raise AssertionError("must not be called")
    monkeypatch.setattr(native, "planner", lambda: Spy())
    g = pf.PathGrid.from_arrays(np.zeros((20, 20), np.uint8))
    pf.plan_dynamic(g, (-1, 5), (5, 5))
    assert not pf._native_ok(g, (256, 5), (5, 5), None)
    assert not pf._native_ok(g, (5, -1), (5, 5), None)
    assert pf._native_ok(g, (5, 5), (255, 0), g.cost)
    assert calls == []


def test_switch_off_means_python(monkeypatch):
    monkeypatch.setenv("ALLODS2_NATIVE", "0")
    assert native.planner() is None


def test_switch_required_raises_when_unavailable(monkeypatch):
    monkeypatch.setenv("ALLODS2_NATIVE", "1")
    monkeypatch.setitem(native._cache, "planner", None)
    monkeypatch.setitem(native._errors, "planner", "test")
    with pytest.raises(RuntimeError):
        native.planner()
    monkeypatch.setenv("ALLODS2_NATIVE", "")
    assert native.planner() is None                                     # auto: silently Python


def test_build_failure_is_silent(monkeypatch, tmp_path):
    """No compiler: load_planner gives None and records why; the planner still answers."""
    monkeypatch.setattr(native, "_compiler", lambda: None)
    monkeypatch.setattr(native, "_out_dirs", lambda: iter([str(tmp_path)]))
    monkeypatch.delitem(native._cache, "planner", raising=False)
    monkeypatch.delitem(native._errors, "planner", raising=False)
    monkeypatch.delenv("ALLODS2_NATIVE", raising=False)
    assert native.load_planner() is None and "compiler" in native.error()
    g = pf.PathGrid.from_arrays(np.zeros((30, 30), np.uint8))
    assert pf.plan_static(g, (10, 10), (20, 20)).found


@needs_lib
def test_build_skips_up_to_date_library_and_rebuilds_stale(tmp_path, monkeypatch):
    src = tmp_path / "x.c"
    src.write_text("int a2_x(void) { return 7; }\n")
    monkeypatch.setattr(native, "_out_dirs", lambda: iter([str(tmp_path)]))
    lib = native.build(str(src), "_x")
    m0 = os.path.getmtime(lib)
    assert native.build(str(src), "_x") == lib and os.path.getmtime(lib) == m0
    os.utime(src, (m0 + 10, m0 + 10))
    native.build(str(src), "_x")
    assert os.path.getmtime(lib) >= m0 and not [p for p in os.listdir(tmp_path) if p.endswith(".tmp")]


# --- the campaign maps -------------------------------------------------------------------------------------------

MAPS = ("scenario/10.alm", "scenario/32.alm", "scenario/53.alm", "scenario/110.alm")


@needs_lib
@needs_data
@pytest.mark.parametrize("spec", MAPS)
def test_campaign_maps(monkeypatch, spec):
    from allods2.assets import AssetCache
    from allods2.cli import open_map
    from engine.sim.movement import path_grid
    from engine.world import World
    w = World.from_map(open_map(spec, GFS), AssetCache(GFS))
    rnd = random.Random(spec)
    for move_type in (1, 2, 3):
        g = path_grid(w, move_type)
        free = [(x, y) for y in range(8, w.height - 8) for x in range(8, w.width - 8) if not g.is_blocked(x, y)]
        units = [(u.x, u.y) for u in w.units.values()]
        pairs = 25 if move_type == 1 else 8
        for _ in range(pairs):
            s = rnd.choice(free)
            t = rnd.choice(free) if rnd.random() < 0.8 else (rnd.randrange(w.width), rnd.randrange(w.height))
            size = rnd.choice([1, 1, 1, 2])
            walker = move_type == 1
            _check(monkeypatch, pf.plan_static, g, s, t, size=size, walker=walker, human=rnd.random() < 0.5)
            near = (min(max(s[0] + rnd.randint(-6, 6), 0), 255), min(max(s[1] + rnd.randint(-6, 6), 0), 255))
            live = g.with_blocked(rnd.sample(units, min(len(units), 60)))
            _check(monkeypatch, pf.plan_dynamic, live, s, near, size=size, walker=walker)
            _check(monkeypatch, pf.plan_dynamic, live, s, near, size=size, walker=walker,
                   follow=(pf.Foot(*s, size), pf.Foot(*near, rnd.choice([1, 2]))))
