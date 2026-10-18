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
from allods2.formats import progression as prog
from allods2.formats.objects import MapObject as PlacedObject

from .rng import DEFAULT_SEED, Rng

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
    formation: int = 1              # client option [GameOptions] Formation: 0 off, 1 auto (default), 2 on (R 4.1)


@dataclass
class OrderGroup:
    """The exe's command group (`FUN_0052b06f`, 0x50 bytes + record at +0x3c): every player command makes a
    new one.  `order` = record+0x20 (0 cancelled, 3 stand ground, 4 group move), `target` = record+0xa (x, y),
    unclamped, `speed` = record+0x44 (non-zero only when the formation was active), `members` in packet order."""
    id: int
    owner: int
    members: list = field(default_factory=list)
    order: int = 0
    target: tuple = (0, 0)
    speed: int = 0


@dataclass(frozen=True)
class Damage:
    """Fight log entry: one resolved blow (`World.fight_log`, never in the dump).  `amount` 0 for a miss or an absorbed hit; `hp` is the
    target's HP after it; `roll` the `rand(200) - 100` of the exe (0 when nothing was drawn)."""
    tick: int
    attacker: int
    target: int
    amount: int
    hp: int
    roll: int = 0
    hit: bool = False


@dataclass(frozen=True)
class Died:
    """Fight log entry: a unit's HP reached 0 (death itself is phase I2)."""
    tick: int
    unit: int
    by: int


@dataclass(frozen=True)
class NoWay:
    """Event: the static planner of one of `player_id`'s units ended far from its target (message `0x92`,
    text "No way").  Lives in `World.events`, never in the dump or the hash."""
    player_id: int
    tick: int


