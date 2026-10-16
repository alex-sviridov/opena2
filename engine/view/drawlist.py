"""Draw lists: what to draw for a camera, in drawing order (no pixels yet).

`build_terrain_items` lists the terrain cells; `build_draw_list` the sprites of
map objects and structures (plus debug overlays) in the exe's pass order.
Spec: docs/engine/rendering.md; order and geometry: docs/formats/map.md part 4,
docs/mechanics/lighting.md sections 4-5.  No pixels and no pygame here.
"""

import functools
import math
import weakref
from dataclasses import dataclass

import numpy as np

from allods2.anim.scene import piece_cells
from allods2.anim.structures import BridgeSet
from allods2.formats import objects as fobj
from allods2.graphics import lighting as lt
from allods2.graphics.terrain import TILE

CELL = TILE
PASS_SHADOW, PASS_FLAT, PASS_CELL, PASS_OVERLAY, PASS_DEBUG = 0, 1, 3, 8, 9
SLOT_STRUCTURE, SLOT_UNIT, SLOT_STEAM, SLOT_OBJECT, SLOT_FIRE = range(5)
WALKER = 1                      # mover for the passability overlay (mask 0x41)
FLAG_DESTROYED = 1              # engine.world.FLAG_DESTROYED (view must not import it)


@dataclass(frozen=True)
class TerrainItem:
    col: int
    row: int
    phase: int            # water animation phase 0..3 (0 for static cells)
    sx: int               # screen x of the cell's first pixel column

    @property
    def key(self):
        return (self.col, self.row, self.phase)


def build_terrain_items(terrain_view, camera, tick):
    """Terrain items of the visible cells, row by row top to bottom (later rows
    overwrite earlier ones), animation clock = `tick`."""
    x0, x1, y0, y1 = terrain_view.proj.visible_cells(camera)
    cx = camera.ix
    return [TerrainItem(col, row, terrain_view.phase(col, row, tick), col * TILE - cx)
            for row in range(y0, y1) for col in range(x0, x1)]


@dataclass(frozen=True)
class DrawOptions:
    """Game options (all default to 1 in the game) plus layer switches.  Defaults
    are the game's; the parity tests use shadows=False, lit=False (= E4)."""
    shadows: bool = True        # DAT_005f17e8
    lit: bool = True            # BRIGHT2 light row (lighting.md section 4)
    smoothing: bool = True      # b.256 overlays and their shadows, DAT_00622768
    animate: bool = True        # "Object animations" DAT_005f17ec
    objects: bool = True        # map objects and structures at all


@dataclass(frozen=True)
class DrawItem:
    kind: str                   # "sprite" | "shadow" | "marker" | "passability" | "depth"
    entity: int = None          # world id
    sprite: tuple = None        # (set_kind "object"|"structure"|"bridge", type_id, source)
    frame: int = 0              # index into the sprite file
    sx: int = 0                 # screen top-left of the frame (a shadow: of the sheared frame)
    sy: int = 0
    w: int = 0
    h: int = 0
    mirrored: bool = False
    blend: str = "opaque"       # "opaque" | "half" | "alpha" | "shadow"
    light_row: int = None       # BRIGHT2 row (None = file palette, unlit)
    shadow: bool = False
    shadow_level: int = None    # k of dst*(16-k)/16 (0x6226cc / 0x6226d0)
    remap: int = None           # human.pal index; always None for structures and objects
    depth: tuple = ()
    shear: int = 0              # 16.16 shear of a shadow
    text: str = None            # depth label; "hotspot" for a marker cross


class DrawList(list):
    """Items in drawing order; `missing` counts entities whose sprite is absent
    (the game draws nothing for them), `culled` those outside the window."""
    missing = 0
    culled = 0


