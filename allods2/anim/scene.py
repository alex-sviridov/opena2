"""Draw a campaign map's objects and structures onto a terrain image, in the
order of the view draw FUN_00406f43.  Spec: docs/formats/map.md part 4.

Cells are visited rows top to bottom, columns right to left.  Flat structures
(bridges, graves, camp fires, ...) are drawn first, then per cell: that cell's
slice of a non-flat structure, then the cell's map object.  Units would sit
between the two (units: map.md part 5); shadows, fog and the structures' owner colours are
not drawn.
"""

import dataclasses
import numpy as np

from ..formats import entities as E
from ..formats import objects as O
from .base import CELL, blit
from .structures import BridgeSet


class Scene:
    """The object and structure sets a map needs, from an `AssetCache` (loaded once)."""

    def __init__(self, fs=None):
        """`fs`: an a2res FS, an install folder or an `AssetCache`."""
        from ..assets import AssetCache
        self.assets = fs if isinstance(fs, AssetCache) else AssetCache(fs)
        self.fs = self.assets.fs

    @property
    def object_records(self):
        return self.assets.objects_reg()

    @property
    def structure_records(self):
        return self.assets.structures_reg()

    def object_set(self, oid):
        return self.assets.object_set(oid)

    def structure_set(self, s):
        return self.assets.structure_set(s.type, s.size)

    def unit_set(self, type_id):
        """UnitSet of a units.reg ID (cached)."""
        cache = self.__dict__.setdefault("_unit_sets", {})
        if type_id not in cache:
            from .units import load_unit_set
            cache[type_id] = load_unit_set(type_id, self.fs)
        return cache[type_id]

    def unit_palette(self, unit, players):
        """RGB palette of a map unit: Palette = 0 types take the owner's human.pal colour row
        (Player.colour), others palette<variant>.pal with variant = data.bin `face` - 1
        (units.md; the variant mapping is INFERRED)."""
        aset = self.unit_set(unit.type)
        rec = E.template(self.assets.databin(), unit)
        db = self.assets.databin()
        face = 1
        if rec is not None and not unit.is_human:
            face = rec.params[db.columns("monsters").index("face")]
        owner = players[unit.owner - 1].colour if 0 < unit.owner <= len(players) else 0
        return aset.palette("main", owner, max(face - 1, 0))


def piece_cells(aset, destroyed=False, tick=0, animate=True):
    """({(c, r): [Part, ...]}, ref): the pieces of a structure drawn from each cell
    (c, r) of its picture footprint (W x TH cells; a bridge: w x h), relative to the
    structure's cell, in draw order (FUN_00461649: a cell draws its piece row
    bottom-up, and the top local row also the FH - TH rows above the footprint).
    `ref` = the frame (`destroyed`: the destroyed pieces); `tick`/`animate` as
    `StructureSet.frame_at` (start 0)."""
    bridge = isinstance(aset, BridgeSet)
    ref = aset.frame_at("destroyed" if destroyed else "bridge" if bridge else "intact", 0, tick, animate=animate)
    lift = 0 if bridge else aset.FH - aset.TH              # picture rows above the footprint
    cells = {}
    for p in ref.parts:
        c, prow = p.dx // CELL, (p.dy + CELL * lift) // CELL
        r = max(prow - lift, 0)
        cells.setdefault((c, r), []).append((prow, p))
    for k in cells:
        cells[k] = [p for _, p in sorted(cells[k], key=lambda t: -t[0])]       # bottom-up
    return cells, ref


def structure_cells(scene, s):
    """{(x, y): [Part, ...]} keyed by absolute cell (see `piece_cells`), and the frame."""
    aset = scene.structure_set(s)
    if aset is None:
        return {}, None
    rec = aset.rec
    destroyed = s.intact == 0 and not rec.get("Indestructible") and "destroyed" in aset.actions
    cells, ref = piece_cells(aset, destroyed)
    return {(s.x + c, s.y + r): parts for (c, r), parts in cells.items()}, ref


UNIT_FACING = 8        # D2 direction of a drawn unit: the file has none (map.md part 5), 8 = front view
BACKPACK = "graphics/backpack/sprites.256"
BACKPACK_B = "graphics/backpack/spritesb.256"      # ground piles (FUN_00461292), 6 frames
FLYER_ALTITUDE = 16    # U+0x10 of a flyer (units.reg Z != 0), set by its constructor 0x46bfc1
# draw passes of FUN_00406f43 (engine/view/drawlist.py): flat structures, piles, per cell, flyers
P_FLAT, P_PILE, P_CELL, P_FLYER = 1, 2, 3, 7


