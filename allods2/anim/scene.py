"""Draw a campaign map's objects and structures onto a terrain image, in the
order of the view draw FUN_00406f43.  Spec: docs/formats/map.md part 4.

Cells are visited rows top to bottom, columns right to left.  Flat structures
(bridges, graves, camp fires, ...) are drawn first, then per cell: that cell's
slice of a non-flat structure, then the cell's map object.  Units would sit
between the two; shadows, fog and the structures' owner colours are not drawn.
"""

import dataclasses

from ..common import as_fs
from ..formats import objects as O
from .base import CELL
from .objects import load_object_records, load_object_set
from .structures import BridgeSet, load_structure_records, structure_paths, StructureSet


class Scene:
    """Loads the object and structure sets a map needs, once."""

    def __init__(self, fs=None):
        self.fs = as_fs(fs)
        self.object_records = load_object_records(self.fs)
        self.structure_records = load_structure_records(self.fs)
        self._objects, self._structures = {}, {}

    def object_set(self, oid):
        if oid not in self._objects:
            self._objects[oid] = load_object_set(oid, self.fs, self.object_records) \
                if oid in self.object_records else None
        return self._objects[oid]

    def structure_set(self, s):
        key = (s.type, s.size)
        if key not in self._structures:
            rec = self.structure_records.get(s.type)
            if rec is None:
                self._structures[key] = None
            elif rec.get("VariableSize"):
                w, h = s.size or (0, 0)
                self._structures[key] = BridgeSet(rec, w, h, paths=structure_paths(rec, self.fs), fs=self.fs)
            else:
                self._structures[key] = StructureSet(rec, paths=structure_paths(rec, self.fs), fs=self.fs)
        return self._structures[key]


def structure_cells(scene, s):
    """{(x, y): [Part, ...]}: the pieces of structure `s` drawn from each cell of
    its picture footprint (W x TH cells; a bridge: w x h), keyed by absolute cell,
    in draw order (FUN_00461649: a cell draws its piece row bottom-up, and the
    top local row also the FH - TH rows above the footprint)."""
    aset = scene.structure_set(s)
    if aset is None:
        return {}, None
    rec = aset.rec
    destroyed = s.intact == 0 and not rec.get("Indestructible") and "destroyed" in aset.actions
    bridge = isinstance(aset, BridgeSet)
    ref = aset.frame_at("destroyed" if destroyed else "bridge" if bridge else "intact", 0, 0)
    lift = 0 if bridge else aset.FH - aset.TH              # picture rows above the footprint
    cells = {}
    for p in ref.parts:
        c, prow = p.dx // CELL, (p.dy + CELL * lift) // CELL
        r = max(prow - lift, 0)
        cells.setdefault((s.x + c, s.y + r), []).append((prow, p))
    for k in cells:
        cells[k] = [p for _, p in sorted(cells[k], key=lambda t: -t[0])]       # bottom-up
    return cells, ref


def draw_scene(canvas, m, scene, *, top=0, relief=True, clock=0, objects=True, structures=True):
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
            jobs.append((1, o.y, -o.x, 1, o))
    for flat, y, nx, kind, payload in sorted(jobs, key=lambda j: j[:4]):
        if kind == 0:
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