def view_window(camera):
    """(vx, vy, W, Hv): the exe's window origin and size in cells (view+0x5c..0x68)
    derived from the camera: the cells the viewport touches, ignoring relief."""
    vx, vy = camera.ix // CELL, camera.iy // CELL
    return (vx, vy, -(-(camera.ix + camera.view_w) // CELL) - vx,
            -(-(camera.iy + camera.view_h) // CELL) - vy)


def in_window(win, x, y):
    """Cells the exe draws: -3 <= x - vx <= W + 2 and -3 <= y - vy <= Hv + 6."""
    vx, vy, w, hv = win
    return vx - 3 <= x <= vx + w + 2 and vy - 3 <= y <= vy + hv + 6


# --- relief ------------------------------------------------------------------

_relief = {}                # id(array) -> (weakref, grid)


def relief_grid(heights):
    """(h, w) int cell relief (view +0xc0): mean of the four corner heights
    truncated toward 0 (== formats.objects.cell_relief), cached per array."""
    hit = _relief.get(id(heights))
    if hit is not None and hit[0]() is heights:
        return hit[1]
    h = np.pad(np.asarray(heights).astype(np.int8).astype(np.int64), ((0, 1), (0, 1)), mode="edge")
    s = h[:-1, :-1] + h[:-1, 1:] + h[1:, :-1] + h[1:, 1:]
    r = np.trunc(s / 4).astype(np.int64)
    _relief[id(heights)] = (weakref.ref(heights), r)
    return r


# --- shadows -----------------------------------------------------------------

@functools.lru_cache(maxsize=256)
def shadow_offsets(h, shear):
    """(offsets, lo, hi): lt.shadow_row_offsets and its extremes."""
    off = tuple(lt.shadow_row_offsets(h, shear))
    return off, min(off), max(off)


def _trunc(v):
    return int(v)


class _Ctx:
    """Per-call state shared by the builders."""

    def __init__(self, world, camera, tick, assets, opts):
        self.world, self.cam, self.tick, self.assets, self.opts = world, camera, tick, assets, opts
        self.cx, self.cy = camera.ix, camera.iy
        self.win = view_window(camera)
        day = lt.daylight(0, False)
        self.row = lt.object_light_row(day.ambient) if opts.lit else None
        self.k1, self.k2 = day.shadow1, day.shadow2
        self.beta = lt.shadow_angle(day.angle)
        self.T = math.tan(self.beta)
        self.shear = lt.shadow_shear(day.angle)
        self.items = DrawList()
        self.relief = relief_grid(world.heights)

    def visible(self, sx, sy, w, h, lo=0, hi=0):
        return (sx + w + hi > 0 and sx + lo < self.cam.view_w
                and sy + h > 0 and sy < self.cam.view_h)

    def sprite(self, ent, key, src, idx, x, y, w, h, depth, blend="opaque"):
        sx, sy = x - self.cx, y - self.cy
        if self.visible(sx, sy, w, h):
            self.items.append(DrawItem("sprite", ent.id, (key[0], key[1], src), idx, sx, sy, w, h,
                                       blend=blend, light_row=self.row, depth=depth))

    def shadow(self, ent, key, src, idx, x, y, w, h, k, depth):
        sx, sy = x - self.cx, y - self.cy
        _, lo, hi = shadow_offsets(h, self.shear)
        if self.visible(sx, sy, w, h, lo, hi):
            self.items.append(DrawItem("shadow", ent.id, (key[0], key[1], src), idx, sx, sy, w, h,
                                       blend="shadow", shadow=True, shadow_level=k, depth=depth,
                                       shear=self.shear))


def _objects(ctx, ent):
    """Map object: P3 (d) = shadow main, shadow b, sprite, b overlay at 50 %."""
    x, y, opts = ent.x, ent.y, ctx.opts
    if not in_window(ctx.win, x, y):
        ctx.items.culled += 1
        return
    aset = ctx.assets.object_set(ent.type_id)
    if aset is None:
        ctx.items.missing += 1
        return
    ref = aset.frame_at("anim" if aset.rec["seq"] else "still", 0, ctx.tick, x=x, y=y,
                        animate=opts.animate)
    wh = aset.size(ref.source, ref.index)
    if wh is None:
        ctx.items.missing += 1
        return
    z = int(ctx.relief[y, x])
    ax, ay = CELL * x + CELL // 2, CELL * y + CELL // 2 - z           # the anchor
    key = ("object", ent.type_id)
    dep = (PASS_CELL, y, -x, SLOT_OBJECT, ent.seq)
    ov = None
    if opts.smoothing:
        ow = aset.size(ref.source + "_b", ref.index)
        if ow is not None:
            ov = ow
    if opts.shadows:
        r = aset.rec
        dx = _trunc(ctx.T * (wh[1] // 2 + r["Height"] // 2 - r["CenterY"]))       # main's, for both
        for sub, src, size, idx_ok, k in ((0, ref.source, wh, True, ctx.k1),
                                          (1, ref.source + "_b", ov, ov is not None, ctx.k2)):
            if not idx_ok:
                continue
            first = aset.size(src, 0)
            px, py = aset.anchor(*first)
            ctx.shadow(ent, key, src, ref.index, ax - px - dx, ay - py, size[0], size[1],
                       k, dep + (0, sub))
    hx, hy = ref.hotspot
    ctx.sprite(ent, key, ref.source, ref.index, ax - hx, ay - hy, wh[0], wh[1], dep + (0, 2))
    if ov is not None:
        bx, by = aset.anchor(*ov)
        ctx.sprite(ent, key, ref.source + "_b", ref.index, ax - bx, ay - by, ov[0], ov[1],
                   dep + (0, 3), "half")


def _destroyed(ent, aset):
    return bool((ent.flags & FLAG_DESTROYED) or ent.hp <= 0) \
        and not aset.rec.get("Indestructible") and "destroyed" in aset.actions


def _structure(ctx, ent):
    """Structure or bridge: P0 shadows (not bridges), P1 flat, P3 (a) slices."""
    opts = ctx.opts
    bridge = ent.kind == "bridge"
    aset = ctx.assets.structure_set(ent.type_id, ent.size if bridge else None)
    if aset is None:
        ctx.items.missing += 1
        return
    if bridge:
        cells, _ = piece_cells(aset, False, ctx.tick, opts.animate)
        sx_, sy_ = aset.w, aset.h
    else:
        cells, _ = piece_cells(aset, _destroyed(ent, aset), ctx.tick, opts.animate)
        sx_, sy_ = aset.W, aset.TH
    flat = bool(aset.rec.get("Flat"))
    g = fobj.ground_height(ctx.world.heights, (ent.x << 8) + 0x80, (ent.y << 8) + 0x80, sx_, sy_)
    sf = aset.sprites()
    if sf is None:
        ctx.items.missing += 1
        return
    ov = aset.overlay() if opts.smoothing else None
    key = ("bridge" if bridge else "structure", ent.type_id)
    X0, Y0 = CELL * ent.x, CELL * ent.y - g
    shadow_y = aset.rec.get("ShadowY", 0)
    for (c, r), parts in cells.items():
        x, y = ent.x + c, ent.y + r
        if not in_window(ctx.win, x, y):
            ctx.items.culled += 1
            continue
        for n, p in enumerate(parts):
            if p.index >= len(sf):
                if not n:
                    ctx.items.missing += 1
                continue
            w, h = sf[p.index].width, sf[p.index].height
            px, py = X0 + p.dx, Y0 + p.dy
            hasb = ov is not None and p.index < len(ov)
            if opts.shadows and not bridge:
                prow = (p.dy + CELL * (aset.FH - aset.TH)) // CELL
                sx = px + _trunc(ctx.T * ((aset.FH - prow) * CELL - shadow_y))
                dep = (PASS_SHADOW, y, -x, SLOT_STRUCTURE, ent.seq, n)
                ctx.shadow(ent, key, "main", p.index, sx, py, w, h, ctx.k1, dep + (0,))
                if hasb:
                    ctx.shadow(ent, key, "main_b", p.index, sx, py, ov[p.index].width,
                               ov[p.index].height, ctx.k2, dep + (1,))
            dep = (PASS_FLAT if flat else PASS_CELL, y, -x, SLOT_STRUCTURE, ent.seq, n)
            ctx.sprite(ent, key, "main", p.index, px, py, w, h, dep + (0,))
            if hasb:
                ctx.sprite(ent, key, "main_b", p.index, px, py, ov[p.index].width,
                           ov[p.index].height, dep + (1,), "half")


def _debug_items(ctx, debug):
    """Overlay items for the DebugFlags set in `debug` (attributes passability, markers, depth)."""
    out = []
    vx, vy, w, hv = ctx.win
    world, relief = ctx.world, ctx.relief
    if getattr(debug, "passability", False):
        blocked = ~world.walkable(WALKER)
        for y in range(max(vy, 0), min(vy + hv, world.height)):
            for x in range(max(vx, 0), min(vx + w, world.width)):
                if blocked[y, x]:
                    out.append(DrawItem("passability", None, None, 0, CELL * x - ctx.cx,
                                        CELL * y - int(relief[y, x]) - ctx.cy, CELL, CELL,
                                        depth=(PASS_DEBUG, y, -x, 0, 0, 0, 0)))
    if getattr(debug, "markers", False):
        for ent in world.objects.values():
            if not ctx.opts.objects:
                continue
            for dx, dy, _solid in ent.footprint:
                x, y = ent.x + dx, ent.y + dy
                if in_window(ctx.win, x, y) and 0 <= x < world.width and 0 <= y < world.height:
                    out.append(DrawItem("marker", ent.id, None, 0, CELL * x - ctx.cx,
                                        CELL * y - int(relief[y, x]) - ctx.cy, CELL, CELL,
                                        depth=(PASS_DEBUG, y, -x, 1, ent.seq, dx + 100 * dy, 0)))
            if in_window(ctx.win, ent.x, ent.y):
                z = int(relief[ent.y, ent.x])
                if ent.kind == "object":
                    hx, hy = CELL * ent.x + CELL // 2, CELL * ent.y + CELL // 2 - z
                else:
                    hx, hy = CELL * ent.x, CELL * ent.y - z
                out.append(DrawItem("marker", ent.id, None, 0, hx - ctx.cx, hy - ctx.cy, 1, 1,
                                    text="hotspot", depth=(PASS_DEBUG, ent.y, -ent.x, 2, ent.seq, 0, 0)))
    if getattr(debug, "depth", False):
        for it in ctx.items:
            if it.kind == "sprite" and it.blend != "half":
                p, row, ncol, slot, seq = it.depth[:5]
                out.append(DrawItem("depth", it.entity, None, 0, it.sx, it.sy, it.w, it.h,
                                    text="P%d r%d c%d s%d" % (p, row, -ncol, slot),
                                    depth=(PASS_DEBUG, row, ncol, 3, seq) + tuple(it.depth[5:])))
    return out


def build_draw_list(world, camera, tick, assets, options=None, debug=None):
    """Sprites (and requested debug overlays) of map objects and structures for
    `camera`, in drawing order: sorted by `DrawItem.depth` =
    (pass, row, -col, slot, seq, part, sub) (the exe's scan order, docs/engine/rendering.md).
    Reads the world only.  `assets`: an `AssetCache`; `options`: `DrawOptions`;
    `debug`: any object with boolean `passability`, `markers`, `depth`."""
    opts = options or DrawOptions()
    ctx = _Ctx(world, camera, tick, assets, opts)
    if opts.objects:
        for ent in world.objects.values():
            if ent.kind == "object":
                _objects(ctx, ent)
            else:
                _structure(ctx, ent)
    ctx.items.sort(key=lambda i: i.depth)
    if debug is not None:
        ctx.items.extend(sorted(_debug_items(ctx, debug), key=lambda i: i.depth))
    return ctx.items
