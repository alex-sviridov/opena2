"""Path planners (H2): synthetic grids, always run.  Spec: docs/engine/simulation.md section 7.

Pictures are embedded at (OFF, OFF) in a blocked arena like the exe's 8-cell border:
'#' blocked, '.' free, 'S' start, 'T' target, 'B' a blocked target."""

import pytest

from engine.sim.pathfinding import (DEFAULT_CONFIG, GRID, PathGrid, chebyshev, plan_dynamic,
                                    plan_static)

import numpy as np

OFF = 8


def picture(rows, cost=None):
    """(PathGrid, start, target) from ASCII rows; coordinates are arena coordinates."""
    h, w = len(rows), max(len(r) for r in rows)
    blocked = np.ones((h + 2 * OFF, w + 2 * OFF), bool)
    start = target = None
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            blocked[y + OFF, x + OFF] = ch in "#B"
            if ch == "B":
                target = (x + OFF, y + OFF)
            if ch == "S":
                start = (x + OFF, y + OFF)
            if ch == "T":
                target = (x + OFF, y + OFF)
    costs = None
    if cost is not None:
        costs = np.full(blocked.shape, cost, np.uint8)
    return PathGrid.from_arrays(blocked, costs), start, target


def at(x, y):
    return (x + OFF, y + OFF)


def legal(res, start):
    """Consecutive cells of a route are neighbours."""
    prev = start
    for c in res.cells:
        assert chebyshev(prev, c) == 1
        prev = c


def test_straight_line():
    g, s, t = picture(["S....T"])
    r = plan_static(g, s, t)
    assert r.found and r.end == t
    assert r.cells == [at(i, 0) for i in range(1, 6)]


def test_start_equals_target_is_empty():
    g, s, _ = picture(["S...."])
    assert plan_static(g, s, s).cells == []


def test_around_a_wall():
    g, s, t = picture(["S.#..T",
                       "..#...",
                       "..#...",
                       "......"])
    r = plan_static(g, s, t)
    assert r.found
    legal(r, s)
    assert all(not g.is_blocked(*c) for c in r.cells)
    assert at(2, 3) in r.cells                      # the only gap
    assert r.cells[-1] == t


def test_diagonal_gap_is_allowed_no_corner_rule():
    # the diagonal step tests only its own target cell (FUN_0055d010)
    g, s, t = picture(["S#",
                       "#T"])
    r = plan_static(g, s, t)
    assert r.found and r.cells == [t]


def test_open_ground_route_diagonals_first():
    # worked by hand from the tie rule (spec 7.1): backward walk takes the last orthogonal tie
    for walker_cost in (None, 8):
        g, s, t = picture(["S....", ".....", "....T"], cost=walker_cost)
        r = plan_static(g, s, t, walker=walker_cost is not None)
        assert r.cells == [at(1, 1), at(2, 2), at(3, 2), at(4, 2)]
    g, s, t = picture(["S..", "...", "...", "..T"][:3] + ["..T"])
    # transposed target (2, 4)
    g, s, t = picture(["S..", "...", "...", "...", "..T"])
    assert plan_static(g, s, t).cells == [at(1, 1), at(2, 2), at(2, 3), at(2, 4)]


def test_costs_steer_a_walker():
    rows = ["S.........T",
            "..........."]
    blocked = np.ones((2 + 2 * OFF, 11 + 2 * OFF), bool)
    blocked[OFF:OFF + 2, OFF:OFF + 11] = False
    cost = np.full(blocked.shape, 8, np.uint8)
    cost[OFF, OFF + 1:OFF + 10] = 30                # expensive top row between the ends
    g = PathGrid.from_arrays(blocked, cost)
    s, t = at(0, 0), at(10, 0)
    r = plan_static(g, s, t, walker=True)
    assert at(5, 1) in r.cells and at(5, 0) not in r.cells
    flat = plan_static(g, s, t, walker=False)       # costs are ignored for non-walkers
    assert flat.cells == [at(i, 0) for i in range(1, 11)]


def test_unreachable_target_in_a_lake_falls_back_to_the_cheapest_shore_cell():
    rows = ["S.........",
            "..........",
            "...#####..",
            "...#####..",
            "...##T##..",
            "...#####..",
            "...#####..",
            ".........."]
    g, s, t = picture(rows)
    r = plan_static(g, s, t)
    assert not r.found and r.reason == "fallback"
    # radius = dist>>2 + 4 = 2 + 4 = 6: rings 1, 2 are lake, ring 3 is the first with labelled cells;
    # the cheapest of them is the one nearest the start
    assert chebyshev(r.end, t) == 3
    assert r.end == at(2, 1) or r.end == at(2, 2) or r.end == at(2, 3) or r.end[0] == t[0] - 3
    assert r.cells[-1] == r.end
    legal(r, s)


