"""Follow-target fallback (FUN_00557f08 and helpers), synthetic; spec docs/engine/simulation.md 7.4."""

import random

import numpy as np

from engine.sim.pathfinding import (FOLLOW_DIRS, GRID, UNSEEN, Foot, PathGrid, centre_x, centre_y, follow_compass,
                                    follow_distance, follow_fallback, plan_dynamic)

T = Foot(50, 50)


def field(labelled):
    """Label field with only the given {(x, y): label} cells labelled."""
    f = [UNSEEN] * (GRID * GRID)
    for (x, y), v in labelled.items():
        f[y * GRID + x] = v
    return f


def full(v=5):
    return [v] * (GRID * GRID)


def test_centre_helpers_FUN_0050d884():
    assert centre_x(Foot(3, 4)) == 3 * 256 + 128 and centre_y(Foot(3, 4)) == 4 * 256 + 128
    assert centre_x(Foot(3, 4, 2, 10, 20)) == 3 * 256 + 10 + 128 and centre_y(Foot(3, 4, 2, 10, 20)) == 4 * 256 + 20 + 128
    assert centre_x(Foot(3, 4, 3)) == 3 * 256 + 128 + 256


def test_follow_distance_FUN_00556dcd():
    assert follow_distance(Foot(5, 5), Foot(6, 5)) == 1            # touching
    assert follow_distance(Foot(5, 5), Foot(5, 5)) == 1            # overlapping clamps at 0
    assert follow_distance(Foot(5, 5), Foot(7, 5)) == 2
    assert follow_distance(Foot(5, 5), Foot(9, 8)) == 4            # Chebyshev: x gap 3 cells + 1
    assert follow_distance(Foot(5, 5, 2), Foot(7, 5)) == 1         # size 2 covers x 5..6: touching
    assert follow_distance(Foot(5, 5, 2), Foot(8, 5)) == 2


def test_compass_codes_FUN_00557cf1():
    t = Foot(50, 50)

    def code(dx, dy):                                              # follower at the offset, sub-cell centres
        return follow_compass(t, Foot(50 + dx, 50 + dy))
    assert code(0, -9) == 15 and code(1, -9) == 0 and code(-1, -9) == 15       # dx == 0 counts as the west half
    assert code(3, -8) == 0 and code(4, -8) == 1 and code(8, -8) == 1 and code(9, -8) == 2
    assert code(9, -5) == 2 and code(9, -4) == 3 and code(9, 0) == 3
    assert code(9, 1) == 4 and code(9, 3) == 4 and code(9, 5) == 5 and code(8, 8) == 6 and code(5, 8) == 6
    assert code(3, 8) == 7 and code(1, 8) == 7
    assert code(0, 8) == 8 and code(-1, 8) == 8 and code(-3, 8) == 8 and code(-5, 8) == 9 and code(-8, 8) == 9
    assert code(-9, 8) == 10 and code(-9, 5) == 10 and code(-9, 3) == 11 and code(-9, 1) == 11
    assert code(-9, 0) == 12 and code(-9, -3) == 12 and code(-9, -5) == 13 and code(-8, -8) == 14 and code(-5, -8) == 14
    assert code(-3, -8) == 15 and code(0, 0) == 14
    # the 2:1 split is strict
    assert follow_compass(t, Foot(50 + 8, 50 + 4)) == 5 and follow_compass(t, Foot(50 + 8, 50 + 3)) == 4


def test_direction_table():
    assert FOLLOW_DIRS[:4] == ((1, 0), (0, 1), (-1, 0), (0, -1)) and len(FOLLOW_DIRS) == 12


def test_entry_point_per_side():
    for follower, entry in ((Foot(50, 44), (50, 49)),               # north: row y0 = ty - follower size
                            (Foot(56, 50), (51, 50)),               # east: column x1 = tx + target size
                            (Foot(50, 56), (50, 51)),               # south: row y1
                            (Foot(44, 50), (49, 50))):              # west: column x0
        assert follow_fallback(full(), follower, T) == entry


def test_diagonal_line_enters_at_the_exact_cell():
    # follower exactly south-east on the diagonal: side 6 (south), s = fx/fy = -1, the line meets row y1 = 51
    # at x = 51 -> the cell (51, 51)
    assert follow_fallback(full(), Foot(56, 56), T) == (51, 51)
    assert follow_fallback(full(), Foot(44, 44), T) == (49, 49)


def test_box_grows_per_attempt_up_to_eight():
    for k in range(1, 9):
        # west follower: the column x0 = 49 - (k - 1); only that cell labelled -> found in attempt k
        f = field({(50 - k, 50): 7})
        assert follow_fallback(f, Foot(30, 50), T) == (50 - k, 50)
    assert follow_fallback(field({(50 - 9, 50): 7}), Foot(30, 50), T) is None
    assert follow_fallback(field({}), Foot(30, 50), T) is None


def test_smallest_label_strict_first_wins():
    # ring of attempt 1 around T (size 1, follower size 1): x 49..51, y 49..51
    f = field({(49, 50): 9, (51, 50): 4, (50, 49): 4, (50, 51): 6})
    # walker 1 from the entry (49, 50) goes south (side 7: p=7 N?) -- either way the label 4 cells tie; the
    # winner is the one a walker reaches first, walker 1 before walker 2 at equal step
    r = follow_fallback(f, Foot(30, 50), T)
    assert r in ((51, 50), (50, 49))
    g = field({(49, 50): 9, (51, 50): 3, (50, 49): 4})
    assert follow_fallback(g, Foot(30, 50), T) == (51, 50)          # lower label wins wherever it is
    # the same label twice: the entry cell itself (step 0, walker 1) wins
    h = field({(49, 50): 4, (51, 50): 4})
    assert follow_fallback(h, Foot(30, 50), T) == (49, 50)


