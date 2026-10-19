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

from .pick import PickRect

CELL = TILE
PASS_SHADOW, PASS_FLAT, PASS_GROUND_ITEMS, PASS_CELL, PASS_FLYER_SHADOW, PASS_FLYER, PASS_OVERLAY, PASS_DEBUG = \
    0, 1, 2, 3, 4, 7, 8, 9
SLOT_STRUCTURE, SLOT_UNIT, SLOT_STEAM, SLOT_OBJECT, SLOT_FIRE = range(5)
SLOT_CORPSE, SLOT_BACKPACK = 0, 1           # inside P2
BACKPACK = "graphics/backpack/sprites"       # + .256 / b.256, 6 frames (FUN_00461292)
BACKPACK_KEY = ("backpack", 0)
MAX_BACKPACK_FRAME = 5
FLYER_ALTITUDE = 16             # U+0x10 set by the flyer constructor 0x46bfc1 (CONFIRMED)
IDLE = "idle"                   # engine.world.IDLE (the view must not import it)
WALKER = 1                      # mover for the passability overlay (mask 0x41)
MANA_TIER = 3                   # `bar` tier of the mana bar (blue)
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
    units: bool = True          # units and ground piles
    health_bars: bool = False   # Ctrl+H: the selection bar of every unit
    flying_damage: bool = True  # "Flying damage" (view+0xabc, default on, Ctrl+L): floating damage numbers (combat.md section 8)


@dataclass(frozen=True)
class DrawItem:
    kind: str                   # "sprite" | "shadow" | "marker" | "passability" | "depth" | "bar" | "searched" | "path" | "hop"
    entity: int = None          # world id
    sprite: tuple = None        # (set_kind "object"|"structure"|"bridge"|"unit"|"backpack", type_id, source)
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
    remap: tuple = None         # units: (human.pal row, palette<N>.pal variant); None for the rest (CONFIRMED lighting §4)
    depth: tuple = ()
    shear: int = 0              # 16.16 shear of a shadow
    text: str = None            # depth label; "hotspot" for a marker cross
    bar: tuple = None           # "bar": (fill_px, track_px, tier), tier 0 green / 1 yellow / 2 red


class DrawList(list):
    """Items in drawing order; `missing` counts entities whose sprite is absent
    (the game draws nothing for them), `culled` those outside the window."""
    missing = 0
    culled = 0
    picks = ()                  # PickRect of the drawn units, in draw order


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
        self.picks = []
        self.relief = relief_grid(world.heights)

    def visible(self, sx, sy, w, h, lo=0, hi=0):
        return (sx + w + hi > 0 and sx + lo < self.cam.view_w
                and sy + h > 0 and sy < self.cam.view_h)

    def sprite(self, ent, key, src, idx, x, y, w, h, depth, blend="opaque", mirrored=False, remap=None):
        sx, sy = x - self.cx, y - self.cy
        if self.visible(sx, sy, w, h):
            self.items.append(DrawItem("sprite", ent.id, (key[0], key[1], src), idx, sx, sy, w, h,
                                       mirrored=mirrored, blend=blend, light_row=self.row,
                                       remap=remap, depth=depth))

    def shadow(self, ent, key, src, idx, x, y, w, h, k, depth, mirrored=False, shear=None):
        sx, sy = x - self.cx, y - self.cy
        shear = self.shear if shear is None else shear
        _, lo, hi = shadow_offsets(h, shear)
        if self.visible(sx, sy, w, h, lo, hi):
            self.items.append(DrawItem("shadow", ent.id, (key[0], key[1], src), idx, sx, sy, w, h,
                                       mirrored=mirrored, blend="shadow", shadow=True,
                                       shadow_level=k, depth=depth, shear=shear))


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


# --- units and ground piles ----------------------------------------------------------------

def unit_position(u, size=1):
    """(X, Y, cell_x, cell_y) of a unit: the exe's filing position `pos - 0x80 + size * 0x80`
    (1/256 cell; FUN_0046025d, CONFIRMED) and the cell it is filed under, `>> 8`.  A 1 x 1 unit
    is filed under its own cell, a larger one under the cell of its footprint centre."""
    X = ((u.x << 8) | u.sub_x) - 0x80 + size * 0x80
    Y = ((u.y << 8) | u.sub_y) - 0x80 + size * 0x80
    return X, Y, X >> 8, Y >> 8


def death_stage(hp):
    """`engine.world.death_stage` (the view must not import it): 0 alive, 1 dying / corpse, 2..4 bones, 5 not drawn."""
    if hp > 0:
        return 0
    return 1 if hp >= -10 else 2 if hp >= -20 else 3 if hp >= -40 else 4 if hp >= -600 else 5


