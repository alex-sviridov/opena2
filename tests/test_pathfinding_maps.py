"""Pathfinding on the install's maps (skipped without it): golden routes and route sanity."""

import hashlib
import json
import os

import pytest

from allods2.assets import AssetCache
from allods2.cli import open_map
from engine.sim.movement import path_grid
from engine.sim.pathfinding import chebyshev, plan_static
from engine.world import World

from helpers import GFS

pytestmark = pytest.mark.skipif(not GFS, reason="game files not present")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD = json.load(open(os.path.join(ROOT, "tests", "golden.json")))["paths"]
ASSETS = AssetCache(GFS) if GFS else None
_worlds = {}


def route(key):
    spec, rest = key.split(":")
    a, b = rest.split(">")
    s, t = tuple(map(int, a.split(","))), tuple(map(int, b.split(",")))
    if spec not in _worlds:
        _worlds[spec] = World.from_map(open_map(spec, GFS), ASSETS)
    w = _worlds[spec]
    return w, s, t, plan_static(path_grid(w, 1), s, t, human=True)


@pytest.mark.parametrize("key", sorted(GOLD))
def test_golden_route(key):
    w, s, t, r = route(key)
    g = GOLD[key]
    assert (r.found, len(r.cells)) == (g["found"], g["len"])
    assert hashlib.sha256(json.dumps(r.cells).encode("ascii")).hexdigest() == g["sha256"]


@pytest.mark.parametrize("key", sorted(GOLD))
def test_route_is_walkable_and_connected(key):
    w, s, t, r = route(key)
    assert r.found and r.cells[-1] == t
    prev = s
    for c in r.cells:
        assert chebyshev(prev, c) == 1 and not w.blocked(c[0], c[1], 1)
        prev = c
    assert len(r.cells) >= chebyshev(s, t)
