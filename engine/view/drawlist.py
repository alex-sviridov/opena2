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
from typing import NamedTuple

import numpy as np

from allods2.anim.lens import LENS_SIZE
from allods2.anim.scene import piece_cells
from allods2.anim.structures import BridgeSet
from allods2.formats import objects as fobj
from allods2.graphics import lighting as lt
from allods2.graphics.terrain import TILE

from . import fog
from .. import herolook
from .objmap import walk_order
from .lights import burning_entries, cell_row, corner_lights, light_map, tile_size
from .pick import PickRect

CELL = TILE
PASS_SHADOW, PASS_FLAT, PASS_GROUND_ITEMS, PASS_CELL, PASS_FLYER_SHADOW, PASS_PROJECTILE, PASS_FLYER, PASS_OVERLAY, PASS_DEBUG = \
    0, 1, 2, 3, 4, 6, 7, 8, 9
SLOT_STRUCTURE, SLOT_UNIT, SLOT_STEAM, SLOT_OBJECT, SLOT_FIRE, SLOT_CELL_FX = range(6)
INVISIBILITY_BIT, STONE_CURSE_BIT = 12, 18      # effect ids (`unit+0x144` bit = 1 << spell number); client list ids 0x20 / 0x2c
SLOT_CORPSE, SLOT_BACKPACK = 0, 1           # inside P2
BACKPACK = "graphics/backpack/sprites"       # + .256 / b.256, 6 frames (FUN_00461292)
BACKPACK_KEY = ("backpack", 0)
MAX_BACKPACK_FRAME = 5
FLYER_ALTITUDE = 16             # U+0x10 set by the flyer constructor 0x46bfc1 (CONFIRMED)
IDLE = "idle"                   # engine.world.IDLE (the view must not import it)
WALKER = 1                      # mover for the passability overlay (mask 0x41)
MANA_TIER = 3                   # `bar` tier of the mana bar (blue)
FLAG_DESTROYED = 1              # engine.world.FLAG_DESTROYED (view must not import it)


class TerrainItem(NamedTuple):
    """One visible terrain cell (a tuple: ~1000 are built per frame)."""
    col: int
    row: int
    phase: int            # water animation phase 0..3 (0 for static cells)
    sx: int               # screen x of the cell's first pixel column
    lit: tuple = None     # the four corner lights (TL, TR, BL, BR) of a cell under a dynamic light (`FUN_00405cf4`), else None

    @property
    def key(self):
        return (self.col, self.row, self.phase, self.lit)


def build_terrain_items(terrain_view, camera, tick, lights=None):
    """Terrain items of the visible cells, row by row top to bottom (later rows
    overwrite earlier ones), animation clock = `tick`.  `lights`: the dynamic light map of the frame (`DrawList.lights`), cells with a lit
    corner get `lit` = min(terrain light, light) per corner."""
    x0, x1, y0, y1 = terrain_view.proj.visible_cells(camera)
    cx = camera.ix
    phases = terrain_view.phase_grid(x0, x1, y0, y1, tick)
    if not lights:
        return [TerrainItem(col, row, ph, col * TILE - cx)
                for row, prow in zip(range(y0, y1), phases) for col, ph in zip(range(x0, x1), prow)]
    base = terrain_view.light
    return [TerrainItem(col, row, ph, col * TILE - cx, corner_lights(lights, base, col, row))
            for row, prow in zip(range(y0, y1), phases) for col, ph in zip(range(x0, x1), prow)]


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
    lights: bool = True         # "Lighting" DAT_005f17f0: structure and projectile lights (lights.py); also needs `lit` (the unlit parity modes draw none)
    flying_damage: bool = True  # "Flying damage" (view+0xabc, default on, Ctrl+L): floating damage numbers (combat.md section 8)


