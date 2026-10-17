# Engine architecture (G1: skeleton, world state, units G3a, interface and selection G3b)

Spec of record: [engine skeleton design](../superpowers/specs/2026-10-16-engine-skeleton-design.md).
Code: `engine/` (the game), `allods2/assets.py` (asset cache). The engine is
a new layer over the reverse-engineered core; it does **not** copy the exe's
structure, but where the exe's behaviour is known (tick period, water
animation clock, draw order, height offsets) the engine reproduces it exactly
and the spec of that behaviour is linked. Facts are marked CONFIRMED /
INFERRED; engine choices that are not from the exe are marked DECISION.

## 1. Layers

Dependencies point down only (a layer imports layers with a smaller number).

| # | Package | Role | May import |
|---|---|---|---|
| 1-2 | `a2res/`, `allods2/` (incl. `allods2/assets.py`) | archives, formats, decoders, asset cache | stdlib, numpy, Pillow; never pygame, never `engine` |
| 3 | `engine/world.py` | `World`: cells, heights, tick counter, entity tables, spatial index, block layer | layers 1-2 |
| 4 | `engine/sim/` | `Simulation.step` (+ command log), systems list (selection, movement), `Command` / `SelectUnits` / `FollowPath`, `CommandQueue`, tick clock ([simulation](simulation.md)) | 1-3 |
| 5 | `engine/ui/` | `Layout`, `choose_cursor`, `SelectionInput` (-> `SelectUnits`), `ScrollInput`, `MinimapPanel` | 1-4, `engine.view` (camera, `pick`) |
| 6 | `engine/view/` | `Camera`, coordinates, visible range, per-cell compositing, draw list | 1-3 |
| 7 | `engine/backend_pygame/` | window, surface cache, blitting, events, main loop, screenshot, `interface.py` (panels, info panel), `cursor.py`, `text.py` (`draw_text`) | everything; the only layer that imports pygame |

Rules (enforced by `tests/test_engine_boundaries.py`, an AST scan):

1. `allods2` and `a2res` never import `pygame` or `engine`.
2. `engine.world` and `engine.sim` never import `pygame`, `engine.view`,
   `engine.ui` or `engine.backend_pygame`.
3. `engine.view` and `engine.ui` never import `pygame` or
   `engine.backend_pygame` (DECISION: they are pure numpy/Python, so they
   test headless). `engine.view` does not import `engine.ui` or `engine.sim`.
4. Input reaches the simulation only as `Command` objects through the queue.
   UI-only state (camera, scrolling) never touches the world.
5. The view reads the world and never writes it.
6. Entities cross layers as integer ids, never as object references.

## 2. Assets

`allods2.assets.AssetCache(fs=None)`: loaded once, returned shared.
`tileset()` -> `graphics.terrain.TerrainSet`; `sprite(path)` -> `SpriteFile`;
`map(spec)` is not part of it (maps are loaded by the CLI via
`allods2.cli.open_map`). No pygame: pixel data stays numpy. Conversion to
surfaces happens only in the backend (`SurfaceCache`).

## 3. Coordinate systems

