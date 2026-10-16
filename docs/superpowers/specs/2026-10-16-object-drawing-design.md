# Object drawing (G2b): draw list + backend, in the original's order

Next after this: G2c minimap.

## Intent
Draw map objects (section 3) and structures/bridges (section 4) over the terrain in the
order of the original view draw `FUN_00406f43`. The view produces a draw list ("what");
the pygame backend executes it ("how"). Units are not in the world yet; the draw order
leaves their slot.

## Decisions and assumptions (made without further questions)
1. **Names.** "E4" = `python -m allods2 map render MAP DEST --relief --layers
   terrain,objects,structures [--clock N]` (`anim/scene.draw_scene`); it is the pixel
   reference. `graphics-overview.md` has no "how to render a sprite" section; the
   authoritative sources are sprites.md (blit modes), animation.md §4.2/4.3 (placement,
   frames), lighting.md §4-5 (light rows, shadows), map.md part 4 (order).
2. **File layout.** `engine/view/draw_list.py` is renamed `engine/view/drawlist.py`
   (as requested) and holds `build_terrain_items(terrain_view, camera, tick)` (the G1
   function, renamed) and `build_draw_list(world, camera, tick, assets, options)` (sprites
   and overlays). G1 tests/imports are updated. The backend draws terrain items first,
   then the draw list.
3. **Depth key = the exe's scan order, not a numeric sort by height.** CONFIRMED in
   map.md part 4: passes in this order, each pass rows top to bottom, columns right to
   left: (0) structure shadows if the Shadows option is on, (1) flat structures, (2) per
   cell: the non-flat structure's slice of that cell, then the unit (none yet), then the
   map object. Heights and sprite offsets only place pixels; they are not in the key.
   `DrawItem.depth = (pass, row, -col, slot, part)`; `slot` 0 structure / 1 unit / 2 object;
   `part` = bottom-up index of the pieces within a structure cell. Sorting by `depth` is
   stable and total, which makes the list deterministic. REA must confirm or correct the
   details below before the code is written (see "REA tasks").
4. **Culling** is by sprite extent against the viewport (a pure, invisible optimisation).
   The exe's own cell window (visible window plus a 4-7 cell margin) is documented; the
   implementer checks with data that no sprite reaches visibly beyond that margin
   (max extent in cells), and records the result. If one does, the exe window rule is
   applied instead and documented as a quirk.
5. **Parity vs shading.** The exe lights objects/structures with a BRIGHT2 row
   (`object_light_row_lit`, lighting.md §4) and darkens shadows (§5); E4 draws neither.
   `DrawOptions(shadows=True, lit=True, smoothing=True)` default to the game's defaults
   (all options default to 1). Parity tests and goldens use `shadows=False, lit=False`
   (= E4); one extra golden per map checks the fully enabled output as a regression
   (documented as not parity). Light/time of day is the fixed default daylight, like the
   terrain (`daylight(0, False)`).
6. **Team colour remap.** `DrawItem.remap` is a player index into `human.pal` or None.
   Objects and structures use their file palette in E4; REA checks whether the structure
   draw (`+0x28`) applies an owner table. If not, `remap` is always None here and the
   field exists for units.
7. **Time.** Objects: `ObjectSet.frame_at("anim", ..., tick, x=, y=)` (CONFIRMED frame rule
   animation.md §4.3). Structures: `StructureSet.frame_at("intact", 0, tick)` with
   `start=0` (the structure counter starts at 0 and advances per tick, animation.md
   §3.2); destroyed when `hp == 0` (flag bit 0) and not Indestructible. Bridges: piece
   rule §4.2 with `clock = tick`. The Animation option (`animate`) is a build option.
8. **Blit execution.** Opaque `.256` sprites: decoded once by the core to RGBA arrays,
   cached as pygame surfaces (`SpriteCache`, LRU, key `(kind, type_id, source, index,
   mirrored, light_row)`), blitted with `Surface.blit`. The 50 % smoothing overlay
   (`b.256`, blend `half`) and shadows (blend `shadow`, `dst*(16-k)/16`) depend on the
   destination, so they are applied in numpy on the framebuffer rectangle
   (`pygame.surfarray.pixels3d`) using the core's formulas (`Canvas.draw_256_translucent`,
   `lighting.shadow_pixel`) so the result is exact; pygame's own alpha blending is not
   used unless a test shows it equal.

## DrawItem (frozen dataclass, no pygame, in engine/view/drawlist.py)
```
kind: "sprite" | "shadow" | "marker" | "passability" | "depth"   # overlays only on request
entity: int | None          # world id (ints across layers)
sprite: (set_kind, type_id, source)   # set_kind "object"|"structure"|"bridge"; source "main"|"dead"
frame: int                  # index into the sprite file
sx, sy: int                 # screen top-left of the frame, after hotspot and camera
w, h: int                   # frame size (for culling and markers)
mirrored: bool; blend: "opaque"|"half"|"alpha"|"shadow"
light_row: int | None       # BRIGHT2 row for the item (None = file palette, unlit)
shadow: bool                # item is a shadow of `sprite`
shadow_level: int | None    # k, 4/6/8 by time of day (0x6226cc)
remap: int | None
depth: tuple
```
The smoothing overlay is its own item (`blend="half"`, same frame, same depth, part+1)
placed right after the item it smooths, as the game draws main then overlay per piece.

