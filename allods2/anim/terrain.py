"""Animated terrain: water (tile sets 8-11).

Spec: docs/formats/terrain.md (water_set, FUN_00404e0e) and
docs/formats/animation.md §3.2 / §4.7.  A water cell of set s at absolute
cell (x, y) draws set 8 + ((s + (x+1) y + (clock >> 2)) & 3): one frame per
4 ticks, a 16-tick loop, out of step from cell to cell; frozen at set 8
when "Object animations" is off.  Lava does not exist in Allods 2; no other
terrain animates.
"""


import numpy as np

from ..alm import load_alm
from a2res import basename, splitext

from ..common import as_fs, campaign_maps
from ..graphics.terrain import TILE, WATER, TerrainSet, decode_cell, water_set
from .base import Action, AnimationSet, FrameRef

TERRAIN_DIR = "graphics/terrain"


class WaterSet(AnimationSet):
    """A window of map cells; action "water" loops 16 ticks.  The anchor is
    the window's top-left corner; (x0, y0) is its absolute cell position,
    which the per-cell phase uses."""
    kind = "terrain"

    def __init__(self, name, terrain, tiles, x0=0, y0=0):
        super().__init__(name)
        self.terrain, self.tiles, self.x0, self.y0 = terrain, np.asarray(tiles), x0, y0
        self.actions = {"water": Action("water", list(range(16)))}

    def frame_at(self, action, facing, tick, *, animate=True):
        return FrameRef("terrain", -1, False, (0, 0), action, tick, effect="terrain" if animate else "frozen")

    def extent(self, ref):
        h, w = self.tiles.shape
        return (0, 0, w * TILE, h * TILE)

    def cell_sets(self, tick, animate=True):
        """(h, w) tile set each cell draws at `tick`."""
        h, w = self.tiles.shape
        out = np.zeros((h, w), np.int32)
        for y in range(h):
            for x in range(w):
                s = decode_cell(self.tiles[y, x]).set
                out[y, x] = water_set(s, self.x0 + x, self.y0 + y, tick, animate) if s in WATER else s
        return out

    def draw(self, canvas, ref, x, y):
        h, w = self.tiles.shape
        anim = ref.phase
        for cy in range(h):
            for cx in range(w):
                t = self.terrain.cell_tile(self.tiles[cy, cx], self.x0 + cx, self.y0 + cy,
                                           anim, ref.effect != "frozen")
                if t is None:
                    continue
                px, py = x + cx * TILE, y + cy * TILE
                if 0 <= px and px + TILE <= canvas.width and 0 <= py and py + TILE <= canvas.height:
                    canvas.pix[py:py + TILE, px:px + TILE] = self.terrain.palette[t]


def find_water_window(fs=None, w=12, h=8):
    """(map path, x0, y0): the first campaign-map window (maps in mission
    order, 4-cell steps, inside the loader's copied area) whose cells are
    40-70 % water, so both shore and open water show."""
    fs = as_fs(fs)
    for path in campaign_maps(fs):
        tiles = load_alm(path, fs).tiles
        sets = (tiles & 0x1FFF) >> 6
        m = (sets >= WATER.start) & (sets < WATER.stop)
        for y0 in range(8, tiles.shape[0] - h - 5, 4):
            for x0 in range(8, tiles.shape[1] - w - 9, 4):
                f = m[y0:y0 + h, x0:x0 + w].mean()
                if 0.4 <= f <= 0.7:
                    return path, x0, y0
    return None


def load_water_set(key, fs=None, w=12, h=8):
    """key "" / "auto": a window found by find_water_window; or
    "<map>,<x0>,<y0>" with <map> a campaign map name ("10.alm")."""
    fs = as_fs(fs)
    if key in ("", "auto", "water"):
        found = find_water_window(fs, w, h)
        if found is None:
            raise FileNotFoundError("no map with a water window")
        path, x0, y0 = found
    else:
        name, x0, y0 = key.split(",")
        path = next((p for p in campaign_maps(fs)
                     if basename(p).lower() == name.lower()), None)
        if path is None:
            raise FileNotFoundError("no map %r" % name)
        x0, y0 = int(x0), int(y0)
    tiles = load_alm(path, fs).tiles[y0:y0 + h, x0:x0 + w]
    terrain = TerrainSet.load(fs, TERRAIN_DIR)
    stem = splitext(basename(path))[0]
    return WaterSet("water_%s_%d_%d" % (stem, x0, y0), terrain, tiles, x0, y0)
