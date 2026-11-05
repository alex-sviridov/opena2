"""Minimap geometry and image with the camera rectangle (no pygame).

Spec: docs/superpowers/specs/2026-10-16-minimap-design.md.  Image pixels per cell `s = 2**k`
(`allods2.minimap.scale_shift`); image pixel `(px, py)` is cell `(px / s + 8, py / s + 8)`.
"""

import numpy as np

from allods2 import vision as v
from allods2.graphics.terrain import TILE
from allods2.graphics.palette import pack16, unpack16
from .objmap import walk_order
from allods2.minimap import BORDER, minimap_light, minimap_rgb, minimap_size, scale_shift

RECT_COLOR = (255, 255, 255)        # CONFIRMED FUN_004569a3 call: all channels full


class MinimapGeometry:
    def __init__(self, map_w, map_h):
        """`map_w`, `map_h` in cells."""
        self.map_w, self.map_h = map_w, map_h
        self.k = scale_shift(map_w, map_h)
        self.s = 2.0 ** self.k
        self.width, self.height = minimap_size(map_w, map_h)

    def cell_to_pixel(self, col, row):
        """Image position (float) of the top-left corner of cell (col, row)."""
        return (col - BORDER) * self.s, (row - BORDER) * self.s

    def pixel_to_cell(self, px, py):
        """Cell position (floats) under image pixel (px, py); not clamped."""
        return px / self.s + BORDER, py / self.s + BORDER

    def camera_cell(self, camera):
        """The camera's top-left as a cell position (relief height ignored: DECISION)."""
        return camera.x / TILE, camera.y / TILE

    def camera_rect(self, camera):
        """(x0, y0, x1, y1) inclusive image pixels of the camera outline, clipped to the
        image; None when it lies outside."""
        cx, cy = self.camera_cell(camera)
        x0, y0 = self.cell_to_pixel(cx, cy)
        x1 = x0 + camera.view_w / TILE * self.s - 1
        y1 = y0 + camera.view_h / TILE * self.s - 1
        x0, y0, x1, y1 = int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))
        if x1 < 0 or y1 < 0 or x0 >= self.width or y0 >= self.height:
            return None
        return max(x0, 0), max(y0, 0), min(x1, self.width - 1), min(y1, self.height - 1)


def dot_box(geometry, col, row):
    """(x0, y0, x1, y1) inclusive image pixels of the unit dot of cell (col, row), or None outside
    the image: `(c - 8) << k` with a `1 << k` square, for k = -1 `>> 1` and one pixel (CONFIRMED
    0x465f3f; no altitude term, flyers use the same function)."""
    k = geometry.k
    x, y = ((col - BORDER) << k, (row - BORDER) << k) if k >= 0 else ((col - BORDER) >> 1, (row - BORDER) >> 1)
    n = 1 << k if k >= 0 else 1
    if x < 0 or y < 0 or x + n > geometry.width or y + n > geometry.height:
        return None
    return x, y, x + n - 1, y + n - 1


def _dot_players(world, owner):
    """The player record whose colour a dot takes: the structure / unit builder stores `players[key 0]` (the section 5 record 1) as the default
    owner, so an owner that matches no record (0 = neutral) draws in record 1's colour (`0x4a4934`, `0x4a51ea`).  CONFIRMED."""
    return world.players.get(owner) or world.players.get(1)


def unit_dots(geometry, world, colors):
    """[(id, (x0, y0, x1, y1), rgb)] of the unit dots in registration order (units, then corpses)."""
    fog = world.fog
    out = []
    for u in (*world.units.values(), *world.corpses.values()):
        if u.hp <= -11:
            continue
        if u.hidden and u.owner != world.fog_viewer:                        # `0x465f3f`: Invisibility effect 0x20 -> only when the viewer's word bit 8 for the owner
            continue                                                        # (`FUN_0041e860`, `view+0x9cc`: the local player's record; own units only, vision.md)
        if fog is not None and not v.cell_in_sight(fog, u.x, u.y):          # `0x465f3f`: the four tiles must OR to 0xc000 (no ownership gate)
            continue
        box = dot_box(geometry, u.x, u.y)
        p = _dot_players(world, u.owner)
        if box is not None and p is not None:
            out.append((u.oid, box, colors[p.colour & 15]))
    return out


def structure_dots(geometry, world, colors, sizes):
    """[(id, (x0, y0, x1, y1), rgb)] of the structure and bridge dots in registration order."""
    fog = world.fog
    k = geometry.k
    out = []
    for ent in world.objects.values():
        if ent.kind == "object":
            continue
        size = ent.size if ent.size is not None else sizes.get(ent.type_id)
        p = _dot_players(world, ent.owner)
        if size is None or p is None:
            continue
        if fog is not None and not v.cell_in_sight(fog, ent.x, ent.y):
            continue
        w, h = size
        if k >= 0:
            x, y, w, h = (ent.x - BORDER) << k, (ent.y - BORDER) << k, w << k, h << k
        else:
            x, y = (ent.x - BORDER) >> 1, (ent.y - BORDER) >> 1
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, geometry.width), min(y + h, geometry.height)
        if x1 > x0 and y1 > y0:
            out.append((ent.id, (x0, y0, x1 - 1, y1 - 1), colors[p.colour & 15]))
    return out


def _paint(image, dots):
    for _, (x0, y0, x1, y1), rgb in dots:
        image[y0:y1 + 1, x0:x1 + 1] = rgb


