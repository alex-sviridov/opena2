"""World state: map cells and heights, entities, spatial index, block layer.

Spec: docs/superpowers/specs/2026-10-16-world-state-design.md (cited as "spec");
rules from docs/formats/map.md parts 3 and 4.  Layer 3: knows nothing of view,
ui or pygame.

`MapObject` here is the engine entity; `allods2.formats.objects.MapObject` (the
parsed section 3 record) is imported under the alias `PlacedObject`.
"""

import hashlib
import json
from dataclasses import dataclass, field

import numpy as np

from allods2.formats import objects as fobj
from allods2.formats import passability as pas
from allods2.formats.objects import MapObject as PlacedObject

STRUCTURE_ID_BASE = 0x6000      # spec decision 2: runtime object id = 0x6000 + uid (CONFIRMED map.md part 4)
OBJECT_ID_BASE = 0x10000        # spec decision 2: section 3 cells (ours, the file has no ids)
UNIT_ID_BASE = 0x20000          # reserved for units/items/players (not used yet)
DEFAULT_HP = 1000               # healthMax 0 -> 1000 (map.md part 4)
FLAG_DESTROYED = 1

KINDS = ("object", "structure", "bridge")
_SOLID, _CLEAR = fobj.SOLID, fobj.CLEAR


@dataclass
class MapObject:
    """A world entity from a map (spec "MapObject").  `footprint` lists the
    BuildingPresent cells row-major as (dx, dy, solid); `seq` is the stamp
    order (assigned on add, later wins), not serialised."""
    id: int
    kind: str                   # "object" | "structure" | "bridge"
    type_id: int                # objects.reg / structures.reg ID (bridge 0x21)
    x: int
    y: int
    sub_x: int = 128            # 1/256 cell, 128 = centre
    sub_y: int = 128
    variant: int = 0
    owner: int = 0
    hp: int = 0
    hp_max: int = 0
    flags: int = 0
    uid: int = 0
    footprint: tuple = ((0, 0, True),)
    known: bool = True
    seq: int = 0
    size: tuple = None          # (w, h) cells of a sized bridge (section 4), else None


@dataclass
class BuildReport:
    """What `World.from_map` found (spec "world.report")."""
    unknown: list = field(default_factory=list)     # (kind, type_id, x, y)
    ignored_outside_window: int = 0
    counts: dict = field(default_factory=dict)      # (kind, type_id) -> n


def structure_footprint(s, stats):
    """(footprint, known, hp_max) of a section 4 record (spec decision 4).
    Present cells only, solid = Passability bit (map.md part 4, FUN_00550a96).
    A type missing in data.bin gets the single cell, solid, hp_max 1000."""
    if s.size is None and not 1 <= s.type <= len(stats):
        return ((0, 0, True),), False, DEFAULT_HP
    w, h, solid, present = fobj.footprint(s, stats)
    sol, pre = fobj.mask_cells(w, h, solid), fobj.mask_cells(w, h, present)
    fp = tuple((c, r, bool(sol[r, c])) for r in range(h) for c in range(w) if pre[r, c])
    hp_max = stats[s.type - 1].params[3] if 1 <= s.type <= len(stats) else 0
    return fp, True, hp_max or DEFAULT_HP