def test_unreachable_target_with_no_shore_in_range_gives_no_path():
    n = 15
    rows = ["." * n] + ["." + "#" * (n - 2) + "."] * (n - 2) + ["." * n]
    rows[0] = "S" + rows[0][1:]
    rows[7] = rows[7][:7] + "T" + rows[7][8:]
    g, s, t = picture(rows)
    r = plan_static(g, s, t, human=False)
    # dist 7: radius 7>>2 + 4 = 5 -> rings 1..4 around the target are all lake (the shore is 6 cells away)
    assert r.cells == [] and r.reason == "unreachable"


def test_search_limit_ai_stops_short_human_walks_the_detour():
    n = 40
    rows = ["S" + "." * 9 + "T"] + ["." * 11] * 0
    blocked = np.ones((n + 2 * OFF, 11 + 2 * OFF), bool)
    blocked[OFF:OFF + n, OFF:OFF + 11] = False
    blocked[OFF:OFF + n - 1, OFF + 5] = True        # wall, gap only at the bottom
    g = PathGrid.from_arrays(blocked)
    s, t = at(0, 0), at(10, 0)
    ai = plan_static(g, s, t, human=False)
    assert not ai.found and ai.limit == 10 + min(DEFAULT_CONFIG.static_scan_ahead, 10 >> 2)
    human = plan_static(g, s, t, human=True)
    assert human.found and human.limit == 1000 and human.cells[-1] == t
    assert at(5, n - 1) in human.cells


def test_human_limit_needs_a_free_target():
    g, s, t = picture(["S....#T"])
    # target free but cut off: the unbounded search runs dry, the fallback takes the labelled cell of ring 2
    r = plan_static(g, s, t, human=True)
    assert not r.found and r.limit == 1000 and r.end == at(4, 0)
    g, s, t = picture(["S....#", "......", "###..T"])
    assert plan_static(g, s, t, human=True).found


def test_target_inside_a_blocked_area():
    g, s, t = picture(["S......",
                       ".......",
                       "..###..",
                       "..#B#..",
                       "..###.."])
    r = plan_static(g, s, t)
    assert not r.found                              # the target cell is blocked: never labelled
    assert r.reason == "fallback" and chebyshev(r.end, t) == 2


def test_sized_unit_needs_a_wide_gap():
    one_row = ["S.##...",
               "..##...",
               "......T",
               "..##...",
               "..##..."]
    g, s, t = picture(one_row)
    assert plan_static(g, s, t, size=1).found
    assert not plan_static(g, s, t, size=2).found   # a 2 x 2 footprint does not fit a one-cell gap
    two_rows = ["S.##....",
                "..##....",
                ".....T..",
                "........",
                "..##....",
                "..##...."]
    g, s, t = picture(two_rows)
    big = plan_static(g, s, t, size=2)
    assert big.found
    for x, y in big.cells:                          # footprint top-left (x, y): x..x+1, y..y+1 all free
        assert all(not g.is_blocked(x + i, y + j) for i in (0, 1) for j in (0, 1))


def test_a_serpentine_longer_than_the_search_limit_ends_at_a_fallback_cell():
    # 17 rows of 130 cells joined alternately at the ends: ~1050 steps.  The human search runs 1000 levels,
    # so the target is never labelled and the walk (capped at 1000 steps by FUN_0054e58c) ends at the fallback.
    w = 130
    rows = []
    for k in range(9):
        rows.append("." * w)
        if k < 8:
            rows.append(("#" * (w - 1) + ".") if k % 2 == 0 else ("." + "#" * (w - 1)))
    g, _, _ = picture(rows)
    s, t = at(0, 0), at(0, len(rows) - 1)
    r = plan_static(g, s, t, human=True)
    assert not r.found and r.limit == 1000 and r.levels >= 1000
    assert len(r.cells) <= 1000


def test_dynamic_plan_has_the_short_limit_and_avoids_stamped_cells():
    g, s, t = picture(["S.....T"])
    live = g.with_blocked([at(3, 0)])
    # one-row corridor: the stamped cell cuts it; limit dist + min(3, dist>>2) = 6 + 1 levels, no way round
    r = plan_dynamic(live, s, t)
    assert not r.found
    g2, s2, t2 = picture(["S.....T", "......."])
    r = plan_dynamic(g2.with_blocked([at(3, 0)]), s2, t2)
    assert r.found and at(3, 0) not in r.cells


def test_searched_cells_start_at_the_start_and_are_unique():
    g, s, t = picture(["S....", ".....", "....T"])
    r = plan_static(g, s, t)
    assert r.searched[0] == s and len(set(r.searched)) == len(r.searched)
    assert t in r.searched


def test_planner_is_pure():
    g, s, t = picture(["S.#..T", "..#...", "......"])
    before = (bytes(g.blocked), None)
    a = plan_static(g, s, t)
    b = plan_static(g, s, t)
    assert a.cells == b.cells and a.searched == b.searched
    assert bytes(g.blocked) == before[0]


def test_map_larger_than_the_grid_is_rejected():
    with pytest.raises(ValueError):
        PathGrid.from_arrays(np.zeros((300, 10), bool))