def draw_unit_dots(image, geometry, world, colors):
    """Write one dot per unit (colour = `colors[owner's human.pal row]`) into `image`.
    The exe draws a dot for any unit in sight (no ownership gate, CONFIRMED `0x465f3f`), none for
    another owner's invisible unit; without fog every unit gets one.  Bodies of death stage >= 2 (HP <= -11) get none (`0x465f3f`); dying bodies and
    the corpses of stage 1 keep theirs (combat.md 12.6).  Registration order; `draw_dots` is the exe's order."""
    _paint(image, unit_dots(geometry, world, colors))


def draw_structure_dots(image, geometry, world, colors, sizes):
    """Structures and bridges draw a dot too (vtable `+0x34` = `0x46213e`, CONFIRMED): top-left cell `(x, y)` of the object,
    colour = palette entry 164 of the owner's row, rectangle `(x - 8) << k`, `(y - 8) << k`, size `W << k` x `H << k` cells
    (`W, H` = `TileWidth/TileHeight` of structures.reg = `sizes[type]`, the map entry's size for a bridge); for k = -1 the
    position is `>> 1` and the size stays `W x H` pixels (the exe does not halve it).  Gate: the four tiles at the cell
    OR to `0xc000` (no ownership, hp or explored gate).  Cropped at the image like `FUN_00456348`."""
    _paint(image, structure_dots(geometry, world, colors, sizes))


def exe_order(dots):
    """Sort `dots` (registration order: structures, units, corpses) into the exe's walk of the view's object map ([objmap](objmap.py)); later dots
    overwrite earlier ones."""
    return [d for _, d in walk_order([(d[0], d) for d in dots])]


def draw_dots(image, geometry, world, colors, sizes=None):
    """Structure dots and unit dots in the order the exe draws overlapping ones (`FUN_004ac414` walks the object map, vtable `+0x34` each)."""
    dots = structure_dots(geometry, world, colors, sizes) if sizes is not None else []
    dots += unit_dots(geometry, world, colors)
    _paint(image, exe_order(dots))


def apply_fog(image, geometry, fog, background=None):
    """`FUN_004ac414` fog blocks, in place: per image pixel the OR of the four tile words at its cell; no 0xc000 bit -> the panel background pixel
    (`background`, an (h, w, 3) uint8 crop of the panel under the image; black when None), exactly 0x8000 -> `(a >> 1) + (b >> 1)` per channel of
    background and map, else the map pixel (vision.md 3).  For k = -1 each pixel stands for the 2 x 2 cells at `px * 2 + 8`."""
    h, w = fog.shape
    pad = np.zeros((h + 1, w + 1), np.uint16)
    pad[:h, :w] = fog
    or4 = pad[:-1, :-1] | pad[:-1, 1:] | pad[1:, :-1] | pad[1:, 1:]
    k = geometry.k
    px = np.arange(geometry.width)
    py = np.arange(geometry.height)
    cx = ((px >> k) if k >= 0 else (px << 1)) + BORDER
    cy = ((py >> k) if k >= 0 else (py << 1)) + BORDER
    bits = or4[np.ix_(np.minimum(cy, h - 1), np.minimum(cx, w - 1))] & np.uint16(v.IN_SIGHT)
    bg = np.zeros_like(image) if background is None else background
    unseen = bits == 0
    explored = bits == v.EXPLORED
    mask = np.uint16(0x7bef)                                      # 565: (a >> 1 & M) + (b >> 1 & M), exactly as the exe
    bw, iw = pack16(bg), pack16(image)
    half = ((bw >> 1) & mask) + ((iw >> 1) & mask)
    out = np.where(explored, half, iw)
    out = np.where(unseen, bw, out).astype(np.uint16)
    image[...] = unpack16(out)
    return image


def draw_camera_rect(image, rect, color=RECT_COLOR):
    """Copy of `image` with the one-pixel outline `rect` drawn."""
    out = image.copy()
    if rect is not None:
        x0, y0, x1, y1 = rect
        out[y0, x0:x1 + 1] = color
        out[y1, x0:x1 + 1] = color
        out[y0:y1 + 1, x0] = color
        out[y0:y1 + 1, x1] = color
    return out


class Minimap:
    """The base image of a world, built once; `image(camera)` adds the camera rectangle."""

    def __init__(self, world, table, dot_colors=None, structure_sizes=None):
        """`dot_colors`: (16, 3) from `allods2.minimap.load_dot_colors` (None = no dots); `structure_sizes`:
        `allods2.minimap.load_structure_sizes` (None = no structure dots)."""
        self.world, self.table, self.dot_colors = world, table, dot_colors
        self.structure_sizes = structure_sizes
        self.geometry = MinimapGeometry(world.width, world.height)
        self._base = None
        self.builds = 0

    def invalidate(self):
        """Forget the base image (terrain edits; nothing else changes the picture)."""
        self._base = None

    @property
    def base(self):
        if self._base is None:
            self._base = minimap_rgb(self.world.cells, self.table, minimap_light(self.world.heights))
            self._base.flags.writeable = False
            self.builds += 1
        return self._base

    def image(self, camera, background=None):
        """Base image, the fog blocks (when `world.fog` is set; `background` = the panel pixels under the image), then the unit dots, then the camera
        rectangle (the exe's order)."""
        img = self.base.copy()
        if self.world.fog is not None:
            apply_fog(img, self.geometry, self.world.fog, background)
        if self.dot_colors is not None:
            draw_dots(img, self.geometry, self.world, self.dot_colors, self.structure_sizes)
        return draw_camera_rect(img, self.geometry.camera_rect(camera))