def unit_cell(u, size):
    """(X, Y, cell x, cell y): the exe's filing position `pos - 0x80 + size * 0x80` and its cell
    (FUN_0046025d; a 2 x 2 unit is filed under the cell of its footprint centre)."""
    X, Y = u.x - 0x80 + size * 0x80, u.y - 0x80 + size * 0x80
    return X, Y, X >> 8, Y >> 8


def pile_frame(gold):
    """Backpack frame `min(5, floor(log10(gold)))`, 0 for an empty pile (items' +0x1c not decoded)."""
    return min(5, len(str(gold)) - 1) if gold > 0 else 0


def draw_scene(canvas, m, scene, *, top=0, relief=True, clock=0, objects=True, structures=True,
               units=False, items=False, facing=UNIT_FACING):
    """Draw onto `canvas` (Canvas whose pixel (0, top) is the map's cell (0, 0) top-left
    with zero relief).  `relief`: displace by the heights (terrain drawn with --relief)."""
    heights = m.heights_i8
    jobs = []                                   # (pass, y, -x, kind, payload)
    if structures:
        for s in m.structures:
            aset = scene.structure_set(s)
            if aset is None:
                continue
            cells, ref = structure_cells(scene, s)
            sx, sy = (aset.w, aset.h) if isinstance(aset, BridgeSet) else (aset.W, aset.TH)
            g = O.ground_height(heights, (s.x << 8) + 0x80, (s.y << 8) + 0x80, sx, sy) if relief else 0
            flat = bool(aset.rec.get("Flat"))
            for (x, y), parts in cells.items():
                jobs.append((P_FLAT if flat else P_CELL, y, -x, 0, (aset, ref, parts, s, g)))
    if objects:
        for o in m.placed_objects():
            jobs.append((P_CELL, o.y, -o.x, 2, o))
    if units:
        for u in m.units:
            aset = scene.unit_set(u.type)
            size = aset.t.TileSize
            _, _, cx, cy = unit_cell(u, size)
            jobs.append((P_FLYER if aset.t.Z else P_CELL, cy, -cx, 1, u))
    if items:
        piles = {}                              # one pile per cell, gold added (FUN_0052ab07)
        for g in m.ground_groups:
            piles[(g.x >> 8, g.y >> 8)] = piles.get((g.x >> 8, g.y >> 8), 0) + g.extra
        for (cx, cy), gold in piles.items():
            jobs.append((P_PILE, cy, -cx, 1, (cx, cy, gold)))
    players = m.players if units else None
    for flat, y, nx, kind, payload in sorted(jobs, key=lambda j: j[:4]):
        if flat == P_PILE:
            cx, cy, gold = payload
            z = O.cell_relief(heights, cx, cy) if relief else 0
            sf = scene.assets.sprite(BACKPACK)
            k = pile_frame(gold)
            px, py = CELL * cx + CELL // 2 - sf[0].width // 2, CELL * cy + CELL // 2 - z - sf[0].height // 2 - 4 + top
            blit(canvas, sf, k, px, py, sf.palette, "opaque", False)
            sfb = scene.assets.sprite(BACKPACK_B)                    # smoothing overlay at 50 %
            if sfb is not None and k < len(sfb):
                blit(canvas, sfb, k, px, py, sf.palette, "half", False)
        elif kind == 1:
            u = payload
            aset = scene.unit_set(u.type)
            ref = aset.frame_at(aset.idle_action, facing, clock)
            size = aset.t.TileSize
            X, Y, _, _ = unit_cell(u, size)
            z = O.ground_height(heights, u.x, u.y, size, size) if relief else 0
            alt = FLYER_ALTITUDE if aset.t.Z else 0
            aset.draw(canvas, ref, (X * CELL) >> 8, ((Y * CELL) >> 8) - z - alt + top,
                      palette=scene.unit_palette(u, players))
        elif kind == 0:
            aset, ref, parts, s, g = payload
            part = dataclasses.replace(ref, parts=tuple(parts))
            aset.draw(canvas, part, CELL * s.x, CELL * s.y - g + top)
        else:
            aset = scene.object_set(payload.id)
            if aset is None:
                continue
            x, y = payload.x, payload.y
            z = O.cell_relief(heights, x, y) if relief else 0
            ref = aset.frame_at("anim" if aset.rec["seq"] else "still", 0, clock, x=x, y=y)
            aset.draw(canvas, ref, CELL * x + CELL // 2, CELL * y + CELL // 2 - z + top)
