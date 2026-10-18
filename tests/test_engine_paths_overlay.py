"""Path debug overlay (view): the draw-list items for a selected unit with a plan; no pygame."""

import numpy as np

from engine.sim import MoveTo, Simulation
from engine.ui import DebugFlags
from engine.view import Camera
from engine.view.drawlist import _Ctx, _path_items
from engine.world import UNIT_ID_BASE, Unit, World


def test_flag_parse_and_items():
    assert DebugFlags.parse("paths").paths and DebugFlags.parse("paths").any()
    w = World(np.zeros((32, 32), np.uint16), np.zeros((32, 32), np.int8), "syn")
    w._cost = np.full((32, 32), 8, np.uint8)
    u = Unit(UNIT_ID_BASE + 1, 1, 1, 10, 10, uid=1, hp=5, hp_max=5, speed_mod=24)
    w.add_unit(u)
    sim = Simulation(w)
    sim.step([MoveTo(u.id, 20, 10)])
    cam = Camera(1024, 768, 32, 32, 0, 0)

    class A:                                    # the context only needs the world here
        pass

    ctx = _Ctx(w, cam, 0, None, __import__("engine.view.drawlist", fromlist=["DrawOptions"]).DrawOptions())
    kinds = {i.kind for i in _path_items(ctx, (u.id,))}
    assert {"searched", "path", "hop"} <= kinds
    assert not _path_items(ctx, ())
