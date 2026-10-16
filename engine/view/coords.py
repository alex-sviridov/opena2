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
