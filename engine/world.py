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

from allods2.formats import entities as fent
from allods2.formats import objects as fobj
from allods2.formats import passability as pas
from allods2.formats.objects import MapObject as PlacedObject

STRUCTURE_ID_BASE = 0x6000      # spec decision 2: runtime object id = 0x6000 + uid (CONFIRMED map.md part 4)
OBJECT_ID_BASE = 0x10000        # spec decision 2: section 3 cells (ours, the file has no ids)
UNIT_ID_BASE = 0x6000           # unit id = 0x6000 + uid: the exe's client view +4, the id space of structures
                                # (CONFIRMED map.md part 5; uids never collide with structure uids in the 46 maps)
ITEM_ID_BASE = 0x30000          # ground piles: 0x30000 + index of the section 8 group (ours; the file has no id)
UNIT_ANGLE_MIN, UNIT_ANGLE_SPAN = 0x40, 128     # creature ctor: angle = 0x40 + rand(128) (CONFIRMED map.md part 5)
IDLE = "idle"                   # logical action of a unit that does nothing; the view picks idle or stand
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
class Player:
    """Section 5 record (map.md part 5).  `id` is the 1-based record number, the value
    `Unit.owner` and `MapObject.owner` hold.  `colour` = row of humans/human.pal."""
    id: int
    colour: int
    name: str = ""
    flags: int = 0
    money: int = 0
    relations: tuple = ()           # 16 words, toward player j + 1 (1 war, 2 alliance, 0x10 vision)
    human: bool = False             # single player: record 1 only (map.md part 5)
    selection: tuple = ()           # selected unit ids, command order (sim/selection.py)


@dataclass
class Unit:
    """A unit or monster (section 6 record).  Field names and meanings follow the exe's
    Creature, docs/engine/unit-struct.md section 2; only what is needed now is here, the rest
    (mover, brain, order +0x50, state +0x54, stats, effects, equipment) belongs to the
    simulation phases and will be added with the systems that use it.

    Position is the cell plus a sub-cell offset in 1/256 cell (Position: cell +0/+1, sub-cell
    +4/+5, 0x80 = centre); `facing` is the mover angle byte (0 up, clockwise, 256 = full circle,
    mover[1]); the draw direction is `facing >> 4` (D2, 0..15).  `action` is the logical action
    name (`IDLE`...), `action_start_tick` the world tick it began (animation time =
    `world.tick - action_start_tick`)."""
    id: int
    type_id: int                    # units.reg ID (creature word +0x0e; the map's editor copy)
    owner: int                      # Player.id (creature +0x14)
    x: int                          # cell
    y: int
    sub_x: int = 128
    sub_y: int = 128
    facing: int = 0x80
    action: str = IDLE
    action_start_tick: int = 0
    hp: int = 0                     # +0x94
    hp_max: int = 0                 # +0x96
    uid: int = 0                    # scenario unit number (+8)
    server_id: int = 0              # data.bin serverID (template key)
    human: bool = False             # data.bin humans (0x254 object) rather than monsters (0x208)
    behaviour: int = 0              # map unit +0x50: bit 8 = summoned (no loot, no XP)
    move_type: int = 1              # +0x4a data.bin movementType: 1 walker, 2 ghost/bee, 3 flyer (mover mask)
    face: int = 1                   # +0x4b palette variant (data.bin monster `face`, 1..7; humans: skin)
    squad: int = 0                  # per-owner group number (file +44)
    group: int = 0                  # section 8 group index (1-based, 0 none): the carried items
    known: bool = True              # units.reg set and data.bin template both exist
    seq: int = 0                    # insertion order, the depth tie-break
    stats: object = None            # allods2.formats.unitstats.UnitType template (None if unknown)


@dataclass
class Item:
    """A pile on the ground (a section 8 group no unit carries; the exe's backpack,
    `FUN_005299b3` pack + `FUN_0052ab07` placement).  `gold` is the pile's gold (file `extra`);
    `codes` the item codes of the members (`entities.decode_item`); one pile per cell."""
    id: int
    x: int
    y: int
    sub_x: int = 128
    sub_y: int = 128
    gold: int = 0
    codes: tuple = ()
    groups: tuple = ()              # section 8 group indices merged into this pile
    seq: int = 0


@dataclass
class BuildReport:
    """What `World.from_map` found (spec "world.report")."""
    unknown: list = field(default_factory=list)     # (kind, type_id, x, y)
    ignored_outside_window: int = 0
    counts: dict = field(default_factory=dict)      # (kind, type_id) -> n
    unknown_units: list = field(default_factory=list)   # (uid, type_id, server_id, x, y): kept, known=False
    units_on_blocked: int = 0       # units whose cell is blocked for their mover: the exe server never creates them (FUN_00510089, r = 0); kept here
    units_sharing_cell: int = 0     # cells with more than one unit