| Name | Unit | Origin | Notes |
|---|---|---|---|
| cell | cells `(col, row)` | map top-left | `0..w-1`, `0..h-1` |
| vertex | `(col, row)`, one more than cells each way | map top-left | heights `H[row][col]` signed byte |
| world px | pixels | map top-left at height 0 | `x = 32*col`, `y = 32*row - H` (CONFIRMED `FUN_004065b1`, [terrain](../formats/terrain.md#vertex-table-fun_004065b1)); 1 height unit = 1 px |
| screen px | pixels | viewport top-left | `screen = world - camera` |

- A cell is the quad of its four vertices; its pixel columns are
  `32*col .. 32*col+31`; the quad edges follow `terrain.edge_offsets`.
- `cell -> world`: the cell origin is vertex `(col, row)`; the cell centre is the
  exact middle of column 16 (`top(16)`, `bot(16)`). `world -> cell`: column is
  `x // 32`; the row is found by searching the rows whose height padding can
  reach `y` and keeping the **last** (lowest) row whose column span contains `y`,
  because later rows overwrite earlier ones when drawn
  ([terrain: draw order](../formats/terrain.md#draw-order-fun_00404e0e)).
  Points outside every drawn cell give `None`.
- Camera: top-left in world px (float internally, floor for drawing),
  clamped so the viewport stays inside `x in [0, 32*w - vw]`,
  `y in [0, 32*h - vh]` (DECISION: the flat grid extent; relief that pokes above
  `y = 0` or below `32*h` is not scrollable into; when the viewport is larger than
  the map the camera is 0 and the rest is black).
- `render_3d` image pixel `(X, Y)` is world `(X, Y - top)` with `top = max(0,
  -min vertex y)`; the engine's screenshot at camera `(x, y)` equals
  `render_3d[top + y : top + y + vh, x : x + vw]` (tested).

## 4. Time

- Tick = fixed step, `period = 1000 // rate` ms with `rate` from speed 0..8 =
  8, 10, 12, 14, 16, 20, 24, 28, 32 ticks/s (CONFIRMED,
  [animation §3.1](../formats/animation.md#31-the-game-tick)); default speed 4 =
  16 ticks/s = 62 ms. The speed is a parameter.
- The exe re-bases its clock every 16 ticks; the engine uses a plain
  accumulator with a frame-time cap (DECISION, `MAX_FRAME_MS = 250`: a stall
  produces at most `250 // 62 = 4` catch-up ticks at the default speed).
  Documented difference: the exe may run up to 15 ticks back to back after a
  stall.
- Animation clock = `world.tick` (view clock `+0xa88` is +1 per tick). Water
  cells use `8 + ((set + (x+1)*y + (tick >> 2)) & 3)` (CONFIRMED,
  [terrain](../formats/terrain.md#cell-value)).

## 5. Main loop

```
acc = 0
while running:
    dt = clock.tick()                     # ms since last frame
    acc += min(dt, MAX_FRAME_MS)
    events = backend.poll()               # window/keys/mouse -> abstract input
    ui.update(dt, input_state, camera)    # scroll -> camera (UI state); minimap press/drag
    for cmd in ui.commands(): queue.put(cmd)   # SelectionInput.release -> SelectUnits (right click: empty)
    while acc >= period_ms:               # fixed-step simulation
        sim.step(queue.drain())           # world.tick += 1, systems run
        acc -= period_ms
    terrain = view.build_terrain_items(terrain_view, camera, world.tick)
    items = view.build_draw_list(world, camera, world.tick, assets, options, debug, selection)
    backend.draw(terrain, items, camera)  # black window, viewport, strips and panels, info panel
    backend.draw_cursor(choose_cursor(...))   # last, at mouse - hotspot; the OS cursor is hidden
```

The camera moves in whole cells per tick period (section 8), the simulation with ticks.
`Simulation(world)` installs the selection system by default; every command it receives is appended
to `Simulation.log` as `(tick, command)` (rejected ones too: the log is the input), and
`replay(sim, log, ticks)` feeds it back (same `dump_hash` and selection, tested).

**Commands and selection (G3b, spec
[interface and selection](../superpowers/specs/2026-10-17-interface-selection-design.md))**:
`SelectUnits(player_id, unit_ids, toggle)`. Set: accepted when every id is owned by the player or
exactly one unit of another owner (info only), else rejected and the selection kept; empty clears.
Toggle: own ids only, and only while the selection is not foreign. Unknown or removed ids are dropped.
`Player.selection` is a tuple in command order; `World.remove_unit` purges it; `World.dump()` adds a
`selection` entry to a player only when non-empty (old goldens stay valid). The exe keeps selection as a
flag on each client object, not a list (CONFIRMED, [ui-layout §8](ui-layout.md)); the engine's per-player
tuple is the DECISION that makes it a replayable command. Picking, cursors, layout and the marker:
[ui-layout](ui-layout.md), [rendering §14](rendering.md#14-interface-cursor-picking-marker-g3b). The draw list
(sprites of map objects and structures, shadows, debug overlays) is described in
[rendering.md](rendering.md).

## 6. Terrain drawing

Objects, structures, shadows and the draw order over the terrain: [rendering.md](rendering.md).

Per visible cell, numpy compositing reuses the core functions
(`terrain.tile_columns`, `shade_table`, `vertex_y`, `light_rows` indirectly
through `tile_columns`, `terrain_light`), so every pixel equals
`render_3d` for the same area by construction. A cell becomes an RGBA array
(alpha 255 where the game's blit writes, 0 elsewhere) placed at its first
written row; the backend turns it into a surface once (`SurfaceCache`, LRU,
key `(col, row, water phase)`). Static cells are cached once, water cells once
per animation phase (4). Cells are drawn row by row, top to bottom. Light is
the map's terrain light at the fixed default daylight, as `map render
--relief` (DECISION; day/night is a later task). The dirt flag is cleared as
on load (`Map.runtime_terrain`).

Measured (map 10, 80x80, 1024x768 viewport, 896 cells, SDL dummy driver):
uncached composite + blit 740 ms per frame (about 0.8 ms per cell: too slow, so
the cache is mandatory); cold cached frame 730 ms (once); warm frame 2 ms
(build list 1 ms, blits 1-2 ms); scroll by one cell column or row 27 ms
(about 30 new cells). Water cells composite once per phase, so a full-water
view hitches once per phase on its first cycle (open: pre-warm, or a flat-cell
fast path in `composite`).

## 7. Visible range

`visible_cells(camera)` returns cell ranges `x0 <= col < x1`, `y0 <= row < y1`.
Columns: those intersecting `[cam.x, cam.x + vw)`. Rows: padded by the map's
min/max height, because a cell can draw anywhere in
`[32*row - Hmax, 32*(row+1) - Hmin]`. Pure over-estimate, never misses a pixel.

## 8. CLI

`python -m engine run MAP [--x PX --y PX] [--speed 0..8] [--size 640x480|800x600|1024x768] [--install DIR]`
(always the original interface, default 640x480) and `python -m engine screenshot MAP X Y DEST.png [--tick N]
[--size WxH] [--interface [--select UID,...]] [--install DIR]` (SDL dummy driver, no window; `--interface`
renders the full window, default 640x480, otherwise only the viewport as before). `python -m engine world-info MAP [--strict]` and
`world-dump MAP DEST.json` need no pygame (section 9). `X`, `Y` = camera top-left in
world pixels. `run` defaults to the playable area corner `(8*32, 8*32)`
(the outer 8 cells are the unplayable border, [map](../formats/map.md)).
Controls: arrow keys, and the mouse on the screen border (x == 0, y == 0, x >= W-2, y >= H-2; panels do not
matter), scroll **one whole cell per tick period** (62 ms at the default speed), clamped to the 8-cell border
(CONFIRMED, [ui-layout §5](ui-layout.md)); left click / drag selects, Shift toggles, right click clears
(DECISION), Ctrl+H health bars, F1-F3 debug, Esc quits. The camera is built from the layout's viewport.

## 9. World state

Spec: [world state design](../superpowers/specs/2026-10-16-world-state-design.md);
code `engine/world.py`; map facts in [map.md parts 3-4](../formats/map.md).

- **Tables**: `World.objects` (id -> `engine.world.MapObject`, kinds `object`,
  `structure`, `bridge`), `units` (`Unit`), `items` (`Item`, ground piles), `players` (`Player`),
  all filled by `from_map` in record order (dict order = file order). The engine
  `MapObject` is not `allods2.formats.objects.MapObject` (the parsed section 3 record).
- **Ids**: structures `0x6000 + uid` (CONFIRMED: map.md part 4), section 3 cells
  `0x10000 + n` (row-major index; DECISION, the exe has no id for a layer cell),
  **units `0x6000 + uid`** (CONFIRMED: the client view `+4`, same space as structures; uids never collide with
  structure uids in the 46 maps, a collision is a `ValueError`; trigger references use this id), ground piles
  `0x30000 + index of their first section 8 group` (ours), players the 1-based section 5 record number (the
  value `Unit.owner` holds).
  A duplicate id is a `ValueError`.
- **Spatial index** `_cells[(x, y)] -> set(ids)` over the BuildingPresent cells
  (an object: its cell); empty sets are deleted.
- **Units and items in the index** (G3a): `units_at`, `items_at`, `entities_at` (per-cell id sets, separate dicts
  `_ucells`, `_icells`; `add_unit/remove_unit/move_unit`, `add_item/remove_item`). **Units never touch the
  static block layer** (DECISION, as the exe: the static layer comes from terrain and objects only,
  `FUN_00554626`; the live layer's unit stamps, `FUN_0055be86`, are dynamic blocking = phase H).
- **Block layer** (`World.block`, read-only (h, w) uint8), per cell in this order:
  terrain base from the raw tile (dirt 0x2000, Mountain, water -> 1, `passability.terrain_base`);
  a section 3 object -> 5; the 8-cell border -> 0x1F (`FUN_00554626`, `FUN_00553b30`);
  then the structure that *holds* the cell: solid bit `|= 5`, free `&= 0xFA`
  (`FUN_00550a96`). A structure holds a cell by registering (`FUN_005599df`): present cells
  in row-major order, the first already-held cell ends the registration (first wins,
  CONFIRMED, map.md part 4). Heights never enter (CONFIRMED).
- **Local recompute**: `add_object`, `remove_object`, `move_object` redo the registration of the
  group of overlapping structures touching the old and new footprint cells and refresh only
  those cells; `rebuild_block()` is the from-scratch reference (tested equal after every step
  and for every campaign map). A failed add (duplicate id, anchor outside the map) changes nothing.
- **Units** (`Unit`, fields named after the exe's Creature, [unit-struct §2](unit-struct.md)): `id, type_id, owner,
  x, y` (cell) `+ sub_x, sub_y` (1/256, 128 = centre), `facing` (mover angle byte, 0 up, clockwise, draw direction
  `>> 4`), `action` (`"idle"`), `action_start_tick`, `hp, hp_max, uid, server_id, human, behaviour, move_type, face,
  squad, group, known`. HP: file override else data.bin `healthMax`; a human with `hp == max_hp` resets to the default
  (`0x562013`); difficulty scaling is not applied. **Facing**: the file has none; `from_map(facing=None)` gives each unit
  `0x40 + rand(128)` like the creature constructor (CONFIRMED), the random draw replaced by a hash of the uid
  (DECISION: deterministic); `facing=int` fixes the angle (E5 uses `0x80`). Players: `Player(id, colour, name,
  flags, money, relations, human)`, human = record 1.
- **Ground piles** (`Item`): section 8 groups no unit's `group` links to; groups on one cell merge (gold added,
  items stacked, CONFIRMED `FUN_0052ab07`), so 19 groups are 17 piles in the install.
- **Unknown or odd units**: unknown types (no units.reg sprite file or no data.bin record) stay with `known=False`
  and are listed in `report.unknown_units` (none in the install); an owner that is not a player is a `ValueError`.
  `report.units_on_blocked` counts units whose cell the static layer blocks for their movement type: **9** in the 46
  maps. The exe server never creates them (`FUN_00510089` called with radius 0 at map load tries only the file cell
  and deletes the unit on failure, CONFIRMED); the client copy `FUN_004a449c` uses the file position, so they stay
  as inert phantoms (INFERRED). The engine keeps and draws them. Four units start at HP 0 (file `hp` 0, max default): a
  walker stays at HP 0 as a corpse for good, a flyer or ghost dies on tick 1 (CONFIRMED `0x50f1b9`-`0x50f24b`,
  `0x50fecb`); no behaviour yet, they idle.
- **Simulation** (G3a, H1): `Simulation.step` runs the systems (selection, then [movement](simulation.md)) and
  advances `world.tick`; units stay in `idle` with `action_start_tick = 0` until ordered, so animation time (`world.tick - action_start_tick`) comes from the simulation and
  never from the render clock (tested at 30 and 60 fps render rates).
- **`World.from_map(map, assets, facing=None)`**: structures in record order, then section 3 cells of the loaded
  window, then players, units, piles; unknown types go to `world.report.unknown` (entity kept, `known=False`). `dump_json()` /
  `dump_hash()` are the deterministic form used by `world-dump` and `tests/golden.json`
  (regenerate with `tools/update_golden.py`).
- `AssetCache.databin()` and `objects_reg()` supply the stats and the object ids (no pygame).

Open: see [open-questions](../open-questions.md#engine).

## Open questions

- Scroll: answered in G3b (whole cell per tick, border rule, 8-cell clamp; ui-layout §5). The view's exact
  "centre on unit" call is not wired (`(unit.x >> 8) - W/2`, no height term, CONFIRMED earlier).
- Day/night light in the engine (the exe recomputes the light map with the
  clock; G1 uses the fixed default).
- Scroll hitch of about 27 ms when new cells enter (pre-warm water phases or add a
  flat-cell fast path to `composite`).
- Trigger references to world ids: section 11 is keyed by structure uid (`0x6000 + uid`, CONFIRMED,
  `FUN_00561422`); section 7 slots are coded numbers 8000–9999; section 3 cells have no exe id.
- Removing a structure: the exe clears every present cell, also those held by another structure
  (`FUN_0055995a`); the engine releases only the cells the structure holds.
