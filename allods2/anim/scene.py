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
from .base import CELL
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
SACK_COLOUR = (255, 220, 40)
CARRIED_COLOUR = (80, 200, 255)


def draw_scene(canvas, m, scene, *, top=0, relief=True, clock=0, objects=True, structures=True,
               units=False, items=False, facing=UNIT_FACING):
    """Draw onto `canvas` (Canvas whose pixel (0, top) is the map's cell (0, 0) top-left
    with zero relief).  `relief`: displace by the heights (terrain drawn with --relief)."""
    heights = m.heights_i8
    jobs = []                                   # (flat, y, -x, kind, payload)
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
                jobs.append((0 if flat else 1, y, -x, 0, (aset, ref, parts, s, g)))
    if objects:
        for o in m.placed_objects():
            jobs.append((1, o.y, -o.x, 2, o))
    if units:
        players = m.players
        for u in m.units:
            jobs.append((1, u.y >> 8, -(u.x >> 8), 1, u))
    for flat, y, nx, kind, payload in sorted(jobs, key=lambda j: j[:4]):
        if kind == 1:
            u = payload
            aset = scene.unit_set(u.type)
            ref = aset.frame_at(aset.idle_action, facing, clock)
            z = O.ground_height(heights, u.x, u.y, 1, 1) if relief else 0
            aset.draw(canvas, ref, (u.x * CELL) >> 8, ((u.y * CELL) >> 8) - z + top,
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

    if items:
        for g in m.ground_groups:
            _marker(canvas, (g.x * CELL) >> 8, ((g.y * CELL) >> 8) + top, SACK_COLOUR)


def _marker(canvas, x, y, colour, r=3):
    """A hollow square of half-size r (item sacks are runtime objects; the file has no sprite)."""
    h, w = canvas.pix.shape[:2]
    for yy in range(y - r, y + r + 1):
        for xx in range(x - r, x + r + 1):
            if (abs(xx - x) == r or abs(yy - y) == r) and 0 <= xx < w and 0 <= yy < h:
                canvas.pix[yy, xx] = colour