@dataclass
class Mover:
    """Movement state of a unit: the exe's Mover object (creature +0x1c0, 0xb4 bytes),
    docs/engine/unit-struct.md section 7.  Facing and the sub-cell offset live on the Unit
    (mover[0] and the Position object); everything else of a step is here.  Steps are in 1/256
    cell."""
    turn_rate: int = 16             # +0x0a facing units per tick (data.bin turn rate; ctor default 0x10)
    target_facing: int = -1         # +0x01 (-1: equal to the unit's facing, as the ctor sets both)
    step_target: tuple = None       # +0x06 cell being entered (x, y) while a step is in progress
    step_from: tuple = None         # +0x70 cell where the step began
    steps: int = 0                  # +0xac ticks done in the step
    step_ticks: int = 0             # +0xaa ticks the step takes (ceil(256 / larger component))
    step_len: int = 0               # +0xa8 length per tick, 1..63
    step_dir: int = 0               # +0xae dir8 of the step (0 N, 1 NE, 2 E ... 7 NW)
    dx: int = 0                     # +0xb0 signed per-tick offset, x
    dy: int = 0                     # +0xb1 y
    turning: bool = False           # +0xa0 a multi-tick turn is in progress
    turn_ticks: int = 0             # +0xa4 ticks the current turn takes
    turn_done: int = 0              # +0x9d turn ticks done
    # path-finding state (docs/engine/simulation.md section 7); the exe's offsets in brackets
    goal: tuple = None              # target cell of the move order (the brain's argument of FUN_00555411)
    dest: tuple = None              # +0x74 target cell the static plan was made for
    tail: tuple = None              # +0x76 last cell of the static plan (own cell when it failed)
    consumed: int = 0               # +0x09 hop plans since the static plan (0xFF = force a re-plan)
    since_hop: int = 0              # +0x78 ticks since the last hop plan
    arrived: bool = False           # +0x90 the unit stands on `tail`
    failed: bool = False            # +0x98 a plan came out empty
    static_path: list = field(default_factory=list)     # the static list (+0x1c8); Unit.path is the dynamic one
    follow: int = None              # +0x7c the unit id the follow driver last planned for (0 after a cancel / arrival at the hop goal)
    follow_cell: tuple = None       # +0x8c the target cell the follow plan was made for
    static_len: int = 0             # +0x8a length of the static list after the last follow re-plan (0xFF = forced)
    waiting: bool = False           # brain mode 10 (`FUN_00556b2c`/`00555411`): turning to face the blocker
    parked: bool = False            # brain mode 0 under a move order after a wait: no driver restarts it
    last_plan: object = None        # debug: PathResult of the last static plan (not dumped)
    last_hop: object = None         # debug: PathResult of the last hop plan (not dumped)
    last_hop_goal: tuple = None     # debug: the cell that hop plan aimed at (not dumped)


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
    cell_seq: int = 0               # order in which the unit last entered its cell (first come, first served: the
                                    # exe's cell-record occupant slot, simulation.md 7.4); not dumped
    stats: object = None            # allods2.formats.unitstats.UnitType template (None if unknown)
    skills: tuple = ()              # humans: +0xa8..+0xb2 (general, blade, axe, bludgeon, pike, shooting); () for monsters
    xp: tuple = ()                  # humans: XP pools of skills 1..5 (+0x23c+4k), pool = thr[skill] at start
    xp_total: int = 0               # humans: +0x130, the sum of the pools
    best_school: int = 0            # +0x23c for Hero_/Start_ templates: first highest school 1..5, else 0
    mana: int = 0                   # humans: +0x9a (starts at the maximum)
    mana_max: int = 0               # humans: +0x9c, derived like the max HP (0 for fighters)
    speed_mod: int = 0              # Haste/Slow effect delta added to the speed stat (+0x8c)
    order: int = 0                  # +0x50 order id (0 none, 1 move to cell); sim/movement.py
    state: int = 0                  # +0x54 state (0 idle, 1 move step); sim/movement.py
    path: list = field(default_factory=list)    # cells still to enter, front first (the exe's list at +0x1c8)
    mover: Mover = field(default_factory=Mover)
    odometer: int = 0               # client walk counter obj+0x9c: map units moved, 16 per walk frame
    order_group: int = 0            # id of the OrderGroup the unit belongs to (unit+0x70), 0 none
    stopped: bool = False           # brain+0x50: set by the stop routine FUN_0056dbc6, cleared by every cancel
    mode_go: bool = False           # Brain mode 1 (go to brain+0xa, mover.goal): the move order and the group-pass restart
                                    # (FUN_0056c8af) set it, the stand orders (FUN_0056d52b) and a failure under another order clear it
    anchor: tuple = None            # brain anchor cell of the stand orders 0xb/0xc
    # fight state (docs/engine/combat.md; sim/combat.py): the exe's offsets in brackets
    combat: object = None           # sim.combatstats.CombatStats, built on first use from `stats` and the item table
    target: int = None              # brain+0xc id of the attack target (order 3, Brain mode 5)
    mode_attack: bool = False       # Brain mode 5 (attack with approach)
    range: int = 1                  # brain+0x14 attack / approach range in cells
    brain_order: int = 0            # brain+0x9: 1 = swing in progress (a step in progress is `mover.step_ticks`)
    swing_count: int = 0            # brain+0x15 ticks into the swing
    phase: int = 0                  # +0x58 swing phase: 0 start, 5 wind-up, 7 recovery
    timer: int = 0                  # +0x6c byte countdown of the phase
    done: bool = True               # +0x136 the swing has finished (set when the recovery ends)
    swing_target: int = None        # +0x5c target of the swing in progress
    last_attacker: int = None       # +0x40 whoever hit this unit last

    def __post_init__(self):
        if self.mover.target_facing < 0:
            self.mover.target_facing = self.facing      # the ctor writes mover[0] and mover[1] together


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

    def __init__(self, cells, heights, name="", terrain=None, seed=DEFAULT_SEED):
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
        self.seed = seed & 0xFFFFFFFF   # the game's RNG seed (docs/engine/simulation.md section 10)
        self.rng = Rng(seed)            # the one generator of the simulation, drawn in update order
        self.objects = {}           # id -> MapObject
        self.units = {}             # id -> Unit, in map record order
        self.items = {}             # id -> Item (ground piles), in section 8 order
        self.players = {}           # id (1-based record) -> Player
        self.groups = {}            # id -> OrderGroup, in creation order (sim/orders.py)
        self.events = []            # NoWay ...: for the UI, not part of dump()/the hash
        self.fight_log = []         # Damage / Died entries (sim/combat.py), drained by the UI, not part of the dump
        self.item_table = None      # allods2.formats.itemdefs.ItemTable (from_map); combat stats read it
        self._next_group = 1
        self.report = BuildReport()
        self._cells = {}            # (x, y) -> set of ids over present footprint cells
        self._claim = {}            # (x, y) -> id of the structure registered there (first wins)
        self._ucells = {}           # (x, y) -> set of unit ids   (never part of the block layer)
        self._icells = {}           # (x, y) -> set of item ids
        self._next_seq = 1
        self._next_cell_seq = 1
        self.costs = pas.DEFAULT_COSTS      # map.reg [Terrain] Cost<name> (from_map loads the install's)
        self.speed_multiplier = 8           # map.reg [Path Finding] SpeedMultiplier (CONFIRMED 8)
        self._cost = None
        self.block_rev = 0                  # bumped whenever a block cell is recomputed (path-grid cache key)
        self._base = pas.terrain_base(self.terrain)         # computed once
        self._block = self._base.copy()
        self._border()
        self._view = self._block.view()
        self._view.flags.writeable = False

    # --- views ---------------------------------------------------------------

    @property
    def cost(self):
        """(h, w) uint8 terrain movement cost (FUN_0055494d / FUN_0055a147), cached."""
        if self._cost is None:
            self._cost = pas.cost_layer(self.terrain, self.costs)
        return self._cost

    def set_costs(self, costs):
        """Install a terrain cost table (index = terrain type, `passability.costs_from_reg`)."""
        self.costs, self._cost = tuple(costs), None

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
        self.block_rev += 1
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
        u.cell_seq, self._next_cell_seq = self._next_cell_seq, self._next_cell_seq + 1
        self.units[u.id] = u
        self._index_add(self._ucells, u)
        return u.id

    def remove_unit(self, uid):
        u = self.units.pop(uid)
        self._index_del(self._ucells, u)
        g = self.groups.get(u.order_group)
        if g is not None and uid in g.members:
            g.members.remove(uid)
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
        if (u.x, u.y) != (x, y):
            u.cell_seq, self._next_cell_seq = self._next_cell_seq, self._next_cell_seq + 1
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
    def from_map(cls, m, assets, facing=None, seed=DEFAULT_SEED):
        """From an `allods2.formats.Map` and an `AssetCache` (spec "World").
        Structures first in record order, then section 3 cells row-major;
        bulk-added, then one full block build; then players, units and ground piles in
        record order.  `facing`: None gives each unit the exe's start angle 0x40 + [0, 128)
        (the exe's rand, here a fixed hash of the uid so a map always loads the same);
        an int puts every unit at that angle byte (0x80 = front view, as `map render`)."""
        w = cls(m.runtime_terrain(), m.heights_i8, m.name, terrain=m.terrain, seed=seed)
        if hasattr(assets, "map_reg"):                  # test doubles keep the defaults
            costs, w.speed_multiplier = assets.map_reg()
            w.set_costs(costs)
        if hasattr(assets, "items"):
            w.item_table = assets.items()
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
                hp = hp_max = fent.NO_HP                    # FUN_00561bf9 0x562013: a human at full HP = default = the recomputed maximum
            base = tpl.hp_max if tpl is not None else 0     # map overrides replace the template value
            mana_max = 0
            if rec.is_human and tpl is not None:            # FUN_0051366b: a human never uses the template healthMax
                base, mana_max = prog.derived_vitals(tpl)
            face = tpl.face if tpl is not None else 1
            move = tpl.movement_type if tpl is not None else 1
            hp_max = base if hp_max == fent.NO_HP else hp_max
            hp = hp_max if hp == fent.NO_HP else hp
            known = tpl is not None and assets.unit_set(rec.type) is not None
            u = Unit(UNIT_ID_BASE + rec.uid, rec.type, rec.owner, rec.x >> 8, rec.y >> 8,
                     rec.x & 255, rec.y & 255, unit_angle(rec.uid, facing), IDLE, 0, hp, hp_max,
                     rec.uid, rec.server_id, rec.is_human, rec.behaviour, move, face, rec.squad, rec.group, known,
                     stats=tpl)
            if tpl is not None and not rec.is_human:
                u.mover.turn_rate = max(1, tpl.turn_rate)       # mover+0xa: monster p9; humans: the speed stat (sim/movement.py)
            if rec.is_human and tpl is not None:        # docs/data/progression.md section 4: no award logic yet
                u.skills = prog.skills_of(tpl)
                u.mana = u.mana_max = mana_max
                u.xp, u.xp_total = prog.start_pools(u.skills)
                u.best_school = prog.best_school(u.skills) if prog.is_hero_name(tpl.name) else 0
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

    # --- consistency ---------------------------------------------------------------

    def check_consistency(self):
        """Internal invariants of the indexes and of the movement state; returns a list of problem strings (empty =
        consistent).  Checked: the per-cell unit/item index equals the entities' cells, every position is inside the
        map with a sub-cell byte, a step in progress holds a reservation (`step_target`, adjacent to `step_from`,
        the unit standing on one of the two: the live layer is derived from exactly these), groups and selections
        refer to living entries, a unit is in at most the one group it names."""
        bad = []
        for name, table, index in (("unit", self.units, self._ucells), ("item", self.items, self._icells)):
            want = {}
            for e in table.values():
                want.setdefault((e.x, e.y), set()).add(e.id)
                if not (0 <= e.x < self.width and 0 <= e.y < self.height):
                    bad.append("%s %#x outside the map at (%d, %d)" % (name, e.id, e.x, e.y))
            if want != index:
                bad.append("%s index differs from the entities' cells" % name)
        for u in self.units.values():
            m = u.mover
            if not (0 <= u.sub_x < 256 and 0 <= u.sub_y < 256):
                bad.append("unit %#x sub-cell (%d, %d)" % (u.id, u.sub_x, u.sub_y))
            if bool(m.step_ticks) != (m.step_target is not None):
                bad.append("unit %#x: step_ticks %d but step_target %s" % (u.id, m.step_ticks, m.step_target))
            if m.step_target is not None:
                t, f = tuple(m.step_target), tuple(m.step_from) if m.step_from else None
                if f is None or max(abs(t[0] - f[0]), abs(t[1] - f[1])) != 1:
                    bad.append("unit %#x: step %s -> %s is not one cell" % (u.id, f, t))
                elif (u.x, u.y) not in (t, f):
                    bad.append("unit %#x at (%d, %d) is on neither end of its step %s -> %s" % (u.id, u.x, u.y, f, t))
                if not (0 <= t[0] < self.width and 0 <= t[1] < self.height):
                    bad.append("unit %#x reserves %s outside the map" % (u.id, t))
            if u.order_group:
                g = self.groups.get(u.order_group)
                if g is None or u.id not in g.members:
                    bad.append("unit %#x names group %d which does not list it" % (u.id, u.order_group))
        seen = {}
        for g in self.groups.values():
            for i in g.members:
                if i not in self.units:
                    bad.append("group %d lists missing unit %#x" % (g.id, i))
                elif self.units[i].order_group != g.id:
                    bad.append("group %d lists unit %#x which names group %d" % (g.id, i, self.units[i].order_group))
                if i in seen:
                    bad.append("unit %#x is in groups %d and %d" % (i, seen[i], g.id))
                seen[i] = g.id
        for p in self.players.values():
            for i in p.selection:
                if i not in self.units:
                    bad.append("player %d selects missing unit %#x" % (p.id, i))
        return bad

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
                            + self._player_extra(p)
                            for _, p in sorted(self.players.items())],
                "units": [[u.id, u.type_id, u.owner, u.x, u.y, u.sub_x, u.sub_y, u.facing, u.action,
                           u.action_start_tick, u.hp, u.hp_max, u.uid, u.server_id, int(u.human),
                           u.behaviour, u.move_type, u.face, u.squad, u.group, int(u.known)]
                          + self._mover_dump(u)
                          for _, u in sorted(self.units.items())],
                "items": [[i.id, i.x, i.y, i.sub_x, i.sub_y, i.gold, list(i.codes), list(i.groups)]
                          for _, i in sorted(self.items.items())],
                "block": [bytes(row).hex() for row in self._block],
                **({"groups": [[g.id, g.owner, list(g.members), g.order, list(g.target), g.speed]
                               for g in self.groups.values()]} if self.groups else {}),
                **({"rng": self.rng.state} if self.rng.state != self.seed else {})}

    @staticmethod
    def _player_extra(p):
        """Optional trailing dict of a player entry: only non-default state (old goldens stay valid)."""
        d = {}
        if p.selection:
            d["selection"] = list(p.selection)
        if p.formation != 1:
            d["formation"] = p.formation
        return [d] if d else []

    @staticmethod
    def _mover_dump(u):
        """Movement state, only for a unit that has any (idle units keep the short entry)."""
        m = u.mover
        fight = World._fight_state(u)
        if fight is None and not (u.order or u.state or u.path or u.odometer or m.steps or m.turning or u.order_group
                                  or u.stopped or m.waiting or m.parked or m.target_facing != u.facing):
            return []
        d = {"order": u.order, "state": u.state, "path": [list(c) for c in u.path],
             "odometer": u.odometer, "target_facing": m.target_facing,
             "step": [list(m.step_target) if m.step_target else None, m.steps, m.step_ticks,
                      m.step_len, m.step_dir, m.dx, m.dy],
             "turn": [int(m.turning), m.turn_ticks, m.turn_done]}
        if m.goal is not None or m.dest is not None or m.static_path:      # only planned orders
            d["plan"] = [list(m.goal) if m.goal else None, list(m.dest) if m.dest else None,
                         list(m.tail) if m.tail else None, m.consumed, m.since_hop, int(m.arrived),
                         int(m.failed), [list(c) for c in m.static_path]]
        if m.waiting or m.parked:                                           # only after a blocker wait
            d["wait"] = [int(m.waiting), int(m.parked)]
        if u.order_group or u.stopped or u.anchor:                          # only after a player command
            d["cmd"] = [u.order_group, int(u.stopped), list(u.anchor) if u.anchor else None]
        if u.mode_go and u.order != 1:                                      # a restarted unit under the stand order
            d["mode"] = 1
        if fight is not None:
            d["fight"] = fight
        return [d]

    @staticmethod
    def _fight_state(u):
        """Fight state as a dict, None for a unit that never fought (old goldens stay valid)."""
        m = u.mover
        if (u.target is None and not u.mode_attack and not u.brain_order and not u.phase and u.done and not u.timer
                and not u.swing_count and u.last_attacker is None and u.swing_target is None and m.follow is None
                and m.follow_cell is None):
            return None
        return {"target": u.target, "mode": int(u.mode_attack), "range": u.range, "brain": u.brain_order,
                "count": u.swing_count, "phase": u.phase, "timer": u.timer, "done": int(u.done),
                "swing": u.swing_target, "by": u.last_attacker,
                "follow": [m.follow, list(m.follow_cell) if m.follow_cell else None, m.static_len]}

    def dump_json(self):
        return json.dumps(self.dump(), sort_keys=True, separators=(",", ":"))

    def dump_hash(self):
        return hashlib.sha256(self.dump_json().encode("ascii")).hexdigest()