def unit_frame(aset, u, tick):
    """FrameRef of unit `u` at world tick `tick`: its action's frame at `tick - action_start_tick`
    (animation time comes from the simulation, never from the render clock).  A unit with HP <= 0 is drawn by its death stage (combat.md 12.6):
    1 the dying animation from `death_tick` (once, then it holds the corpse frame), 2-4 bones 1-3, 5 nothing (None)."""
    if u.hp <= 0:
        stage = death_stage(u.hp)
        facing = (u.facing >> 4) & 15
        if stage == 5:
            return None
        if stage == 1:
            if u.death_tick is not None and "dying" in aset.actions:
                return aset.frame_at("dying", facing, tick - u.death_tick)
            if "corpse" in aset.actions:
                return aset.frame_at("corpse", facing, 0)
        elif "bones%d" % (stage - 1) in aset.actions:
            return aset.frame_at("bones%d" % (stage - 1), facing, 0)
        return None
    action = aset.idle_action if u.action == IDLE else u.action
    if action == "turn":                                # the stand frame of the stepping facing
        action = "stand"
    if action == "move":                                # distance-driven: 1 frame per 16 units walked
        return aset.frame_at(action, (u.facing >> 4) & 15, tick - u.action_start_tick, odometer=u.odometer)
    return aset.frame_at(action, (u.facing >> 4) & 15, tick - u.action_start_tick)


def unit_remap(world, u):
    """(human.pal row, variant) of a unit: the owner's colour for Palette = 0 types, `face - 1`
    for the others (the unit set picks which applies; INFERRED variant mapping, units.md)."""
    p = world.players.get(u.owner)
    return (p.colour if p is not None else 0, max(u.face - 1, 0))


