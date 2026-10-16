# World state (G2a'): entities from a map, spatial index, passability

Task label in CLAUDE.md: the next item after this is G2b.

## Intent
Fill `engine/world.py` from a loaded map: every tree/rock and structure becomes an
entity with a stable integer id, a cell -> ids spatial index, and a passability grid that
follows the documented rules and updates locally when an entity is added, removed or
moved. Fully testable headless (no pygame import anywhere in this path).

## Decisions and assumptions (made without further questions)
1. **One table, a `kind` field.** `world.objects: dict[int, MapObject]` holds both section 3
   (trees, rocks, decorations: `kind="object"`) and section 4 (`kind="structure"`,
   bridges `kind="bridge"`) entries, because the brief asks for one table. IDs of
   `objects.reg` and `structures.reg` overlap, so `(kind, type_id)` is the type key.
   The engine class is `engine.world.MapObject`; it is distinct from
   `allods2.formats.objects.MapObject` (the parsed record) and is never confused with it
   (the world imports the format class under an alias).
2. **Ids.** Structures: `0x6000 + uid` (CONFIRMED runtime object id, map.md part 4;
   uid 1..363 so ids 0x6001..0x616B), in section 4 record order. Section 3 cells:
   `OBJECT_ID_BASE + n` with `OBJECT_ID_BASE = 0x10000`, `n` = row-major index among the
   window cells (`Map.placed_objects()`), because the file gives cells no ids.
   Units/items/players get their own ranges later (reserve 0x20000+). **INFERRED:** that
   the trigger references (sections 5-12, still raw, open question) use these ids; the
   structure id is the game's own object id, the object ids are ours. Duplicate ids are an
   error (`ValueError`), never silently overwritten.
3. **Window.** Only the cells the game loads (rows 8..h-5, columns 8..w-9) become entities
   (`placed_objects(window=True)`, CONFIRMED animation.md §1.7). The count of ignored
   outside-window cells is kept in the build report. All of them lie inside the 8-cell
   border (derivation: the border is 8 cells on every side, so rows h-8..h-1 and columns w-8..w-1 and 0..7 are border, and the window only excludes cells in rows h-4..h-1 or columns w-8..w-1 or 0..7), so the block
   layer is identical with or without them; a test checks that on every map.
4. **Unknown types** go into `world.report.unknown` as `(kind, type_id, x, y)`; the entity
   is still created (footprint = the cell for objects; for structures the rectangle from
   data.bin if present, else the cell) and flagged `known=False`; `from_map` never raises
   for them and never drops them silently. Known = `type_id` resolves in `objects.reg`
   (objects) or data.bin structures (structures). `world-info` prints the list and exits 0;
   exit code 2 only for `--strict`.
