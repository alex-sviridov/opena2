# Engine skeleton (G1): layered structure + scrollable terrain window

## Intent
Set up the engine's layered structure and show a real map's terrain in a window
you can scroll. Layering is enforced by a test that scans imports.
Output of this task: `engine/` package, `allods2/assets.py`,
`docs/engine/architecture.md`, tests, CLAUDE.md update (Status: G1 done; Next: G2a).

## Decisions (from the brief and the brainstorm)
- Tick: fixed step, `period = 1000 // rate` ms, CONFIRMED in animation.md §3.1.
  Default speed 4 = 16 ticks/s, 62 ms. Speed is a parameter (0..8). No INFERRED constant.
  The game re-bases every 16 ticks; the engine uses a plain accumulator with a
  frame-time cap (documented difference).
- `docs/formats/tiles.md` does not exist; terrain.md is the source.
- "E2" = `map render --relief` (`render_3d`); "E3" = height offset (map.md Part 3,
  y = 32·row − H, 1 px per unit). Assumed, to be corrected if wrong.
- Dependencies: the `game` extra (pygame) is replaced by `engine` = `pygame-ce`.
  Nothing in allods2/ imports pygame. The two packages cannot coexist; the venv
  swap is confirmed with the user before it is run.
- Terrain drawing: per-cell numpy compositing of visible cells only, reusing
  `graphics.terrain.tile_columns` / `shade_table` / `vertex_y` (pixel parity with
  `render_3d` by construction). Backend caches per-cell surfaces: static cells once,
  water cells per animation frame. Performance is measured; the cache is the fix if slow.

## Layers (dependencies point down only)
| # | Package | Role |
|---|---|---|
| 1–2 | `allods2/` (+`a2res/`) | formats, decoders, `assets.AssetCache`; never imports pygame or engine |
| 3 | `engine/world.py` | entity storage (integer ids), map reference, tick counter |
| 4 | `engine/sim/` | `Simulation.step`, systems list (empty), `Command` + queue |
| 5 | `engine/ui/` | input -> commands, scroll input (view state), panels later |
| 6 | `engine/view/` | `Camera`, coordinate conversions, visible range, draw list |
| 7 | `engine/backend_pygame/` | window, surface cache, blitting, events, main loop |

Rules: sim/world never import pygame, engine.view or engine.ui. Input reaches the
sim only as commands. View reads the world, never writes it. Entities cross layers
as integer ids.

## Components
- `AssetCache(fs)`: `tileset()`, `sprite(id)`, loaded once, returns decoded numpy frames.
- `Camera`: world-pixel position, viewport size, clamped to map pixel bounds.
- `view/coords.py`: cell <-> world pixel <-> screen; vertex y = 32·r − H; inverse by
  column search; `visible_cells(camera)` padded by max height.
- `view/draw_list.py`: terrain items for visible cells with the sim tick as animation clock.
- `ui/scroll.py`: arrow keys + screen-edge mouse -> camera velocity.
- `backend_pygame/`: `SurfaceCache`, `Window`, `run()` (accumulator loop), `screenshot()`.
- CLI `python -m engine run <map> [--x --y] [--install]`,
  `python -m engine screenshot <map> <x> <y> <dest.png> [--tick N]` (SDL dummy driver).

## Main loop
```
acc += min(frame_dt, MAX_FRAME)
while acc >= TICK_MS: sim.step(commands.drain()); acc -= TICK_MS
ui.update(dt, events) -> camera
draw(view.build_draw_list(world, camera, sim.tick))
```

## Tests (headless)
Coordinate round-trips (incl. non-zero heights); camera clamping at four edges;
visible range at corners; screenshot vs `render_3d` crop pixel for pixel (differences,
e.g. margin above row 0 and edge padding, documented); AST import-boundary test.
Game-file tests skip without the install.

## Out of scope
Entities, objects/structures drawing, fog, minimap, UI panels, commands beyond the base class.

## Open questions
- Performance of per-cell numpy compositing at full viewport (measure; cache).