## build_draw_list(world, camera, tick, assets, options)
Reads `world.objects`, `world.heights`, `world.cells`; walks the world's entities (index
by cell for the visible range); never mutates anything. Placement (CONFIRMED animation.md
§4.2/4.3): object anchor `(32X + 16, 32Y + 16 - relief)`, relief = `cell_relief`;
structure pieces at `(32*(X0+c), 32*(Y0 + row - (FH-TH)) - g)`, `g` = `ground_height`
for the footprint `W x TH` (bridges `w x h`); the screen position subtracts the camera.
Assets: `AssetCache` gains `object_set(id)` and `structure_set(type, size)` (moved out of
`anim.scene.Scene`, which then uses them); unknown/missing sprites yield no item (the
game draws nothing) and are counted in the build report of the list.

## Shadows (REA tasks decide the details)
Only with the Shadows option. Shape = the sprite's covered pixels, sheared per
lighting.md §5 (`shadow_shear`, `shadow_row_offsets`), each covered pixel
`dst*(16-k)/16`, `k` from the time of day. Which entity kinds cast shadows (structures per
map.md; objects/units?), their anchor and the level for the second set (`0x626ca8`) are
REA tasks.

## REA tasks (use the mcp__rea__* tools on the GOG allods2.exe; mark CONFIRMED/INFERRED
with routine addresses in map.md / lighting.md / rendering.md)
1. `FUN_00406f43`: the exact pass order, scan direction, the window margin (4-7 cells:
   which numbers for which side), and where object shadows (if any) sit in the order.
2. The shadow draw: callers of `FUN_0045506f` / `FUN_00456021`; which classes have a shadow
   method (vtable `+0x2c`): structures, objects, units; the shadow anchor and shear origin
   (placement of the sheared sprite relative to the unmirrored frame); which
   objects use the lighter level `0x6226d0` / set `0x626ca8`.
3. Whether the structure draw (`+0x28`) and object draw (`+0x14`/`+0x28`) take an owner
   palette, and how `b.256` smoothing interacts with the light row.
4. How the object light row is passed to a structure's pieces (one row per cell?).
Corrections found by REA win over this spec; record them in "Implementation notes" below.

## Debug toggles (UI layer)
`engine/ui/debug.py`: `DebugFlags(passability, markers, depth)`; keys F1/F2/F3 toggle
(handled in the backend event loop, UI state only, never a sim command). The view turns
flags into overlay items: `passability` (tint of blocked cells from `world.block`, walker
mask 0x41), `markers` (footprint cells outline + hotspot cross per entity), `depth` (the
`depth` tuple as text). CLI: `screenshot ... --debug passability,markers,depth`.

## Backend
`engine/backend_pygame/render.py` `draw_frame(surface, caches, terrain_items, items,
camera)`: terrain, then items in list order. `sprites.py`: `SpriteCache`. Fonts for the
depth text via `pygame.font` (backend only).

## CLI
`python -m engine run MAP ...` and `screenshot MAP X Y DEST [--tick N] [--no-shadows]
[--no-light] [--no-objects] [--debug LIST]`. The screenshot X, Y stay world pixels.

## Tests
- Without game files (synthetic world + stub asset sets): determinism (same input, same
  list), sorted by `depth`, never mutates the world (hash before/after), expected order
  for overlapping cases: structure in front of/behind an object by row; same row, columns
  right to left; flat structure under everything; shadow pass before flat; structure slice
  vs object in one cell (slice first); bottom-up parts; culling keeps items whose extent
  overlaps the viewport and drops the others.
- Import boundary: `engine/view` has no pygame (existing test extended).
- With the install (skip without): 3 fixed positions on each of 2 maps (maps 10 and 52;
  positions chosen where trees, a structure and a bridge/water meet, recorded in the test)
  at tick 0, `shadows=False, lit=False`: engine screenshot equals the crop of E4
  (`draw_scene` on `render_3d`) pixel for pixel; one position at tick 20 with `--layers
  terrain,objects --clock 20`.
- Goldens in `tests/golden.json` (new key `"screenshots"`; keep the existing world-hash
  entries): SHA-256 of the RGB bytes for the 6 parity screenshots plus 2 fully-enabled
  (shadows + light) regression shots; `tools/update_golden.py` regenerates them.
- Debug overlay smoke tests (items exist, counts match `world.block` blocked cells in view).

## Docs
`docs/engine/rendering.md`: pipeline (world -> terrain items + draw list -> backend),
depth rule with exe addresses, placement formulas, shadows, lighting, smoothing, blend
execution, culling and measured timing, debug toggles. `docs/engine/architecture.md`
sections 5-6 point to it. map.md / lighting.md updated with REA results. CLAUDE.md:
Status G2b done, Next G2c (minimap). `docs/open-questions.md` updated.

## Out of scope
Units, projectiles, fog, selection, burning cells, day/night cycle (fixed daylight),
the low-memory shadow variants.

## Implementation notes
(filled in by the implementer: REA results, deviations, measured timings)
