"""Coordinate conversions and the visible cell range.

World px: x = 32*col, y = 32*row - H (CONFIRMED FUN_004065b1).  Screen px =
world px - camera.  Docs: docs/engine/architecture.md section 3.
"""

import math

import numpy as np

from allods2.graphics.terrain import TILE, edge_offsets, vertex_y


class Projection:
    """Vertex table of one map (height offsets) and conversions over it."""

    def __init__(self, heights):
        h = np.asarray(heights).astype(np.int8).astype(np.int64)
        self.rows, self.cols = h.shape
        self._flat = h.ravel()                     # the exe reads the height bytes as one flat array
        self.vy = vertex_y(h)                      # (rows+1, cols+1)
        self.hmax = int(h.max())
        self.hmin = int(h.min())

    def corners(self, col, row):
        vy = self.vy
        return (int(vy[row, col]), int(vy[row, col + 1]),
                int(vy[row + 1, col]), int(vy[row + 1, col + 1]))

    def column_span(self, col, row, px):
        """(top, bottom) world y of pixel column `px` (0..31) of a cell, as drawn."""
        ytl, ytr, ybl, ybr = self.corners(col, row)
        return (ytl + int(edge_offsets(ytl, ytr)[px]),
                ybl + int(edge_offsets(ybl, ybr, bottom=True)[px]))

    def cell_to_world(self, col, row):
        """World px of the cell's origin vertex (top-left corner)."""
        return col * TILE, int(self.vy[row, col])

    def cell_center_world(self, col, row):
        top, bot = self.column_span(col, row, TILE // 2)
        return col * TILE + TILE // 2, (top + bot) // 2

    def world_to_cell(self, wx, wy):
        """(col, row) of the cell drawn at world px (wx, wy), or None.  The
        lowest row wins where cells overlap, as in the draw order."""
        col = math.floor(wx / TILE)
        if not 0 <= col < self.cols:
            return None
        px = int(wx) - col * TILE
        lo = max(0, math.floor((wy + self.hmin) / TILE) - 1)
        hi = min(self.rows - 1, math.floor((wy + self.hmax) / TILE) + 1)
        for row in range(hi, lo - 1, -1):
            top, bot = self.column_span(col, row, px)
            if top <= wy < bot:
                return col, row
        return None

    def hover_cell(self, wx, wy):
        """(col, row) under world px (wx, wy) by the exe's hover rule, or None (CONFIRMED
        FUN_00417f31, used by the hover flags of FUN_004180c6, docs/engine/ui-layout.md section 6).
        Rows are scanned upward from the smallest; the first row whose top line <= wy <= bottom
        line at the pixel column wins.  A line is the linear interpolation, truncated toward zero,
        of the two vertex y values by the pixel column (no edge_offsets)."""
        col, fx = divmod(int(wx), TILE)
        if not 0 <= col < self.cols:
            return None
        vy = self.vy

        def line(row):
            a, b = int(vy[row, col]), int(vy[row, col + 1])
            return a + int((b - a) * fx / TILE)      # int() truncates toward zero, as the exe

        lo = max(0, math.floor((wy + self.hmin) / TILE) - 2)
        hi = min(self.rows - 1, math.floor((wy + self.hmax) / TILE) + 1)
        for row in range(lo, hi + 1):
            if line(row) <= wy <= line(row + 1):
                return col, row
        return None

    def exe_row(self, vx, vy, view_w, view_h, mx, my):
        """Row (relative to the view's top cell `vy`) that the exe's `FUN_00417f31(mx, my)` returns for the view whose
        origin cell is (`vx`, `vy`) and whose size is `view_w` x `view_h` cells, for ANY mouse position, also right of
        the view (CONFIRMED asm 0x417f31-0x4180c3, tables `FUN_004065b1`, sizes `FUN_00402fb8`;
        docs/engine/click-to-move-research.md 1.6).  The three tables are flat arrays indexed with the column
        `(mx >> 5) + 3` and NO bounds test: vertex table stride `W + 7` (rows -3 ..), top/bottom extreme tables stride
        `W + 6`, so a column >= W + 3 reads the next row's first entries.  Rows run -3 .. H + 6; the first row whose
        extreme bounds contain `my` and whose interpolated top line <= `my` <= bottom line wins; none -> `H + 4`.
        The one read past an allocation that can happen (the last row, column >= W + 3, only after no earlier row
        matched) hits the next heap block's header; INFERRED to be skipped, so the result is `H + 4`.  Returns None
        only for a vertex read outside its table (unreachable for a mouse position in the screen)."""
        flat, mw = self._flat, self.cols
        sv, sm = view_w + 7, view_w + 6
        nv, nm = sv * (view_h + 11), sm * (view_h + 10)

        def vt(i):
            if not 0 <= i < nv:
                raise IndexError(i)
            r, c = divmod(i, sv)
            r, c = r - 3, c - 3
            return 32 * r - int(flat[(vy + r) * mw + vx + c])

        def vt_min(j):                              # b8: min y of a cell's top edge
            r, c = divmod(j, sm)
            i = r * sv + c
            return min(vt(i), vt(i + 1))

        def vt_max(j):                              # bc: max y of a cell's bottom edge
            r, c = divmod(j, sm)
            i = r * sv + c + sv
            return max(vt(i), vt(i + 1))

        col, fx = (mx >> 5) + 3, mx & 31

        def line(i):
            a, b = vt(i), vt(i + 1)
            d = (b - a) * fx
            return a + ((d + (31 if d < 0 else 0)) >> 5)       # truncated toward zero, as the exe

        try:
            for r in range(-3, view_h + 7):
                j = (r + 3) * sm + col
                if j >= nm:                         # last row, column >= W + 3: heap bytes past the table (INFERRED:
                    continue                        # the next block's header, a large positive value -> skipped)
                if vt_min(j) > my or vt_max(j) < my:
                    continue
                i = (r + 3) * sv + col
                if line(i) <= my <= line(i + sv):
                    return r
        except IndexError:
            return None
        return view_h + 4

    def visible_cells(self, camera):
        """(x0, x1, y0, y1): cells x0 <= col < x1, y0 <= row < y1 that can touch the
        viewport.  Rows are padded by the map's height range."""
        cx, cy = camera.ix, camera.iy
        x0 = max(0, cx // TILE)
        x1 = min(self.cols, -(-(cx + camera.view_w) // TILE))
        y0 = max(0, (cy + self.hmin) // TILE)
        y1 = min(self.rows, -(-(cy + camera.view_h + self.hmax) // TILE))
        return x0, max(x0, x1), y0, max(y0, y1)


def world_to_screen(camera, wx, wy):
    return wx - camera.ix, wy - camera.iy


def screen_to_world(camera, sx, sy):
    return sx + camera.ix, sy + camera.iy