def unit_angle(uid, facing=None):
    """The creature constructor's start angle `0x40 + rand(128)` (map.md part 5, CONFIRMED
    0x50e2ac); the file has no facing.  DECISION: the random draw is replaced by a hash of the
    uid so loading is deterministic.  An int `facing` overrides it."""
    if facing is not None:
        return facing & 255
    return UNIT_ANGLE_MIN + ((uid * 2654435761) >> 11) % UNIT_ANGLE_SPAN


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
        self.units = {}             # id -> Unit, in map record order
        self.items = {}             # id -> Item (ground piles), in section 8 order
        self.players = {}           # id (1-based record) -> Player
        self.report = BuildReport()
        self._cells = {}            # (x, y) -> set of ids over present footprint cells
        self._claim = {}            # (x, y) -> id of the structure registered there (first wins)
        self._ucells = {}           # (x, y) -> set of unit ids   (never part of the block layer)
        self._icells = {}           # (x, y) -> set of item ids
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

    # --- units, items, players ------------------------------------------------------
    # Units and items are indexed per cell but never enter the block layer: the static block
    # layer is what the exe's path finder derives from terrain and objects (FUN_00554626,
    # FUN_00550a96).  The exe stamps occupancy of units in the same grid at run time
    # (FUN_0055be86, unit-struct.md 7.4); that dynamic blocking is simulation (phase H).

    def units_at(self, x, y):
        """Ids of the units whose cell is (x, y)."""
        return frozenset(self._ucells.get((x, y), ()))

    def items_at(self, x, y):
        """Ids of the ground piles on cell (x, y)."""
        return frozenset(self._icells.get((x, y), ()))

    def entities_at(self, x, y):
        """Ids of everything on a cell: footprint entities, units, ground piles."""
        return self.objects_at(x, y) | self.units_at(x, y) | self.items_at(x, y)

    def _index_add(self, index, ent):
        index.setdefault((ent.x, ent.y), set()).add(ent.id)

    def _index_del(self, index, ent):
        s = index[(ent.x, ent.y)]
        s.discard(ent.id)
        if not s:
            del index[(ent.x, ent.y)]

    def _check_cell(self, ent):
        if not (0 <= ent.x < self.width and 0 <= ent.y < self.height):
            raise ValueError("entity %#x at (%d, %d) is outside the map" % (ent.id, ent.x, ent.y))

    def add_unit(self, u):
        """Add a unit; ValueError (world unchanged) on a duplicate id or a cell outside the map."""
        if u.id in self.units or u.id in self.objects:
            raise ValueError("duplicate entity id %#x" % u.id)
        self._check_cell(u)
        u.seq, self._next_seq = self._next_seq, self._next_seq + 1
        self.units[u.id] = u
        self._index_add(self._ucells, u)
        return u.id

    def remove_unit(self, uid):
        self._index_del(self._ucells, self.units.pop(uid))
        for p in self.players.values():
            if uid in p.selection:
                p.selection = tuple(i for i in p.selection if i != uid)

    def selection_is_foreign(self, player_id):
        """True when the player's selection is a unit of another owner (info only)."""
        sel = self.players[player_id].selection
        return bool(sel) and self.units[sel[0]].owner != player_id

    def move_unit(self, uid, x, y, sub_x=128, sub_y=128):
        """Put a unit on cell (x, y); the block layer is untouched."""
        u = self.units[uid]
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("target (%d, %d) is outside the map" % (x, y))
        self._index_del(self._ucells, u)
        u.x, u.y, u.sub_x, u.sub_y = x, y, sub_x, sub_y
        self._index_add(self._ucells, u)

    def add_item(self, it):
        if it.id in self.items:
            raise ValueError("duplicate item id %#x" % it.id)
        self._check_cell(it)
        it.seq, self._next_seq = self._next_seq, self._next_seq + 1
        self.items[it.id] = it
        self._index_add(self._icells, it)
        return it.id

    def remove_item(self, iid):
        self._index_del(self._icells, self.items.pop(iid))

    # --- loading -------------------------------------------------------------------

    @classmethod
    def from_map(cls, m, assets, facing=None):
        """From an `allods2.formats.Map` and an `AssetCache` (spec "World").
        Structures first in record order, then section 3 cells row-major;
        bulk-added, then one full block build; then players, units and ground piles in
        record order.  `facing`: None gives each unit the exe's start angle 0x40 + [0, 128)
        (the exe's rand, here a fixed hash of the uid so a map always loads the same);
        an int puts every unit at that angle byte (0x80 = front view, as `map render`)."""
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
        w._load_players(m)
        w._load_units(m, assets, facing)
        w._load_items(m)
        return w

    def _load_players(self, m):
        for p in m.players:
            self.players[p.index] = Player(p.index, p.colour, p.name, p.flags, p.money,
                                           tuple(p.relations), human=p.index == 1)

    def _load_units(self, m, assets, facing):
        """Section 6 in record order.  Unknown types (no units.reg set or no data.bin record)
        are kept with `known=False` and listed in `report.unknown_units`; an owner that is not
        a section 5 record is an error (the exe logs "Can't resolve player" and skips the unit,
        never the case in the 46 maps)."""
        types = assets.unit_stats()
        rep = self.report
        for rec in m.units:
            if rec.owner not in self.players:
                raise ValueError("unit uid %d: owner %d is not a player" % (rec.uid, rec.owner))
            tpl = types.lookup(rec.is_human, rec.server_id)
            hp, hp_max = rec.hp, rec.max_hp
            if rec.is_human and hp_max != fent.NO_HP and hp_max == hp:
                hp = hp_max = fent.NO_HP                    # FUN_00561bf9 0x562013: a hero at full HP = default
            base = tpl.hp_max if tpl is not None else 0     # map overrides replace the template value
            face = tpl.face if tpl is not None else 1
            move = tpl.movement_type if tpl is not None else 1
            hp_max = base if hp_max == fent.NO_HP else hp_max
            hp = hp_max if hp == fent.NO_HP else hp
            known = tpl is not None and assets.unit_set(rec.type) is not None
            u = Unit(UNIT_ID_BASE + rec.uid, rec.type, rec.owner, rec.x >> 8, rec.y >> 8,
                     rec.x & 255, rec.y & 255, unit_angle(rec.uid, facing), IDLE, 0, hp, hp_max,
                     rec.uid, rec.server_id, rec.is_human, rec.behaviour, move, face, rec.squad, rec.group, known,
                     stats=tpl)
            self.add_unit(u)
            if not known:
                rep.unknown_units.append((rec.uid, rec.type, rec.server_id, u.x, u.y))
        rep.units_sharing_cell = sum(1 for s in self._ucells.values() if len(s) > 1)
        rep.units_on_blocked = sum(1 for u in self.units.values()
                                   if self.blocked(u.x, u.y, u.move_type if u.move_type in pas.MOVE_MASK else 1))

    def _load_items(self, m):
        """Ground piles: the section 8 groups no unit's `group` points at (`Map.ground_groups`).
        Groups on one cell merge into one pile, gold added and items stacked (`FUN_0052ab07`,
        CONFIRMED map.md part 5); the pile takes the id of its first group,
        `ITEM_ID_BASE + group index` (0-based, file order)."""
        used = {u.group for u in m.units if u.group}
        at = {}
        for n, g in enumerate(m.item_groups):
            if n + 1 in used:
                continue
            cell = (g.x >> 8, g.y >> 8)
            codes = tuple(mem.code & 0xFFFF for mem in g.members)
            if cell in at:
                it = at[cell]
                it.gold += g.extra
                it.codes += codes
                it.groups += (n,)
                continue
            at[cell] = Item(ITEM_ID_BASE + n, cell[0], cell[1], g.x & 255, g.y & 255, g.extra, codes,
                            groups=(n,))
            self.add_item(at[cell])

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
                           "unknown_units": [list(u) for u in r.unknown_units],
                           "units_on_blocked": r.units_on_blocked,
                           "units_sharing_cell": r.units_sharing_cell,
                           "ignored_outside_window": r.ignored_outside_window,
                           "counts": {"%s:%d" % k: v for k, v in sorted(r.counts.items())}},
                "objects": objs,
                "players": [[p.id, p.colour, p.name, p.flags, p.money, list(p.relations), int(p.human)]
                            + ([{"selection": list(p.selection)}] if p.selection else [])
                            for _, p in sorted(self.players.items())],
                "units": [[u.id, u.type_id, u.owner, u.x, u.y, u.sub_x, u.sub_y, u.facing, u.action,
                           u.action_start_tick, u.hp, u.hp_max, u.uid, u.server_id, int(u.human),
                           u.behaviour, u.move_type, u.face, u.squad, u.group, int(u.known)]
                          for _, u in sorted(self.units.items())],
                "items": [[i.id, i.x, i.y, i.sub_x, i.sub_y, i.gold, list(i.codes), list(i.groups)]
                          for _, i in sorted(self.items.items())],
                "block": [bytes(row).hex() for row in self._block]}

    def dump_json(self):
        return json.dumps(self.dump(), sort_keys=True, separators=(",", ":"))

    def dump_hash(self):
        return hashlib.sha256(self.dump_json().encode("ascii")).hexdigest()
