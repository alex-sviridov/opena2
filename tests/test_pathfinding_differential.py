"""The optimised planner must equal the original sequential one field for field (tests/pathfinding_reference.py)."""

import random

import numpy as np
import pytest

from engine.sim import pathfinding as new
import pathfinding_reference as ref


def _grid(rnd, w, h, density, with_cost, border):
    blocked = (np.random.RandomState(rnd.randrange(1 << 30)).rand(h, w) < density).astype(np.uint8)
    if border:
        blocked[:border] = 1
        blocked[-border:] = 1
        blocked[:, :border] = 1
        blocked[:, -border:] = 1
    cost = None
    if with_cost:
        cost = np.random.RandomState(rnd.randrange(1 << 30)).randint(1, 9, (h, w)).astype(np.uint8)
        if rnd.random() < 0.3:
            cost = np.random.RandomState(rnd.randrange(1 << 30)).randint(0, 256, (h, w)).astype(np.uint8)
    return blocked, cost


def _same(a, b):
    assert a.cells == b.cells
    assert a.searched == b.searched
    assert (a.found, a.end, a.limit, a.levels, a.reason) == (b.found, b.end, b.limit, b.levels, b.reason)


@pytest.mark.parametrize("seed", range(12))
def test_random_grids_match_reference(seed):
    rnd = random.Random(seed)
    for _ in range(10):
        w, h = rnd.choice([(12, 9), (30, 30), (64, 40), (100, 100), (160, 160)])
        blocked, cost = _grid(rnd, w, h, rnd.choice([0.0, 0.1, 0.3, 0.45]), rnd.random() < 0.6,
                              rnd.choice([0, 0, 8]) if min(w, h) > 20 else 0)
        g = new.PathGrid.from_arrays(blocked, cost)
        size = rnd.choice([1, 1, 2])
        walker = rnd.random() < 0.7
        for _ in range(3):
            s = (rnd.randrange(w), rnd.randrange(h))
            t = (rnd.randrange(w), rnd.randrange(h))
            if rnd.random() < 0.15:                                     # edges of the 256 grid / map
                s = (rnd.choice([0, w - 1, 255]), rnd.choice([0, h - 1, 255]))
            if rnd.random() < 0.1:
                t = (rnd.choice([0, 255, w - 1]), rnd.choice([0, 255, h - 1]))
            human = rnd.random() < 0.5
            _same(new.plan_static(g, s, t, size=size, walker=walker, human=human),
                  ref.plan_static(g, s, t, size=size, walker=walker, human=human))
            radius = rnd.choice([None, None, 3, 12])
            _same(new.plan_dynamic(g, s, t, size=size, walker=walker, radius=radius),
                  ref.plan_dynamic(g, s, t, size=size, walker=walker, radius=radius))


def test_maze_with_wrapping_labels():
    """A long snake corridor with cost 255 pushes labels past 16 bits (wrap-around arithmetic)."""
    w = h = 40
    blocked = np.zeros((h, w), np.uint8)
    for y in range(1, h, 2):
        blocked[y, :] = 1
        blocked[y, w - 1 if (y // 2) % 2 == 0 else 0] = 0
    cost = np.full((h, w), 255, np.uint8)
    g = new.PathGrid.from_arrays(blocked, cost)
    for t in ((w - 1, h - 2), (3, 5), (0, h - 1)):
        _same(new.plan_static(g, (0, 0), t, human=True), ref.plan_static(g, (0, 0), t, human=True))
