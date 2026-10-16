"""Engine view layer: coordinates, camera, visible range, draw list, ui, sim (headless, no game files)."""

import numpy as np
import pytest

from engine.sim import CommandQueue, Simulation, tick_period_ms
from engine.ui import ScrollInput
from engine.view import Camera, Projection, build_draw_list
from engine.world import World

W, H = 24, 20


def heights(seed=1, hi=60):
    rng = np.random.default_rng(seed)
    return rng.integers(0, hi, (H, W)).astype(np.int8)


def test_tick_period_is_confirmed_table():
    assert [tick_period_ms(s) for s in range(9)] == [125, 100, 83, 71, 62, 50, 41, 35, 31]
    assert tick_period_ms(99) == 31 and tick_period_ms(-1) == 125


def test_simulation_step_counts_ticks_and_runs_systems():
    w = World(np.zeros((2, 2)), np.zeros((2, 2)))
    seen = []
    sim = Simulation(w, [lambda world, cmds: seen.append((world.tick, list(cmds)))])
    q = CommandQueue()
    q.put("a")
    sim.step(q.drain())
    sim.step(q.drain())
    assert w.tick == 2 and seen == [(0, ["a"]), (1, [])] and len(q) == 0


def test_world_ids_are_integers():
    w = World(np.zeros((2, 2)), np.zeros((2, 2)))
    assert w.new_entity() == 1 and w.new_entity("x") == 2


@pytest.mark.parametrize("flat", [True, False])
def test_cell_world_round_trip(flat):
    h = np.zeros((H, W), np.int8) if flat else heights()
    p = Projection(h)
    for row in range(H):
        for col in range(W):
            wx, wy = p.cell_center_world(col, row)
            got = p.world_to_cell(wx, wy)
            if got != (col, row):
                # a lower row may overdraw this cell's centre (cliff); then it is that cell's pixel
                top, bot = p.column_span(*got, wx - got[0] * 32)
                assert got[1] > row and top <= wy < bot
    # origin vertex
    assert p.cell_to_world(3, 2) == (96, 64 - int(h[2, 3]))


def test_flat_cell_origin_and_points():
    p = Projection(np.zeros((H, W), np.int8))
    assert p.world_to_cell(0, 0) == (0, 0)
    assert p.world_to_cell(31, 31) == (0, 0)
    assert p.world_to_cell(32, 32) == (1, 1)
    assert p.world_to_cell(-1, 0) is None and p.world_to_cell(W * 32, 0) is None


def test_world_to_cell_with_height_uses_vertex_offset():
    h = np.zeros((H, W), np.int8)
    h[5, 4] = 20                                   # vertex (4, 5) raised 20 px
    p = Projection(h)
    assert p.cell_to_world(4, 5) == (128, 160 - 20)
    # world y 150 at column 4: above the flat grid row line of 160 -> row 5 (raised corner)
    assert p.world_to_cell(128, 150) == (4, 5)


def test_camera_clamps_at_all_edges():
    c = Camera(100, 80, 10, 10)                    # map 320 x 320 px
    c.move_to(-50, -50)
    assert (c.x, c.y) == (0, 0)
    c.move_to(10000, -5)
    assert (c.x, c.y) == (220, 0)
    c.move_to(-5, 10000)
    assert (c.x, c.y) == (0, 240)
    c.move_to(10000, 10000)
    assert (c.x, c.y) == (220, 240)
    c.move_by(-1000, 0)
    assert c.x == 0
    c.move_to(12.7, 3.2)
    assert (c.ix, c.iy) == (12, 3)


def test_camera_larger_viewport_than_map_sits_at_zero():
    c = Camera(1000, 1000, 4, 4, 50, 50)
    assert (c.x, c.y) == (0, 0)


def test_visible_range_at_corners():
    h = heights()
    p = Projection(h)
    c = Camera(160, 96, W, H)
    assert p.visible_cells(c) == (0, 5, 0, -(-(96 + p.hmax) // 32))      # top-left
    c.move_to(1e6, 1e6)
    x0, x1, y0, y1 = p.visible_cells(c)
    assert (x1, y1) == (W, H) and x0 == (W * 32 - 160) // 32
    assert y0 == (H * 32 - 96 + p.hmin) // 32
    c.move_to(0, 1e6)
    assert p.visible_cells(c)[:2] == (0, 5) and p.visible_cells(c)[3] == H
    c.move_to(1e6, 0)
    assert p.visible_cells(c)[1] == W and p.visible_cells(c)[2] == 0


def test_visible_range_is_a_superset_of_cells_touching_the_viewport():
    h = heights(3, 120)
    p = Projection(h)
    c = Camera(100, 90, W, H, 77, 205)
    x0, x1, y0, y1 = p.visible_cells(c)
    for row in range(H):
        for col in range(W):
            for px in (0, 15, 31):
                top, bot = p.column_span(col, row, px)
                wx = col * 32 + px
                touches = bot > top and c.iy <= bot - 1 and top < c.iy + 90 and c.ix <= wx < c.ix + 100
                if touches:
                    assert x0 <= col < x1 and y0 <= row < y1


def test_scroll_input_moves_camera_and_clamps():
    s = ScrollInput(speed=100, edge=4)
    c = Camera(100, 100, 10, 10, 50, 50)
    s.update(c, 500, {"right", "down"})
    assert (c.x, c.y) == (100, 100)
    s.update(c, 10000, {"left"})
    assert c.x == 0
    c.move_to(10, 10)
    s.update(c, 1000, set(), mouse=(99, 50))        # right edge
    assert (c.x, c.y) == (110, 10)
    s.update(c, 1000, set(), mouse=(50, 2))         # top edge
    assert c.y == 0
    assert s.direction({"left"}, (0, 50), 100, 100) == (-1, 0)       # clamps to one step
    assert s.direction(set(), None, 100, 100) == (0, 0)


def test_draw_list_row_order_and_water_phase():
    from engine.view.terrain_view import TerrainView
    from allods2.graphics.terrain import TerrainSet, cell_value
    cells = np.full((H, W), cell_value(0, 0, 0), np.uint16)
    cells[2, 2] = cell_value(9, 0, 0)
    w = World(cells, heights())
    tv = TerrainView(w, TerrainSet({}, np.zeros((128, 32), np.uint8), np.zeros((256, 3), np.uint8)))
    c = Camera(96, 96, W, H, 32, 32)
    items = build_draw_list(tv, c, 0)
    order = [(i.row, i.col) for i in items]
    assert order == sorted(order)
    assert all(i.sx == i.col * 32 - 32 for i in items)
    water = {i.key for i in build_draw_list(tv, c, 0) if (i.col, i.row) == (2, 2)}
    assert {(i.phase) for t in range(0, 16) for i in build_draw_list(tv, c, t) if (i.col, i.row) == (2, 2)} == {0, 1, 2, 3}
    assert all(i.phase == 0 for i in build_draw_list(tv, c, 7) if (i.col, i.row) != (2, 2))
    assert water