@dataclass(frozen=True)
class DrawItem:
    kind: str                   # "sprite" | "shadow" | "lens" | "marker" | "passability" | "depth" | "bar" | "searched" | "path" | "hop"
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
    gray: bool = False          # a Stone Curse unit: the GRAY shade table of its palette instead of BRIGHT2 (`FUN_004632a1`)
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
    lights = None              # the frame's dynamic light map {(vx, vy): value} (lights.py), for build_terrain_items
    hover_picks = ()            # units and hoverable structures merged, in draw order (the info panel's hover, ui-layout 7 / 10)


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

    def __init__(self, world, camera, tick, assets, opts, hover=None, hidden=None):
        self.world, self.cam, self.tick, self.assets, self.opts = world, camera, tick, assets, opts
        self.hidden = hidden or {}  # {unit id: creature slot whose item is on the cursor} (ui/pack.py `hidden_slot`): the hero is drawn without it
        self.hover = hover          # entity id under the pointer: that unit is drawn at light row 0 (`FUN_004632a1`, ui-layout 7)
        self.cx, self.cy = camera.ix, camera.iy
        self.win = view_window(camera)
        day = getattr(world, "daylight", None) or lt.daylight(0, False)     # TerrainView.set_clock
        self.row = lt.object_light_row(day.ambient) if opts.lit else None
        self.k1, self.k2 = day.shadow1, day.shadow2
        self.beta = lt.shadow_angle(day.angle)
        self.T = math.tan(self.beta)
        self.shear = lt.shadow_shear(day.angle)
        self.items = DrawList()
        self.lights = light_map(world, assets, tick) if opts.lights and opts.lit and opts.objects else {}
        self.items.lights = self.lights
        self.ambient = day.ambient
        self.picks = []
        self.struct_picks = []
        self.relief = relief_grid(world.heights)

    def row_at(self, x, y):
        """Light row of cell (x, y): the default, or the light-map row (`FUN_00404a2a`)."""
        if not self.lights or self.row is None:
            return self.row
        r = cell_row(self.lights, x, y, self.ambient)
        return self.row if r is None else r

    def visible(self, sx, sy, w, h, lo=0, hi=0):
        return (sx + w + hi > 0 and sx + lo < self.cam.view_w
                and sy + h > 0 and sy < self.cam.view_h)

    def sprite(self, ent, key, src, idx, x, y, w, h, depth, blend="opaque", mirrored=False, remap=None, row=None, gray=False):
        sx, sy = x - self.cx, y - self.cy
        if self.visible(sx, sy, w, h):
            self.items.append(DrawItem("sprite", ent.id, (key[0], key[1], src), idx, sx, sy, w, h,
                                       mirrored=mirrored, blend=blend, light_row=self.row if row is None or self.row is None else row,
                                       remap=remap, gray=gray, depth=depth))

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
    if aset.dead is not None and ctx.world.cells[y, x] & 0x2000:       # burnt cell (CONFIRMED `0x408b0f`/`0x408c10`): frame 0 of the DeadObject's file
        ref = aset.frame_at("dead", 0, ctx.tick)
    else:
        ref = aset.frame_at("anim" if aset.rec["seq"] else "still", 0, ctx.tick, x=x, y=y,
                            animate=opts.animate)
    st = _object_static(ctx, aset, ent.type_id, ref)
    if st is None:
        ctx.items.missing += 1
        return
    wh, ov, shadows, bxy, dx = st
    row = ctx.row_at(x, y)
    # the items of one object are a pure function of this key (DrawItem is immutable), so a still camera and a still frame
    # share them from one frame to the next; kept on the world (entity ids are per world), dropped past 4096 entries
    memo = ctx.world.__dict__.setdefault("_object_items", {})
    mk = (ent.id, ent.seq, ent.type_id, x, y, ref.source, ref.index, ctx.cx, ctx.cy, row, ctx.T, ctx.k1, ctx.k2,
          opts.smoothing, opts.shadows, ctx.cam.view_w, ctx.cam.view_h)
    hit = memo.get(mk)
    if hit is not None:
        ctx.items.extend(hit)
        return
    n0 = len(ctx.items)
    z = int(ctx.relief[y, x])
    ax, ay = CELL * x + CELL // 2, CELL * y + CELL // 2 - z           # the anchor
    key = ("object", ent.type_id)
    dep = (PASS_CELL, y, -x, SLOT_OBJECT, ent.seq)
    for sub, src, size, px, py, k in shadows:
        ctx.shadow(ent, key, src, ref.index, ax - px - dx, ay - py, size[0], size[1], k, dep + (0, sub))
    hx, hy = ref.hotspot
    ctx.sprite(ent, key, ref.source, ref.index, ax - hx, ay - hy, wh[0], wh[1], dep + (0, 2), row=row)
    if ov is not None:
        ctx.sprite(ent, key, ref.source + "_b", ref.index, ax - bxy[0], ay - bxy[1], ov[0], ov[1],
                   dep + (0, 3), "half", row=row)
    if len(memo) > 4096:
        memo.clear()
    memo[mk] = tuple(ctx.items[n0:])


