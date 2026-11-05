"""Fog of war as the view applies it (docs/engine/vision.md section 2): which objects are drawn / pickable, the overlay levels, the minimap blocks.

Reads `World.fog` (tile words with the exe's bits, `None` = no fog) and never writes it.
"""

import numpy as np

from allods2 import vision as v
from allods2.graphics import lighting as lt
from allods2.graphics.terrain import TILE


def active(world):
    return world.fog is not None


def unit_visible(world, u):
    """`FUN_00468762`: the viewer's own units always; others when one of the four tiles of their cell has both bits."""
    return world.fog is None or u.owner == world.fog_viewer or v.cell_in_sight(world.fog, u.x, u.y)


def cell_visible(world, x, y):
    """The four tiles of cell (x, y) OR to exactly `0xc000`: ground piles (`0x409547`) and the hover flags 0x40 (item) / 0x400 (fogged) of `FUN_004180c6`."""
    return world.fog is None or v.cell_in_sight(world.fog, x, y)


def item_visible(world, it):
    """Ground piles: the cell test of `cell_visible`."""
    return cell_visible(world, it.x, it.y)


def structure_state(world, ent):
    """`S` of `FUN_00461460`: 0 in sight (always for the viewer's own), 1 explored, 2 never seen."""
    if world.fog is None or ent.owner == world.fog_viewer:
        return 0
    return v.structure_state(world.fog, [(ent.x + dx, ent.y + dy) for dx, dy, _ in ent.footprint])


def levels(world, camera, cols, rows):
    """Fog level of view cell (c, r) for `lighting.draw_fog`: shape (rows + 3, cols + 1) from the camera's origin cell, cells beyond the map never seen."""
    vx, vy = camera.ix // TILE, camera.iy // TILE
    out = np.full((rows + 3, cols + 1), lt.FOG_UNSEEN, np.int64)
    fog = world.fog
    h, w = fog.shape
    x0, x1 = max(vx, 0), min(vx + cols + 1, w)
    y0, y1 = max(vy, 0), min(vy + rows + 3, h)
    if x0 < x1 and y0 < y1:
        sub = fog[y0:y1, x0:x1] & np.uint16(v.IN_SIGHT)
        lv = np.where(sub == v.IN_SIGHT, lt.FOG_SEEN, np.where(sub == v.EXPLORED, lt.FOG_EXPLORED, lt.FOG_UNSEEN))
        out[y0 - vy:y1 - vy, x0 - vx:x1 - vx] = lv
    return out


def overlay(world, camera, vertex_y):
    """Input of `lighting.draw_fog` for the camera: (levels, screen y of the vertices, cols, rows).  Cells c = 0 .. W-1, r = 0 .. Hv+3 from the view
    origin cell; `vertex_y` is `Projection.vy` (world y of vertex (col, row)); vertices beyond the map repeat the edge."""
    vx, vy = camera.ix // TILE, camera.iy // TILE
    cols = -(-(camera.ix + camera.view_w) // TILE) - vx
    rows = -(-(camera.iy + camera.view_h) // TILE) - vy + 4
    vr, vc = vertex_y.shape
    ri = np.clip(np.arange(vy, vy + rows + 4), 0, vr - 1)
    ci = np.clip(np.arange(vx, vx + cols + 2), 0, vc - 1)
    sy = vertex_y[np.ix_(ri, ci)].astype(np.int64) - camera.iy
    return levels(world, camera, cols, rows), sy, cols, rows