5. **Heights do not affect passability** (CONFIRMED map.md part 3: "the block layer never
   reads heights"). Heights enter only through speed and sight (not in this task). The
   task's "terrain/height rules" is therefore terrain + objects + border + footprints.
6. **"E3's debug overlay"** does not exist in the repo. The independent reference for
   tests is a scalar re-implementation of the map.md text written inside the test.
7. ~~Later structure wins on shared present cells.~~ **Superseded by REA (see Implementation
   notes): the first structure wins and the registration of the later one stops.**
8. Squares only: `passability.block_layer` raises on non-square maps; all 46 campaign maps
   are square. The synthetic world must be square too.

## MapObject (dataclass, mutable fields only where the sim may change them)
```
id: int                 kind: "object" | "structure" | "bridge"
type_id: int            # objects.reg ID / structures.reg ID (bridge: 0x21)
x, y: int               # top-left cell
sub_x, sub_y: int       # 1/256 cell inside the cell, 128 = centre (CONFIRMED all files)
variant: int = 0        # reserved (frame/skin choice; not stored in the file)
owner: int = 0          # structures: 1..8 section 5 record index, objects: 0
hp, hp_max: int         # structures: data.bin healthMax (0 -> 1000); hp = hp_max or 0
                        #   when intact == 0 (CONFIRMED 0x4a4a5c); objects: 0, 0
flags: int = 0          # bit 0 destroyed (hp == 0 at load); rest reserved
uid: int = 0            # structures: section 4 uid; objects: 0
footprint: tuple        # ((dx, dy, solid), ...) for the BuildingPresent cells in row-major
                        #   order; solid = Passability bit (index mod 32, mask_cells)
known: bool = True
seq: int                # stamp order (assigned on add; later wins), not serialised
```
`footprint` for an object is `((0, 0, True),)`. For a bridge the mask is 0 so every cell is
`solid=False` over the whole w x h rectangle. Cells outside the map are dropped.

## World
- Tables: `objects` (filled), `units`, `items`, `players` (empty dicts, documented
  placeholders). `new_entity()` / `entities` from G1 are removed; their one test is
  updated. `tick` stays.
- `World(cells, heights, name="", terrain=None)`: `terrain` is the raw Tiles (dirt bit
  kept) the server reads for the block layer; default `cells`.
- `add_object(obj) -> id`, `remove_object(id)`, `move_object(id, x, y)` (= remove + re-add
  with the same id and seq), `objects_at(x, y) -> frozenset[int]`, `blocked(x, y, mover=1)`,
  `walkable(mover=1) -> (h, w) bool`, `block -> (h, w) uint8` (read-only view).
- Spatial index `_cells: dict[(x, y), set[int]]` over present footprint cells; empty sets
  are deleted so the index never keeps dead keys. `add/remove/move` update index and
  block together or not at all (validate first, then mutate).
- Block layer, per cell `(x, y)` (map.md part 3 "Passability: derived" + part 4
  "Footprint and blocking"), in this order:
  1. terrain base from the raw tile: dirt bit 0x2000 -> 1; terrain type Mountain -> 1;
     water -> 1; else 0 (`passability.terrain_class` rules);
  2. a section 3 object on the cell -> 5 (replaces);
  3. the 8-cell border -> 0x1F;
  4. structures covering the cell in `seq` order: a present cell with `solid` -> `|= 5`,
     with not solid -> `&= 0xFA`.
  `_refresh(cells)` recomputes exactly those cells from the index; add/remove/move call it
  for the old and new footprint cells only (local recompute). `terrain_base` is computed
  once in the constructor (vectorised, shared with `passability.block_layer` helpers).
- `World.from_map(m, assets)`: `terrain=m.terrain`, `cells=m.runtime_terrain()`,
  heights; structures first in record order then objects row-major (so ids and seq follow
  record order); bulk-adds then one full block build (vectorised) for speed, which must
  equal repeated `_refresh` (tested). `assets` supplies `databin()` and
  `objects_reg()` (new `AssetCache` methods, no pygame); stats = `databin().structures`.
- `world.report`: `BuildReport(unknown: list, ignored_outside_window: int,
  counts: dict[(kind, type_id)] -> int)`.

## CLI (engine/__main__.py; must not import pygame)
- `python -m engine world-info MAP [--install] [--strict]`: entity counts per kind and
  per type (sorted), objects/structures total, blocked cell count (walker mask 0x41),
  unknown types, ignored outside-window cells.
- `python -m engine world-dump MAP DEST.json [--install]`: deterministic JSON
  (`sort_keys`, `separators=(",", ":")`, ints only): name, width, height, report, objects
  sorted by id (all fields except `seq`), block layer as one hex string per row. The
  default destination convention is `out/`; never committed.

## Tests (headless; assert `pygame` not in `sys.modules`)
- Every map (skip without the install): object count == `len(placed_objects()) +
  len(structures)`; ids unique and in the documented ranges; every id is in the index at
  every present footprint cell; no id in the index that is not in `objects`;
  `world.block` equals the independent reference (scalar, from the spec text:
  terrain classification via the documented rules, objects, border, structure stamps in
  record order) and equals `Map.block_with_structures(stats)`; block equal with
  `window=False` objects (derivation in decision 3).
- Synthetic square world: add/remove/move of an object and of a structure (solid cell,
  free cell, overlap of two structures, a structure over water, first wins) keep index and block equal
  to a from-scratch rebuild after every step; remove restores the exact prior block;
  failed add (duplicate id / out of map) leaves the world unchanged.
- Unknown type reported, entity present, `from_map` does not raise; CLI `world-info`
  prints it.
- Golden: `tests/golden.json` holds SHA-256 of the `world-dump` JSON for maps 10, 20, 52
  (ids chosen to exist; the hashes are derived values, no game data, so they may be
  committed). `tools/update_golden.py` regenerates; the test fails with a clear message
  when it differs. Skipped without the install.

## Docs
`docs/engine/architecture.md` gets a "World state" section (tables, ids, index, block
layer order with spec citations, local recompute, report). CLAUDE.md: Known so far +
"Next: G2b". Open questions (also in docs/open-questions.md): trigger-reference id
mapping (sections 5-12); double-claimed present cells (first vs later wins).

## Out of scope
Units, items, players content; dynamic unit stamps; cost layer use; drawing objects
(that is the next view task); the sim writing to the world.

## Implementation notes
Assumptions and findings recorded while implementing (all decisions made without questions).

REA results (objdump of the GOG exe 1.01, routine addresses in map.md part 4):
- **CONFIRMED, double-claimed cells: first wins, registration stops.** `FUN_00559890` returns 0
  when the cell already holds a structure (`0x5598c2`); `FUN_005599df` returns 0 at the first
  failure (`0x559a8d`) so the rest of that structure's present cells stay unregistered; the
  constructor (`0x5200b1`) ignores the result. The documented "later wins" stamping was wrong.
  `World` and `allods2.formats.objects.stamp_structures` now follow the exe (16 cells in 30.alm
  and 40.alm differ from the old output); map.md and tests updated. The registration is redone
  locally for the connected group of overlapping structures (seq order = add order).
- **CONFIRMED, refresh order** (`FUN_00550a96`): baseline (static block incl. border/objects, the two
  bytes the record took at creation, `FUN_005508a0`) first, then `|= 5` / `&= 0xFA`; so a
  structure stamp overrides the border (border cell + free structure cell = 0x1A). Same as
  decision 3's order. INFERRED: the static build precedes structure creation at load.
- **CONFIRMED, ids**: object ids are 16 bit; structures `0x6000 + uid` (client `0x4a48ab`, `0x4a511b`,
  `0x4a59fd`; server `0x52b2ac`, `0x52c1d7`); ids < 0x6000 are allocated dynamically (bitmap
  `0x6c9628`). A section 3 cell has no exe id. INFERRED (unchanged): trigger references use
  `0x6000 + uid` only; open.
- Not modelled: unregistering clears cells held by others (`FUN_0055995a`); the "record exists, no
  structure" branch of `FUN_00559890` skips the refresh. Both listed in open questions.

Deviations and choices:
- `World` accepts non-square arrays (decision 8 said raise) because the G1 view tests use 24 x 20
  worlds; the block layer works for any shape here (the exe uses a 256-wide grid for non-square
  maps, not modelled). Campaign maps are all square.
- An unknown structure type (not in data.bin) gets one solid cell and `hp_max` 1000; none occurs
  in the 46 maps (no unknown type of any kind).
- Entities have no `seq` in `dump`; `known` is dumped as 0/1; `world.report.counts` keys are
  `"kind:type"` strings in the dump.
- `move_object` out of the map raises `ValueError` before changing anything; footprint cells outside
  the map are dropped from index and claims.
- Independent reference grid in `tests/test_engine_world_maps.py` is scalar and written from map.md;
  it re-types the shape table (only set 7 can be Mountain). Golden maps: 10, 20, 52.
- Ignored outside-window object cells occur in 26 of 46 maps (all in the border; block identical).