def _object_static(ctx, aset, type_id, ref):
    """What `_objects` needs of a frame that does not depend on the object's place or the camera: sizes, anchors, the shadow shift.
    Cached on the asset cache per (type, source, frame, shadow angle, options); None = the frame is missing."""
    opts = ctx.opts
    cache = ctx.assets.__dict__.setdefault("_object_static", {})
    ck = (type_id, ref.source, ref.index, ctx.T, ctx.k1, ctx.k2, opts.smoothing, opts.shadows)
    if ck in cache:
        return cache[ck]
    wh = aset.size(ref.source, ref.index)
    if wh is None:
        cache[ck] = None
        return None
    ov = aset.size(ref.source + "_b", ref.index) if opts.smoothing else None
    shadows, dx = [], 0
    if opts.shadows:
        r = aset.rec
        dx = _trunc(ctx.T * (wh[1] // 2 + r["Height"] // 2 - r["CenterY"]))       # main's, for both
        for sub, src, size, ok, k in ((0, ref.source, wh, True, ctx.k1), (1, ref.source + "_b", ov, ov is not None, ctx.k2)):
            if ok:
                px, py = aset.anchor(*aset.size(src, 0))
                shadows.append((sub, src, size, px, py, k))
    cache[ck] = out = (wh, ov, tuple(shadows), aset.anchor(*ov) if ov is not None else None, dx)
    return out


def _destroyed(ent, aset):
    return bool((ent.flags & FLAG_DESTROYED) or ent.hp <= 0) \
        and not aset.rec.get("Indestructible") and "destroyed" in aset.actions


def structure_hoverable(ent, aset):
    """The view registers a pick rect for every structure it draws in sight (`FUN_00406f43` `0x408068` flat, `0x4086b7` the rest; the test is the
    visibility state `obj+0x7c` == 0, **not** a death stage: a destroyed structure stays pickable), and the hover loop of `FUN_004180c6` skips it when
    it is Indestructible (`+0x64`) and not Usable (`+0x8c`) (CONFIRMED)."""
    rec = aset.rec
    return bool(rec.get("Usable")) or not rec.get("Indestructible")


def pick_cell(win, x, y, w, h):
    """Footprint cell whose draw registers the structure's pick rect last (CONFIRMED `FUN_0046025d`, `FUN_00406f43`): the view registers the rect in
    **every** cell of the box (x .. x + w - 1, y .. y + h - 1) clipped to the drawn window (`FUN_00460591` kind 1), rows ascending and x descending, so
    the last registration (the one that decides the order against units) is the clipped box's smallest x in its largest y row.  None = box outside."""
    vx, vy, ww, hv = win
    x1, x2 = max(x - vx, -3), min(x + w - 1 - vx, ww + 2)
    y1, y2 = max(y - vy, -3), min(y + h - 1 - vy, hv + 6)
    if x1 > x2 or y1 > y2 or x + w - 1 - vx < -3 or y + h - 1 - vy < -3:
        return None
    return vx + x1, vy + y2


def _structure(ctx, ent):
    """Structure or bridge: P0 shadows (not bridges), P1 flat, P3 (a) slices."""
    opts = ctx.opts
    bridge = ent.kind == "bridge"
    state = fog.structure_state(ctx.world, ent)         # 0 in sight, 1 explored (frozen, not pickable), 2 never seen (not drawn)
    if state == 2:
        return
    animate = opts.animate and state == 0
    aset = ctx.assets.structure_set(ent.type_id, ent.size if bridge else None)
    if aset is None:
        ctx.items.missing += 1
        return
    if bridge:
        cells, _ = piece_cells(aset, False, ctx.tick, animate)
        sx_, sy_ = aset.w, aset.h
    else:
        cells, _ = piece_cells(aset, _destroyed(ent, aset), ctx.tick, animate)
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
    pc = None if bridge or state != 0 or not structure_hoverable(ent, aset) else pick_cell(ctx.win, ent.x, ent.y, aset.W, aset.TH)
    if pc is not None:
        ox, oy = X0 - ctx.cx, Y0 + (aset.TH - aset.FH) * CELL - ctx.cy      # `0x4085ac`-`0x4086b7`: (x << 5, ((y + TH - FH) << 5) - ground)
        r = aset.rec
        ctx.struct_picks.append(((PASS_FLAT if flat else PASS_CELL, pc[1], -pc[0], SLOT_STRUCTURE, ent.seq, 0),
                                 PickRect(ent.id, r.get("SelectionX1", -1) + ox, r.get("SelectionY1", -1) + oy,
                                          r.get("SelectionX2", -1) + ox, r.get("SelectionY2", -1) + oy)))
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
            row = ctx.row_at(x, y)                      # one row per footprint cell, for every piece of its column (lighting.md section 4)
            ctx.sprite(ent, key, "main", p.index, px, py, w, h, dep + (0,), row=row)
            if hasb:
                ctx.sprite(ent, key, "main_b", p.index, px, py, ov[p.index].width,
                           ov[p.index].height, dep + (1,), "half", row=row)


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


def unit_frame(aset, u, tick, frozen=False):
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
                return aset.frame_at("dying", facing, 0 if frozen else tick - u.death_tick)     # Stone Curse: phase 0 (INFERRED: the frame index is the facing alone)
            if "corpse" in aset.actions:
                return aset.frame_at("corpse", facing, 0)
        elif "bones%d" % (stage - 1) in aset.actions:
            return aset.frame_at("bones%d" % (stage - 1), facing, 0)
        return None
    action = aset.idle_action if u.action == IDLE else u.action
    if frozen:                                          # Stone Curse: the frame index is the facing alone (`0x4632a1`): phase 0 of the action
        return aset.frame_at(action if action != "turn" else "stand", (u.facing >> 4) & 15, 0)
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
    if not fog.unit_visible(ctx.world, u):              # S != 0: neither the sprite, the shadow nor the pick rect (vision.md 2)
        return
    skey = herolook.look_key(ctx.world, ctx.assets, u, ctx.hidden.get(u.id, 0)) or u.type_id     # a hero is drawn from its equipment's folder (herolook.py)
    aset = ctx.assets.unit_set(skey)
    if aset is None:
        ctx.items.missing += 1
        return
    X, Y, cx, cy = unit_position(u, aset.t.TileSize)
    if not in_window(ctx.win, cx, cy):
        ctx.items.culled += 1
        return
    mask = u.effect_mask
    invisible = bool(u.hidden or mask >> INVISIBILITY_BIT & 1)
    if invisible and u.owner != ctx.world.fog_viewer:   # effect 0x20 and the owner is not the viewer (`FUN_0041e860`, player flag 8): nothing at all
        return
    stone = bool(mask >> STONE_CURSE_BIT & 1) and death_stage(u.hp) <= 2     # effect 0x2c: frozen frame, GRAY table, death stage <= 2 (`0x463b5c`; the effect pass runs for dying units, effects.md 6)
    ref = unit_frame(aset, u, ctx.tick, stone)
    if ref is None:                                     # death stage 5 or no death frames
        return
    wh = aset.size(ref.source, ref.index)
    if wh is None:
        ctx.items.missing += 1
        return
    z = fobj.ground_height(ctx.world.heights, (u.x << 8) | u.sub_x, (u.y << 8) | u.sub_y,
                           aset.t.TileSize, aset.t.TileSize)
    px, py = (X * CELL) >> 8, (Y * CELL) >> 8
    key = ("unit", skey)
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
        for sub, src, size, k in ((0, ref.source, wh, ctx.k2 if invisible else ctx.k1), (1, ref.source + "_b", None if invisible else ov, ctx.k2)):
            if size is None:                            # an invisible unit casts the lighter main shadow only (0x6226d0, no `b` shadow)
                continue
            ax, ay = aset.anchor(*size)
            ctx.shadow(u, key, src, ref.index, px - ax + dx, py - ay - z, size[0], size[1], k,
                       sdep + (0, sub), ref.mirrored, 0 if flyer else None)
    row = 0 if ctx.hover == u.id else ctx.row_at(cx, cy)              # the hovered unit's sprite and overlay take light row 0 (x2 brightness; shadows take no row)
    ctx.sprite(u, key, ref.source, ref.index, px - hx, py - hy - z - alt, wh[0], wh[1], dep + (0, 2),
               "half" if invisible else "opaque", ref.mirrored, remap, row, stone)     # the viewer's own invisible unit: the 50 % blit (vtable +0x34)
    t = aset.t
    ox, oy = px - t.CenterX - ctx.cx, py - t.CenterY - z - alt - ctx.cy
    if death_stage(u.hp) < 2:                           # the pick rect is registered while the death stage is < 2 (0x4087c2, combat.md 12.2)
        ctx.picks.append((dep, PickRect(u.id, t.SelectionX1 + ox, t.SelectionY1 + oy,
                                        t.SelectionX2 + ox, t.SelectionY2 + oy)))
    if ov is not None:
        bx, by = aset.anchor(*ov)
        ctx.sprite(u, key, ref.source + "_b", ref.index, px - bx, py - by - z - alt, ov[0], ov[1],
                   dep + (0, 3), "half", ref.mirrored, remap, row, stone)


CELL_FX = ((0, 15, 3), (3, 43, 17), (2, 21, 6))    # (cell record slot, projectiles.reg id, view flag bit = spell number): fire wall, wall of earth, poison cloud


def cell_fx_y(heights, vx, vy, col, row):
    """View-relative y of the cell effect sprite centre (`FUN_00409xxx` -> `FUN_0040af69`): `(min top edge + max bottom edge) / 2` of the view vertex
    table `vt(r, c) = 32 r - H[vy + r][vx + c]` (`+0xb8` / `+0xbc`, terrain.md), halved toward 0."""
    h, w = heights.shape

    def vt(r, c):
        return 32 * r - int(np.int8(heights[min(max(vy + r, 0), h - 1), min(max(vx + c, 0), w - 1)]))
    top = min(vt(row, col), vt(row, col + 1))
    bottom = max(vt(row + 1, col), vt(row + 1, col + 1))
    return _trunc((top + bottom) / 2)


def _cell_effects(ctx):
    """Cell effect sprites (`FUN_0040af69`, CONFIRMED): fire wall (view flag bit 3: frame `3 + n % 5`) and wall of earth (bit 17: `n % Phases`, one frame)
    in pass 3 after the cell's other entities, poison cloud (bit 6: `n % Phases`) in pass 6 after the missiles; `n = |tick / 2 + x * y|` with the
    view-relative `x = 32 col + 16`, `y` = `cell_fx_y`.  The frame is placed by its box (record Width x Height) centred on (x, y).  Gate: the cell is in
    sight (tile words OR `0xc000`).  The flags come from the server's cell slots (`World.cell_fx`; the client mirrors them by message 0x87)."""
    w = ctx.world
    vx, vy = ctx.win[0], ctx.win[1]
    for (cx, cy), slots in w.cell_fx.items():
        if not in_window(ctx.win, cx, cy) or not fog.cell_visible(w, cx, cy):
            continue
        col, row = cx - vx, cy - vy
        x, y = 32 * col + 16, cell_fx_y(w.heights, vx, vy, col, row)
        n = abs(_trunc(ctx.tick / 2) + x * y)
        for k, (slot, pid, bit) in enumerate(CELL_FX):
            if slots[slot] is None:
                continue
            poison = bit == 6
            if poison and not (0 <= col < ctx.win[2] and 0 <= row <= ctx.win[3] + 3):      # pass 6 scans rows 0..Hv+3, cols 0..W-1
                continue
            pset = ctx.assets.projectile_set(pid)
            if pset is None:
                ctx.items.missing += 1
                continue
            phases = max(pset.rec["Phases"], 1)
            idx = 3 + n % 5 if bit == 3 else n % phases
            wh = pset.size("main", idx)
            if wh is None:
                ctx.items.missing += 1
                continue
            sx = 32 * vx + x - pset.rec["Width"] // 2 - ctx.cx
            sy = 32 * vy + y - pset.rec["Height"] // 2 - ctx.cy
            if ctx.visible(sx, sy, wh[0], wh[1]):
                depth = ((PASS_PROJECTILE, (1 << 20) + cy, -cx, 0, 0) if poison else (PASS_CELL, cy, -cx, SLOT_CELL_FX, k))
                ctx.items.append(DrawItem("sprite", -1, ("projectile", pid, "main"), idx, sx, sy, wh[0], wh[1],
                                          blend="alpha" if pset.rec["A16"] else "opaque", light_row=None, depth=depth))


BURN_STEAM_TICKS = 18       # steam draws while the list counter is below 18 (`0x4088b8`); the entry itself lives to 22 (`0x40c0f3`)
STEAM_PROJECTILE, FIRE_PROJECTILE = 8, 15


def _has_object(w, x, y):
    return any(w.objects[i].kind == "object" for i in w.objects_at(x, y))


def _burning_sprites(ctx):
    """Burning-list sprites (`view+0xa94`, CONFIRMED): per cell of the P3 scan, steam (`0x40883f`-`0x40895c`, before the map object: slot 2) when the
    entry's cell is water (tile word `& 0x1fff >> 6` in 8..11) and counter < 18: projectile 8, frame `counter >> 1`; fire (`0x409406`-`0x40949c`,
    after the object: slot 4): projectile 15 `firewall`, frame `counter >> 1`.  Both are the record's `Width x Height` box centred on
    `(32 X + 16, 32 Y + 16 - relief)` (relief = the cell's mean corner height, as for objects), `.16a` alpha, no light row.
    Gates (CONFIRMED): steam needs the Lighting option (`0x5f17f0`), fire needs a map object on the cell (inside the object gate `0x408981`, then
    `FUN_0040b117` = 0, skipped only when every fog vertex of the object's box is 16 = black, invisible); no fog (tile `0xc000`) test on either."""
    w = ctx.world
    for x, y, counter in burning_entries(w, ctx.assets, ctx.tick):
        if not in_window(ctx.win, x, y):
            continue
        water = 8 <= (int(w.cells[y, x]) & 0x1FFF) >> 6 < 12
        # steam: only with the Lighting option (`cmp [0x5f17f0], 0` at `0x40883f`); fire: only on a cell with a map object (the block `0x409406` is
        # inside the object gate `0x408981`); neither tests the fog (`0xc000`) words, projectiles and explosions neither (`FUN_0046cb7b`, list `0x40984e`)
        kinds = ((STEAM_PROJECTILE, SLOT_STEAM),) if water and counter < BURN_STEAM_TICKS and ctx.opts.lights else ()
        if _has_object(w, x, y):
            kinds += ((FIRE_PROJECTILE, SLOT_FIRE),)
        for pid, slot in kinds:
            pset = ctx.assets.projectile_set(pid)
            if pset is None:
                ctx.items.missing += 1
                continue
            idx = counter >> 1
            wh = pset.size("main", idx)
            if wh is None:
                ctx.items.missing += 1
                continue
            sx = CELL * x + CELL // 2 - pset.rec["Width"] // 2 - ctx.cx
            sy = CELL * y + CELL // 2 - int(ctx.relief[y, x]) - pset.rec["Height"] // 2 - ctx.cy
            if ctx.visible(sx, sy, wh[0], wh[1]):
                ctx.items.append(DrawItem("sprite", -1, ("projectile", pid, "main"), idx, sx, sy, wh[0], wh[1],
                                          blend="alpha" if pset.rec["A16"] else "opaque", light_row=None,
                                          depth=(PASS_CELL, y, -x, slot, 0)))


MISSILE_Z = 0               # CONFIRMED `FUN_0046707e` / `FUN_00466e18` / `FUN_0046025d`: a projectile's altitude `obj+0x10` starts at 0 and follows the target's (0), the
                            # screen position is the world position / 8 and the sprite is only lifted by the ground relief: the "height" is the ShootOffset point


class _Fx:
    """The `ent` of a client effect object's draw items."""
    id = -1


def _flashes(ctx):
    """P6: the one-shot cast sprites (Teleport 0x36: frame `age - 1`, 21 steps, both ends; Drain Life 0x3c: frame `age` = 1 for its single step on the
    target's footprint centre), the generic projectile path (`.16a` alpha, altitude 0, no shadow, no direction)."""
    w = ctx.world
    for f in w.flashes:
        age = ctx.tick - f.born                         # the exe age `obj+0x9c`: made in step `born`, ticked once in it, drawn after it (`world.tick` is already `born + 1`)
        if age < 1 or age > f.life:
            continue
        pos = f.pos
        if pos is None:
            t = w.find_unit(f.target)
            if t is None:
                continue
            size = tile_size(w, t)
            pos = (t.x * 256 + t.sub_x + ((size - 1) << 7), t.y * 256 + t.sub_y + ((size - 1) << 7))
        cx, cy = pos[0] >> 8, pos[1] >> 8
        if not in_window(ctx.win, cx, cy):
            ctx.items.culled += 1
            continue
        pset = ctx.assets.projectile_set(f.pid)
        if pset is None:
            ctx.items.missing += 1
            continue
        ref = pset.frame_at("effect", 0, age, age0=-1)          # Teleport: phase age - 1 (frame 0 at age 1); Drain Life: phase age
        a16 = bool(pset.rec["A16"])
        dep = (PASS_PROJECTILE, cy, -cx, 0, (1 << 24) + f.born, f.pid, int(pos[0]))
        _projectile_item(ctx, _Fx, None, pset, ref, pos, dep + (0, 0), "alpha" if a16 else "opaque", "main", z0=0)
        if not a16 and pset.rec["Palette"]:
            _projectile_item(ctx, _Fx, None, pset, ref, pos, dep + (1, 0), "half", "main_b", z0=0)


def _arrows(ctx):
    """P6: the shooter projectiles (ids 1-6; 7 is the screen lens, no sprite) at the position `arrow_system` steps them to: the generic projectile path
    of `FUN_0046cb7b`, frame `phase + Phases * ((facing - 8) & 15)` (16 facings, no mirroring in the data; `RotationPhases == 1` = the one picture of the
    sling stone), `.16a` alpha when `A16` else opaque (+ the `b.256` half overlay when the record has a palette).  CONFIRMED: no shadow, no trail,
    altitude 0 (the sprite sits at the ShootOffset point and flies in the ground plane at the target's footprint centre), nothing is drawn on the
    impact (the object is simply removed)."""
    w = ctx.world
    for a in w.arrows:
        if not a.live:
            continue
        cx, cy = a.x >> 8, a.y >> 8
        if not in_window(ctx.win, cx, cy):
            ctx.items.culled += 1
            continue
        if a.pid == 7:                                  # the screen lens (animation.md 4.5): no sprite, a bulge of the pixels drawn so far, at (x, y - relief)
            px, py = (a.x * CELL) >> 8, (a.y * CELL) >> 8
            sx, sy = px - ctx.cx, py - fobj.ground_height(w.heights, a.x, a.y, 1, 1) - ctx.cy
            if ctx.visible(sx - LENS_SIZE, sy - LENS_SIZE, 2 * LENS_SIZE + 1, 2 * LENS_SIZE + 1):
                ctx.items.append(DrawItem("lens", -1, None, 0, sx, sy, 0, 0, depth=(PASS_PROJECTILE, cy, -cx, 0, (1 << 23) + a.born, a.shooter, 0, 0)))
            continue
        pset = ctx.assets.projectile_set(a.pid)
        if pset is None:
            ctx.items.missing += 1
            continue
        ref = pset.frame_at("flight", a.facing, a.age - 1, age0=0)
        a16 = bool(pset.rec["A16"])
        dep = (PASS_PROJECTILE, cy, -cx, 0, (1 << 23) + a.born, a.shooter)
        pos = (a.x, a.y)
        _projectile_item(ctx, _Fx, None, pset, ref, pos, dep + (0, 0), "alpha" if a16 else "opaque", "main", z0=0)
        if not a16 and pset.rec["Palette"]:
            _projectile_item(ctx, _Fx, None, pset, ref, pos, dep + (1, 0), "half", "main_b", z0=0)
        if pset.has_trail and a.trail:                  # ids 10 / 12: the 6 previous positions, oldest first, after the body (`FUN_0046cb7b`)
            points = [((y << 16) | x) & 0xFFFFFFFF for x, y in a.trail]
            for k, (tref, _) in enumerate(pset.trail(points)):
                _projectile_item(ctx, _Fx, None, pset, tref, a.trail[k], dep + (2 + k, 0), "alpha", "trail", z0=0)


def _explosions(ctx):
    """P6: the fire explosions (projectile 13) at their cell centre, drawn by the generic projectile path of `FUN_0046cb7b`: frame `(age / 2) mod Phases`
    (`RotationPhases == 1`, no direction), `.16a` alpha when `A16`, else opaque plus the `b.256` half overlay; `obj+0x10` (z) is 0 for message objects."""
    from .lights import explosion_phases
    w = ctx.world
    for e, age, _ in explosion_phases(w, ctx.assets, ctx.tick):
        if not in_window(ctx.win, e.x, e.y):
            ctx.items.culled += 1
            continue
        pset = ctx.assets.projectile_set(13)
        if pset is None:
            ctx.items.missing += 1
            continue
        pos = (e.x * 256 + 128, e.y * 256 + 128)
        ref = pset.frame_at("flight", 0, age, age0=-1)
        a16 = bool(pset.rec["A16"])
        dep = (PASS_PROJECTILE, e.y, -e.x, 0, (1 << 21) + e.born)
        _projectile_item(ctx, _Fx, None, pset, ref, pos, dep + (0, 0), "alpha" if a16 else "opaque", "main", z0=0)
        if not a16 and pset.rec["Palette"]:
            _projectile_item(ctx, _Fx, None, pset, ref, pos, dep + (1, 0), "half", "main_b", z0=0)


def _bolts(ctx):
    """P6: the Lightning / Prismatic Spray bolts (projectile 28 / 30, `FUN_0046cb7b` cases 0x1c / 0x1e): one sprite on every point of every segment,
    frame `phase` (Lightning) or `phase + 5 * variant` (Spray, variant = list index % 7), phase from the ping-pong table by age, `.16a` alpha."""
    from .lights import bolt_age, bolt_segments
    w = ctx.world
    for b in w.bolts:
        if bolt_age(b, ctx.tick) is None:
            continue
        pset = ctx.assets.projectile_set(b.pid)
        if pset is None:
            ctx.items.missing += 1
            continue
        a16 = bool(pset.rec["A16"])
        n = 0
        for var, pts in bolt_segments(w, b, ctx.tick):
            ref = pset.frame_at("effect", 0, ctx.tick - b.born, age0=b.age0, colour=var)
            for x, y in pts:
                pos = (int(x) << 3, int(y) << 3)
                dep = (PASS_PROJECTILE, int(y) >> 5, -(int(x) >> 5), 0, (1 << 22) + b.born, n)
                _projectile_item(ctx, _Fx, None, pset, ref, pos, dep, "alpha" if a16 else "opaque", "main", z0=-fobj.ground_height(
                    w.heights, pos[0], pos[1], 1, 1))
                n += 1


def _projectile_item(ctx, ent, c, pset, ref, pos, depth, blend, source, z0=None):
    wh = pset.size(source if source != "main_b" else "main_b", ref.index)
    if wh is None:
        ctx.items.missing += 1
        return
    z = fobj.ground_height(ctx.world.heights, pos[0], pos[1], 1, 1) + (MISSILE_Z if z0 is None else z0)
    px, py = (pos[0] * CELL) >> 8, (pos[1] * CELL) >> 8
    sx, sy = px - ref.hotspot[0] - ctx.cx, py - ref.hotspot[1] - z - ctx.cy
    if ctx.visible(sx, sy, wh[0], wh[1]):
        ctx.items.append(DrawItem("sprite", ent.id, ("projectile", pset.pid, source), ref.index, sx, sy, wh[0], wh[1],
                                  mirrored=ref.mirrored, blend=blend, light_row=None, depth=depth))


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
    if not fog.item_visible(ctx.world, it):
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


def _unregistered_units(world, assets):
    """Ids of the units the exe never draws: `FUN_00460591` stores the object in ONE pointer per cell of a layer array (ground units and bodies of
    death stage < 2, flyers, bones of stage >= 2 or flag `0x80`: `FUN_00463093`), the last one registered wins, and the registration walks the view's
    object map in hash order ([objmap](objmap.py)).  Only a cell holding two objects of one layer loses any (two bones on one cell).  The shadow
    passes are assumed to follow the same arrays (INFERRED)."""
    cells = {}
    for u in (*world.units.values(), *world.corpses.values()):
        aset = assets.unit_set(u.type_id)
        if aset is None:
            continue
        stage = death_stage(u.hp)
        layer = 4 if stage >= 2 else (3 if aset.t.Z else 2)
        _, _, cx, cy = unit_position(u, aset.t.TileSize)
        cells.setdefault((layer, cx, cy), []).append((u.oid, u))
    lost = set()
    for group in cells.values():
        if len(group) > 1:
            lost.update(id(u) for _, u in walk_order(group)[:-1])
    return lost


def build_draw_list(world, camera, tick, assets, options=None, debug=None, selection=(), hover=None, ai_info=None, hidden=None):
    """Sprites (and requested debug overlays) of map objects and structures for
    `camera`, in drawing order: sorted by `DrawItem.depth` =
    (pass, row, -col, slot, seq, part, sub) (the exe's scan order, docs/engine/rendering.md).
    Reads the world only.  `assets`: an `AssetCache`; `options`: `DrawOptions`;
    `debug`: any object with boolean `passability`, `markers`, `depth`; `selection`: unit ids that
    get a selection bar, `hover`: the unit id under the pointer (it gets bars too).  `DrawList.picks` holds the unit pick rects in draw order."""
    opts = options or DrawOptions()
    ctx = _Ctx(world, camera, tick, assets, opts, hover, hidden)
    if opts.objects:
        for ent in world.objects.values():
            if ent.kind == "object":
                _objects(ctx, ent)
            else:
                _structure(ctx, ent)
    if opts.units:
        for it in world.items.values():
            _item(ctx, it)
        lost = _unregistered_units(world, assets)
        for u in world.corpses.values():
            if id(u) not in lost:
                _unit(ctx, u)
        for u in world.units.values():
            if id(u) not in lost:
                _unit(ctx, u)
        _explosions(ctx)
        _bolts(ctx)
        _arrows(ctx)
        _flashes(ctx)
        _cell_effects(ctx)
        _burning_sprites(ctx)
    ctx.items.sort(key=lambda i: i.depth)
    ctx.items.picks = [r for _, r in sorted(ctx.picks, key=lambda p: p[0] + (0, 2))]
    ctx.items.hover_picks = [r for _, r in sorted([(d + (0, 2), r) for d, r in ctx.picks] + [(d + (0, 0), r) for d, r in ctx.struct_picks],
                                                  key=lambda p: p[0])]
    ctx.items.extend(_bars(ctx, selection, hover))
    if debug is not None:
        ctx.items.extend(sorted(_debug_items(ctx, debug, selection, ai_info), key=lambda i: i.depth))
    return ctx.items
