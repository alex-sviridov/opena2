"""Draw list: what to draw for a camera, in drawing order (no pixels yet)."""

from dataclasses import dataclass

from allods2.graphics.terrain import TILE


@dataclass(frozen=True)
class TerrainItem:
    col: int
    row: int
    phase: int            # water animation phase 0..3 (0 for static cells)
    sx: int               # screen x of the cell's first pixel column

    @property
    def key(self):
        return (self.col, self.row, self.phase)


def build_draw_list(terrain_view, camera, tick):
    """Terrain items of the visible cells, row by row top to bottom (later rows
    overwrite earlier ones), animation clock = `tick`."""
    x0, x1, y0, y1 = terrain_view.proj.visible_cells(camera)
    cx = camera.ix
    return [TerrainItem(col, row, terrain_view.phase(col, row, tick), col * TILE - cx)
            for row in range(y0, y1) for col in range(x0, x1)]