class World:
    """`cells` (h, w) uint16 runtime tile values, `heights` (h, w) int8 (one
    signed byte per vertex, 1 px each), `terrain` the raw Tiles (dirt bit kept)
    the block layer reads (default `cells`).  Campaign maps are square (spec
    decision 8); other shapes are accepted here for the view tests (the exe's
    grid of a non-square map is 256 wide, FUN_00553b30, not modelled)."""

    def __init__(self, cells, heights, name="", terrain=None):
        self.cells = np.asarray(cells, np.uint16)
        self.heights = np.asarray(heights).astype(np.int8)
        if self.cells.shape != self.heights.shape:
            raise ValueError("cells and heights differ in shape")
        self.height, self.width = self.cells.shape
        self.terrain = self.cells if terrain is None else np.asarray(terrain, np.uint16)
        if self.terrain.shape != self.cells.shape:
            raise ValueError("terrain and cells differ in shape")
        self.name = name
        self.tick = 0
        self.objects = {}           # id -> MapObject
        self.units = {}             # placeholders (spec "World")
        self.items = {}
        self.players = {}
        self.report = BuildReport()
        self._cells = {}            # (x, y) -> set of ids over present footprint cells
        self._claim = {}            # (x, y) -> id of the structure registered there (first wins)
        self._next_seq = 1
        self._base = pas.terrain_base(self.terrain)         # computed once
        self._block = self._base.copy()
        self._border()
        self._view = self._block.view()
        self._view.flags.writeable = False

    # --- views ---------------------------------------------------------------

    @property
    def block(self):
        """(h, w) uint8 block layer, read-only view."""
        return self._view

    def walkable(self, mover=1):
        """(h, w) bool: cells a mover of that movementType may enter."""
        return pas.walkable(self._block, mover)

    def blocked(self, x, y, mover=1):
        """True if the cell is blocked for `mover`; cells outside the map are."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return True
        return bool(self._block[y, x] & pas.MOVE_MASK[mover])

    def objects_at(self, x, y):
        """Ids of the entities with a present footprint cell at (x, y)."""
        return frozenset(self._cells.get((x, y), ()))

    # --- block layer -----------------------------------------------------------

    def _border(self):
        b, n = pas.BORDER, self._block
        n[:b, :] = n[-b:, :] = n[:, :b] = n[:, -b:] = pas.B_BORDER

    def _cell_value(self, x, y):
        """Block value of one cell from base + index (spec "Block layer" 1-4)."""
        ids = self._cells.get((x, y), ())
        o = self.objects
        v = int(self._base[y, x])
        if any(o[i].kind == "object" for i in ids):
            v = pas.B_GROUND | pas.B_OBJECT
        b = pas.BORDER
        if x < b or y < b or x >= self.width - b or y >= self.height - b:
            v = pas.B_BORDER
        i = self._claim.get((x, y))
        if i is not None:
            ob = o[i]
            solid = next(s for dx, dy, s in ob.footprint if (ob.x + dx, ob.y + dy) == (x, y))
            v = v | _SOLID if solid else v & _CLEAR
        return v

    def _refresh(self, cells):
        """Recompute exactly `cells` (local recompute, spec)."""
        for x, y in cells:
            if 0 <= x < self.width and 0 <= y < self.height:
                self._block[y, x] = self._cell_value(x, y)

    def rebuild_block(self):
        """From-scratch block layer from base + entities, vectorised for objects
        (equals repeated `_refresh`, tested).  Returns a new array."""
        blk = self._base.copy()
        ys, xs = [], []
        for ob in self.objects.values():
            if ob.kind == "object":
                ys.append(ob.y)
                xs.append(ob.x)
        if xs:
            blk[ys, xs] = pas.B_GROUND | pas.B_OBJECT
        b = pas.BORDER
        blk[:b, :] = blk[-b:, :] = blk[:, :b] = blk[:, -b:] = pas.B_BORDER
        claim = {}
        for ob in sorted(self.objects.values(), key=lambda o: o.seq):
            if ob.kind != "object":
                self._register(ob, claim)
        for (x, y), i in claim.items():
            ob = self.objects[i]
            solid = next(s for dx, dy, s in ob.footprint if (ob.x + dx, ob.y + dy) == (x, y))
            blk[y, x] = blk[y, x] | _SOLID if solid else blk[y, x] & _CLEAR
        return blk

    def _register(self, ob, claim):
        """FUN_005599df: claim the present cells in row-major order; the first
        cell already held by another structure ends the registration, the rest
        of this structure's cells stay unregistered (FUN_00559890 fails, the
        caller returns 0).  Cells outside the map are skipped."""
        for c in self._present(ob):
            if c in claim:
                break
            claim[c] = ob.id

    def _resolve(self, seed):
        """Re-run the registration for the connected group of structures that
        touch the cells `seed` (local: groups are independent), then refresh
        the cells concerned."""
        group, stack, cells = set(), list(seed), set(seed)
        while stack:
            for i in self._cells.get(stack.pop(), ()):
                if i not in group and self.objects[i].kind != "object":
                    group.add(i)
                    for c in self._present(self.objects[i]):
                        if c not in cells:
                            cells.add(c)
                            stack.append(c)
        for c in cells:
            self._claim.pop(c, None)
        for i in sorted(group, key=lambda i: self.objects[i].seq):
            self._register(self.objects[i], self._claim)
        self._refresh(cells)

    # --- entities ----------------------------------------------------------------

    def _present(self, ob):
        """Map cells of the object's footprint (outside cells dropped)."""
        out = []
        for dx, dy, _ in ob.footprint:
            x, y = ob.x + dx, ob.y + dy
            if 0 <= x < self.width and 0 <= y < self.height:
                out.append((x, y))
        return out

    def _check(self, ob):
        if ob.kind not in KINDS:
            raise ValueError("unknown kind %r" % (ob.kind,))
        if not (0 <= ob.x < self.width and 0 <= ob.y < self.height):
            raise ValueError("entity %#x at (%d, %d) is outside the map" % (ob.id, ob.x, ob.y))

    def _insert(self, ob, seq=None):
        if seq is None:
            seq, self._next_seq = self._next_seq, self._next_seq + 1
        ob.seq = seq
        self.objects[ob.id] = ob
        cells = self._present(ob)
        for c in cells:
            self._cells.setdefault(c, set()).add(ob.id)
        return cells

    def _detach(self, oid):
        ob = self.objects.pop(oid)
        cells = self._present(ob)
        for c in cells:
            s = self._cells[c]
            s.discard(oid)
            if not s:
                del self._cells[c]
        return ob, cells

    def add_object(self, ob):
        """Add an entity; returns its id.  ValueError (world unchanged) on a
        duplicate id or an anchor cell outside the map."""
        if ob.id in self.objects:
            raise ValueError("duplicate entity id %#x" % ob.id)
        self._check(ob)
        self._resolve(self._insert(ob))
        return ob.id

    def remove_object(self, oid):
        """Remove an entity (KeyError if absent) and recompute its cells."""
        if oid not in self.objects:
            raise KeyError(oid)
        _, cells = self._detach(oid)
        self._resolve(cells)

    def move_object(self, oid, x, y):
        """Remove + re-add at (x, y) with the same id and seq."""
        if oid not in self.objects:
            raise KeyError(oid)
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("target (%d, %d) is outside the map" % (x, y))
        ob, old = self._detach(oid)
        ob.x, ob.y = x, y
        self._resolve(old + self._insert(ob, ob.seq))

    # --- loading -------------------------------------------------------------------

    @classmethod
    def from_map(cls, m, assets):
        """From an `allods2.formats.Map` and an `AssetCache` (spec "World").
        Structures first in record order, then section 3 cells row-major;
        bulk-added, then one full block build."""
        w = cls(m.runtime_terrain(), m.heights_i8, m.name, terrain=m.terrain)
        stats = assets.databin().structures
        reg = assets.objects_reg()
        rep = w.report

        def count(kind, tid):
            rep.counts[(kind, tid)] = rep.counts.get((kind, tid), 0) + 1

        for s in m.structures:
            fp, known, hp_max = structure_footprint(s, stats)
            kind = "bridge" if s.is_bridge else "structure"
            ob = MapObject(STRUCTURE_ID_BASE + s.uid, kind, s.type, s.x, s.y, owner=s.owner,
                           hp=hp_max if s.intact else 0, hp_max=hp_max,
                           flags=0 if s.intact else FLAG_DESTROYED, uid=s.uid, footprint=fp,
                           known=known, size=s.size)
            if ob.id in w.objects:
                raise ValueError("duplicate structure id %#x (uid %d)" % (ob.id, s.uid))
            w._check(ob)
            w._insert(ob)
            count(kind, s.type)
            if not known:
                rep.unknown.append((kind, s.type, s.x, s.y))
        placed = m.placed_objects()
        for n, p in enumerate(placed):
            known = p.id in reg
            w._insert(MapObject(OBJECT_ID_BASE + n, "object", p.id, p.x, p.y, known=known))
            count("object", p.id)
            if not known:
                rep.unknown.append(("object", p.id, p.x, p.y))
        rep.ignored_outside_window = int(np.count_nonzero(m.objects)) - len(placed)
        w._resolve(list(w._cells))
        return w

    # --- dump ----------------------------------------------------------------------

    def dump(self):
        """Deterministic plain-int dict of the world (spec "CLI" world-dump)."""
        objs = []
        for i in sorted(self.objects):
            o = self.objects[i]
            objs.append({"id": o.id, "kind": o.kind, "type_id": o.type_id, "x": o.x, "y": o.y,
                         "sub_x": o.sub_x, "sub_y": o.sub_y, "variant": o.variant,
                         "owner": o.owner, "hp": o.hp, "hp_max": o.hp_max, "flags": o.flags,
                         "uid": o.uid, "known": int(o.known),
                         "footprint": [[dx, dy, int(s)] for dx, dy, s in o.footprint]})
        r = self.report
        return {"name": self.name, "width": self.width, "height": self.height,
                "report": {"unknown": [list(u) for u in r.unknown],
                           "ignored_outside_window": r.ignored_outside_window,
                           "counts": {"%s:%d" % k: v for k, v in sorted(r.counts.items())}},
                "objects": objs,
                "block": [bytes(row).hex() for row in self._block]}

    def dump_json(self):
        return json.dumps(self.dump(), sort_keys=True, separators=(",", ":"))

    def dump_hash(self):
        return hashlib.sha256(self.dump_json().encode("ascii")).hexdigest()
