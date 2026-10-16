# Engine architecture (G1: skeleton)

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
| 4 | `engine/sim/` | `Simulation.step`, systems list, `Command`, `CommandQueue`, tick clock | 1-3 |
| 5 | `engine/ui/` | input state to commands and to camera motion (`ScrollInput`) | 1-4, `engine.view` (camera) |
| 6 | `engine/view/` | `Camera`, coordinates, visible range, per-cell compositing, draw list | 1-3 |
| 7 | `engine/backend_pygame/` | window, surface cache, blitting, events, main loop, screenshot | everything; the only layer that imports pygame |

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
    ui.update(dt, input_state, camera)    # scroll -> camera (UI state)
    for cmd in ui.commands(): queue.put(cmd)
    while acc >= period_ms:               # fixed-step simulation
        sim.step(queue.drain())           # world.tick += 1, systems run
        acc -= period_ms
    terrain = view.build_terrain_items(terrain_view, camera, world.tick)
    items = view.build_draw_list(world, camera, world.tick, assets, options, debug)
    backend.draw(terrain, items, camera)  # surface caches + blits + blends + flip
```

The camera moves with frame time (smooth), the simulation with ticks. The draw list
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

`python -m engine run MAP [--x PX --y PX] [--speed 0..8] [--size WxH] [--install DIR]`
and `python -m engine screenshot MAP X Y DEST.png [--tick N] [--size WxH]
[--install DIR]` (SDL dummy driver, no window). `python -m engine world-info MAP [--strict]` and
`world-dump MAP DEST.json` need no pygame (section 9). `X`, `Y` = camera top-left in
world pixels. `run` defaults to the playable area corner `(8*32, 8*32)`
(the outer 8 cells are the unplayable border, [map](../formats/map.md)).
Controls: arrow keys and mouse within 4 px of the window edge scroll at 600 px/s
(DECISION, not from the exe); Esc quits.

## 9. World state

Spec: [world state design](../superpowers/specs/2026-10-16-world-state-design.md);
code `engine/world.py`; map facts in [map.md parts 3-4](../formats/map.md).

- **Tables**: `World.objects` (id -> `engine.world.MapObject`, kinds `object`,
  `structure`, `bridge`), empty placeholders `units`, `items`, `players`. The engine
  `MapObject` is not `allods2.formats.objects.MapObject` (the parsed section 3 record).
- **Ids**: structures `0x6000 + uid` (CONFIRMED: map.md part 4), section 3 cells
  `0x10000 + n` (row-major index; DECISION, the exe has no id for a layer cell),
  units later from 0x20000 (the exe keeps ids below 0x6000 for dynamic objects).
  A duplicate id is a `ValueError`.
- **Spatial index** `_cells[(x, y)] -> set(ids)` over the BuildingPresent cells
  (an object: its cell); empty sets are deleted.
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
- **`World.from_map(map, assets)`**: structures in record order, then section 3 cells of the loaded
  window; unknown types go to `world.report.unknown` (entity kept, `known=False`). `dump_json()` /
  `dump_hash()` are the deterministic form used by `world-dump` and `tests/golden.json`
  (regenerate with `tools/update_golden.py`).
- `AssetCache.databin()` and `objects_reg()` supply the stats and the object ids (no pygame).

Open: see [open-questions](../open-questions.md#engine).

## Open questions

- Exe view scroll limits, speeds and edge-scroll zone (not traced; engine uses
  DECISION values above).
- Day/night light in the engine (the exe recomputes the light map with the
  clock; G1 uses the fixed default).
- Scroll hitch of about 27 ms when new cells enter (pre-warm water phases or add a
  flat-cell fast path to `composite`).
- Trigger references (map sections 5-12) to world ids: structures `0x6000 + uid` assumed; section 3
  cells have no exe id. Starting routine: reader `FUN_00534ad4` cases 5-12.
- Removing a structure: the exe clears every present cell, also those held by another structure
  (`FUN_0055995a`); the engine releases only the cells the structure holds.