def test_label_zero_is_the_best_label():
    f = field({(49, 49): 0, (49, 50): 1})
    assert follow_fallback(f, Foot(30, 50), T) == (49, 49)


def test_dead_cells_count_as_unlabelled_except_the_start():
    f = field({(49, 50): 0, (51, 50): 5})
    dead = bytearray(GRID * GRID)
    dead[50 * GRID + 49] = 1
    assert follow_fallback(f, Foot(30, 50), T, dead) == (51, 50)
    assert follow_fallback(f, Foot(30, 50), T, dead, 50 * GRID + 49) == (49, 50)


def test_two_walkers_cover_the_ring_when_the_entry_is_on_it():
    rng = random.Random(7)
    hit = miss = 0
    for _ in range(300):
        ts, fs = rng.choice((1, 1, 2, 3)), rng.choice((1, 1, 2, 3))
        tgt = Foot(100, 100, ts, rng.randrange(256), rng.randrange(256))
        fol = Foot(rng.randrange(80, 120), rng.randrange(80, 120), fs, rng.randrange(256), rng.randrange(256))
        if abs(fol.x - tgt.x) < 8 and abs(fol.y - tgt.y) < 8:
            continue
        x0, y0, x1, y1 = tgt.x - fs, tgt.y - fs, tgt.x + ts, tgt.y + ts
        ring = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)
                if x in (x0, x1) or y in (y0, y1)]
        cell = rng.choice(ring)
        r = follow_fallback(field({cell: 3}), fol, tgt)
        assert r in (None, cell)
        hit += r is not None
        miss += r is None
    assert hit > 10 * miss                       # a miss needs the entry point off the edge (see below)


def test_entry_point_off_the_box_edge_can_miss_a_ring_cell():
    # consequence of the algorithm (INFERRED play): the line meets the east column at row 98, above the box
    # (rows 99..101); the walkers cover only n = 5 cells each from there, the west cell (99, 100) is missed
    fol, tgt = Foot(114, 86, 1, 186, 13), Foot(100, 100, 1, 0, 77)
    assert follow_fallback(full(3), fol, tgt) == (101, 98)
    assert follow_fallback(field({(99, 100): 3}), fol, tgt) is None


def test_sized_follower_and_target_box():
    # follower size 2 west of a size 2 target: box x0 = 50 - 2, x1 = 52, y0 = 48, y1 = 52
    t = Foot(50, 50, 2)
    r = follow_fallback(full(), Foot(30, 50, 2), t)
    assert r[0] == 48                                               # column x0, entered on the line y ~ 51
    assert follow_fallback(field({(48, 48): 1}), Foot(30, 50, 2), t) == (48, 48)       # corner of the box


def test_same_centre_does_not_raise():
    # compass 14 -> side 4 and 0 / 0 = NaN: FISTP gives the integer indefinite (low dword 0), no FP trap assumed
    r = follow_fallback(full(), Foot(50, 50), T)
    assert r is None or len(r) == 2


def test_entry_point_matches_the_exact_line_within_one_cell():
    """Differential: the float32 slope + truncated intercept entry point against the exact rational line
    through the two centres (the exe truncates the intercept to 1/256 cell and the slope to float32)."""
    from fractions import Fraction
    rng = random.Random(3)
    same = total = 0
    for _ in range(2000):
        tgt = Foot(100, 100, 1, rng.randrange(256), rng.randrange(256))
        fol = Foot(rng.randrange(60, 140), rng.randrange(60, 140), 1, rng.randrange(256), rng.randrange(256))
        if max(abs(fol.x - 100), abs(fol.y - 100)) < 5:
            continue
        side = (((follow_compass(tgt, fol) + 2) & 12) >> 2) + 4
        got = follow_fallback(full(3), fol, tgt)
        fx, fy = centre_x(tgt) - centre_x(fol), centre_y(tgt) - centre_y(fol)
        if side in (5, 7):
            edge = (tgt.x + 1) if side == 5 else (tgt.x - 1)
            fx = fx or 1
            exact = (edge, int(centre_y(tgt) + Fraction(fy, fx) * ((edge << 8) + 128 - centre_x(tgt))) >> 8)
        else:
            edge = (tgt.y - 1) if side == 4 else (tgt.y + 1)
            exact = (int(centre_x(tgt) + Fraction(fx, fy) * ((edge << 8) + 128 - centre_y(tgt))) >> 8, edge)
        assert abs(got[0] - exact[0]) <= 1 and abs(got[1] - exact[1]) <= 1
        total += 1
        same += got == exact
    assert same > 0.97 * total


def test_plan_dynamic_follow_ends_on_the_follower_side():
    blocked = np.ones((80, 80), bool)
    blocked[8:72, 8:72] = False
    blocked[30, 40] = True                                          # the target unit's cell is stamped
    grid = PathGrid.from_arrays(blocked)
    tgt = Foot(40, 30)
    res = plan_dynamic(grid, (30, 30), (40, 30), follow=(Foot(30, 30), tgt))
    assert res.reason == "fallback" and res.end == (39, 30)
    assert res.cells[-1] == (39, 30)