def _unit(ctx, u):
    """Ground unit, P3 (b): shadow main, shadow b, sprite, b overlay at 50 % (0x464487, 0x4632a1)."""
    opts = ctx.opts
    aset = ctx.assets.unit_set(u.type_id)
    if aset is None:
        ctx.items.missing += 1
        return
    X, Y, cx, cy = unit_position(u, aset.t.TileSize)
    if not in_window(ctx.win, cx, cy):
        ctx.items.culled += 1
        return
    ref = unit_frame(aset, u, ctx.tick)
    if ref is None:                                     # death stage 5 or no death frames
        return
    wh = aset.size(ref.source, ref.index)
    if wh is None:
        ctx.items.missing += 1
        return
    z = fobj.ground_height(ctx.world.heights, (u.x << 8) | u.sub_x, (u.y << 8) | u.sub_y,
                           aset.t.TileSize, aset.t.TileSize)
    px, py = (X * CELL) >> 8, (Y * CELL) >> 8
    key = ("unit", u.type_id)
    flyer = bool(aset.t.Z)                      # units.reg Z != 0: the 0x5cd660 view class, layers P4 / P7
    alt = FLYER_ALTITUDE if flyer else 0        # U+0x10: raises the sprite, never the shadow
    dep = (PASS_FLYER if flyer else PASS_CELL, cy, -cx, SLOT_UNIT, u.seq)
    ov = aset.size(ref.source + "_b", ref.index) if opts.smoothing else None
    remap = unit_remap(ctx.world, u)
    hx, hy = ref.hotspot
    if opts.shadows:
        t = aset.t
        # ground: sheared, x - dx; flyer (P4): the unsheared blitter at x + trunc(shear / 2000)
        dx = _trunc(ctx.shear / 2000) if flyer else -_trunc(ctx.T * (wh[1] // 2 + t.Height // 2 - t.CenterY))
        sdep = (PASS_FLYER_SHADOW,) + dep[1:] if flyer else dep
        for sub, src, size, k in ((0, ref.source, wh, ctx.k1), (1, ref.source + "_b", ov, ctx.k2)):
            if size is None:
                continue
            ax, ay = aset.anchor(*size)
            ctx.shadow(u, key, src, ref.index, px - ax + dx, py - ay - z, size[0], size[1], k,
                       sdep + (0, sub), ref.mirrored, 0 if flyer else None)
    ctx.sprite(u, key, ref.source, ref.index, px - hx, py - hy - z - alt, wh[0], wh[1], dep + (0, 2),
               mirrored=ref.mirrored, remap=remap)
    t = aset.t
    ox, oy = px - t.CenterX - ctx.cx, py - t.CenterY - z - alt - ctx.cy
    if death_stage(u.hp) < 2:                           # the pick rect is registered while the death stage is < 2 (0x4087c2, combat.md 12.2)
        ctx.picks.append((dep, PickRect(u.id, t.SelectionX1 + ox, t.SelectionY1 + oy,
                                        t.SelectionX2 + ox, t.SelectionY2 + oy)))
    if ov is not None:
        bx, by = aset.anchor(*ov)
        ctx.sprite(u, key, ref.source + "_b", ref.index, px - bx, py - by - z - alt, ov[0], ov[1],
                   dep + (0, 3), "half", ref.mirrored, remap)


def backpack_frame(gold):
    """Frame of a pile: `min(5, floor(log10(total)))` (FUN_0052a895 sent in message 0x7a; the
    items' own `+0x1c` is not decoded, so only the gold counts), 0 when empty."""
    return min(MAX_BACKPACK_FRAME, len(str(gold)) - 1) if gold > 0 else 0


def _item(ctx, it):
    """Ground pile, P2 after the corpses: shadow main, shadow b (no Smoothing gate), sprite,
    b overlay (Smoothing).  FUN_00461292 / 0x4611bf: anchor the cell centre, frame-0 size."""
    if not in_window(ctx.win, it.x, it.y):
        ctx.items.culled += 1
        return
    sf = ctx.assets.sprite(BACKPACK + ".256")
    frame = backpack_frame(it.gold)
    if sf is None or frame >= len(sf):
        ctx.items.missing += 1
        return
    sfb = ctx.assets.sprite(BACKPACK + "b.256")
    ow = (sfb[frame].width, sfb[frame].height) if sfb is not None and frame < len(sfb) else None
    w0, h0 = sf[0].width, sf[0].height
    z = int(ctx.relief[it.y, it.x])
    X, Y = CELL * it.x + CELL // 2, CELL * it.y + CELL // 2 - z
    x, y = X - w0 // 2, Y - h0 // 2 - 4
    dep = (PASS_GROUND_ITEMS, it.y, -it.x, SLOT_BACKPACK, it.seq)
    if ctx.opts.shadows:
        dx = _trunc(ctx.T * (h0 // 2))
        ctx.shadow(it, BACKPACK_KEY, "main", frame, x - dx, y, sf[frame].width, sf[frame].height,
                   ctx.k1, dep + (0, 0))
        if ow is not None:
            ctx.shadow(it, BACKPACK_KEY, "main_b", frame, x - dx, y, ow[0], ow[1], ctx.k2,
                       dep + (0, 1))
    ctx.sprite(it, BACKPACK_KEY, "main", frame, x, y, sf[frame].width, sf[frame].height, dep + (0, 2))
    if ow is not None and ctx.opts.smoothing:
        ctx.sprite(it, BACKPACK_KEY, "main_b", frame, x, y, ow[0], ow[1], dep + (0, 3), "half")


def _debug_items(ctx, debug, selection=(), ai_info=None):
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
    if getattr(debug, "paths", False):
        out.extend(_path_items(ctx, selection))
    if getattr(debug, "ai", False) and ai_info:
        out.extend(_ai_items(ctx, ai_info))
    if getattr(debug, "depth", False):
        for it in ctx.items:
            if it.kind == "sprite" and it.blend != "half":
                p, row, ncol, slot, seq = it.depth[:5]
                out.append(DrawItem("depth", it.entity, None, 0, it.sx, it.sy, it.w, it.h,
                                    text="P%d r%d c%d s%d" % (p, row, -ncol, slot),
                                    depth=(PASS_DEBUG, row, ncol, 3, seq) + tuple(it.depth[5:])))
    return out


def _path_items(ctx, selection):
    """Path overlay of the selected units (docs/engine/simulation.md 7): "searched" = cells the last static
    plan labelled, "path" = the rest of the static plan, "hop" = the dynamic list being walked."""
    out = []
    relief = ctx.relief

    def cell(kind, x, y, n):
        if in_window(ctx.win, x, y) and 0 <= x < ctx.world.width and 0 <= y < ctx.world.height:
            out.append(DrawItem(kind, None, None, 0, CELL * x - ctx.cx, CELL * y - int(relief[y, x]) - ctx.cy,
                                CELL, CELL, depth=(PASS_DEBUG, y, -x, 4 + n, 0, 0, 0)))

    for uid in selection:
        u = ctx.world.units.get(uid)
        if u is None:
            continue
        m = u.mover
        if m.last_plan is not None and m.goal is not None:
            for x, y in m.last_plan.searched:
                cell("searched", x, y, 0)
        for x, y in m.static_path:
            cell("path", x, y, 1)
        for x, y in u.path:
            cell("hop", x, y, 2)
    return out


def _ai_items(ctx, ai_info):
    """AI overlay of the selected monsters (docs/engine/ai.md 10): `ai_info` = {unit id: sim.ai.overlay(...)}, computed by the backend."""
    out, relief = [], ctx.relief

    def cell(kind, x, y, n):
        if in_window(ctx.win, x, y) and 0 <= x < ctx.world.width and 0 <= y < ctx.world.height:
            out.append(DrawItem(kind, None, None, 0, CELL * x - ctx.cx, CELL * y - int(relief[y, x]) - ctx.cy,
                                CELL, CELL, depth=(PASS_DEBUG, y, -x, 8 + n, 0, 0, 0)))

    for uid, info in sorted(ai_info.items()):
        u = ctx.world.units.get(uid)
        if u is None or info is None:
            continue
        for x, y in sorted(info["sight"]):
            cell("ai_sight", x, y, 0)
        for x, y in sorted(info["ring"]):
            cell("ai_radius", x, y, 1)
        if info["post"]:
            cell("ai_post", *info["post"], 2)
        if info["target"]:
            cell("ai_target", *info["target"], 3)
        if in_window(ctx.win, u.x, u.y):
            out.append(DrawItem("ai_text", uid, None, 0, CELL * u.x - ctx.cx, CELL * u.y - int(relief[u.y, u.x]) - ctx.cy - 40, 1, 1,
                                text=info["label"], depth=(PASS_DEBUG, u.y, -u.x, 12, 0, 0, 0)))
    return out


def _bars(ctx, selection, hover=None):
    """Selection bars (FUN_004653a5, ui-layout.md section 9): the HP bar on the top edge of each selected or hovered unit's pick rect (every
    drawn unit with `DrawOptions.health_bars`), and the mana bar 4 px lower for a unit with mana (`obj+0x14a > 0`)."""
    chosen = set(selection)
    if hover is not None:
        chosen.add(hover)
    out = []
    for n, r in enumerate(ctx.items.picks):
        u = ctx.world.units.get(r.entity)
        if u is None or u.hp_max <= 0 or not (ctx.opts.health_bars or r.entity in chosen):
            continue
        track = max(r.x2 - r.x1 - 8, 0)
        hp = max(u.hp, 0)
        fill = max(1, hp * track // u.hp_max) if hp > 0 else 0
        tier = 2 if hp * 4 < u.hp_max else 1 if hp * 2 < u.hp_max else 0
        out.append(DrawItem("bar", r.entity, None, 0, r.x1, r.y1 - 2, r.x2 - r.x1, 4,
                            depth=(PASS_OVERLAY, n, 0, 0, 0), bar=(min(fill, track), track, tier)))
        if u.mana_max > 0:
            mfill = max(1, u.mana * track // u.mana_max) if u.mana > 0 else 0
            out.append(DrawItem("bar", r.entity, None, 0, r.x1, r.y1 + 2, r.x2 - r.x1, 4,
                                depth=(PASS_OVERLAY, n, 1, 0, 0), bar=(min(mfill, track), track, MANA_TIER)))
    return out


def build_draw_list(world, camera, tick, assets, options=None, debug=None, selection=(), hover=None, ai_info=None):
    """Sprites (and requested debug overlays) of map objects and structures for
    `camera`, in drawing order: sorted by `DrawItem.depth` =
    (pass, row, -col, slot, seq, part, sub) (the exe's scan order, docs/engine/rendering.md).
    Reads the world only.  `assets`: an `AssetCache`; `options`: `DrawOptions`;
    `debug`: any object with boolean `passability`, `markers`, `depth`; `selection`: unit ids that
    get a selection bar, `hover`: the unit id under the pointer (it gets bars too).  `DrawList.picks` holds the unit pick rects in draw order."""
    opts = options or DrawOptions()
    ctx = _Ctx(world, camera, tick, assets, opts)
    if opts.objects:
        for ent in world.objects.values():
            if ent.kind == "object":
                _objects(ctx, ent)
            else:
                _structure(ctx, ent)
    if opts.units:
        for it in world.items.values():
            _item(ctx, it)
        for u in world.corpses.values():
            _unit(ctx, u)
        for u in world.units.values():
            _unit(ctx, u)
    ctx.items.sort(key=lambda i: i.depth)
    ctx.items.picks = [r for _, r in sorted(ctx.picks, key=lambda p: p[0] + (0, 2))]
    ctx.items.extend(_bars(ctx, selection, hover))
    if debug is not None:
        ctx.items.extend(sorted(_debug_items(ctx, debug, selection, ai_info), key=lambda i: i.depth))
    return ctx.items
