# Engine rendering: draw list and backend (G2b)

Spec: [object-drawing design](../superpowers/specs/2026-10-16-object-drawing-design.md) (its
"Implementation notes" win). Order, window and shadows are CONFIRMED in
[map.md part 4](../formats/map.md#draw-order-and-placement-structures) and
[lighting.md §4-5](../mechanics/lighting.md); this page says how the engine applies them.

## 1. Pipeline

```
world (objects, heights) --build_terrain_items--> TerrainItem list  --\
world + camera + tick + assets + DrawOptions + DebugFlags            --> backend.draw_frame
                         --build_draw_list--> DrawList of DrawItem  --/   (SurfaceCache, SpriteCache)
```

`engine/view/drawlist.py` (no pygame, reads the world only) answers "what, where, in which
order"; `engine/backend_pygame/{render,sprites}.py` answers "how". `draw_frame(surface, caches,
terrain_items, items, camera)`: black, terrain items (`SurfaceCache`), then the items in list
order. `Caches(terrain, sprites)` bundles the two caches and a debug font.

`DrawItem` (frozen): `kind` (`sprite`, `shadow`, `marker`, `passability`, `depth`), `entity`
(world id), `sprite = (set_kind "object"|"structure"|"bridge", type_id, source "main"|"main_b"|
"dead"|"dead_b")`, `frame`, screen `sx, sy` (top-left of the frame after hotspot and camera;
for a shadow the sheared frame's `x, y` as the exe passes it), `w, h`, `mirrored`, `blend`
(`opaque`, `half`, `shadow`; `alpha` reserved for units), `light_row`, `shadow`, `shadow_level`,
`remap` (always None here: structures and objects take no owner table, CONFIRMED lighting.md §4),
`depth`, `shear` (16.16), `text` (depth label; `"hotspot"` marks the cross marker).
`DrawList` is a list with `missing` (entities without sprite: the game draws nothing) and
`culled` (cells outside the window). `DrawOptions(shadows, lit, smoothing, animate, objects)`
default to the game's defaults (every option is 1); the light is the fixed default daylight
(`daylight(0, False)`) like the terrain.

## 2. Order

`depth = (pass, row, -col, slot, seq, part, sub)`, sorted ascending (stable, total, deterministic).
CONFIRMED order of `FUN_00406f43` (every pass: rows top to bottom, columns right to left):

| pass | content | here |
|---|---|---|
| P0 | structure shadows (Shadows option; bridges none) | yes |
| P1 | flat structures (`Flat`) | yes |
| P2 | corpses, backpacks | not yet |
| P3 | per cell: (a) non-flat structure slice, (b) unit, (c) steam, (d) map object, (e) fire | slots 0, 3 |
| P4-P8 | flyer shadows, projectiles, cell effects, flyers, overlays | not yet |

`slot` 0 structure, 1 unit, 2 steam, 3 object, 4 fire; `seq` = the world's stamp order (a
deterministic tie-break: E4 orders ties by record order); `part` = piece index within a
structure cell, bottom-up; `sub`: structure 0 piece, 1 its `b` overlay; shadows of structures
(P0) 0 main, 1 `b`; object 0 shadow main, 1 shadow `b`, 2 sprite, 3 `b` overlay (a shadow is
drawn right before its sprite, objects in P3). Debug overlays use pass 9.

A structure draws once per footprint cell with the pieces of picture column `c` for that cell
([animation §4.2](../formats/animation.md#42-structures-and-bridges); `anim.scene.piece_cells`):
the top local row also the `FH - TH` rows above the footprint, bottom-up. Heights and offsets
only place pixels, they are not in the key.

## 3. Placement

CONFIRMED formulas of animation.md §4.2/4.3 (relief per cell = mean of the four corner heights
truncated toward 0, cached per array; structure `g` = `ground_height` of the `W x TH` footprint,
bridges `w x h` from the section 4 size kept in `MapObject.size`):

- object: anchor `(32X + 16, 32Y + 16 - relief)`, frame top-left = anchor - `anchor(w, h)` of the
  frame; the `b.256` overlay uses **its own** frame size (36 files differ);
- structure piece: `(32 X0 + dx, 32 Y0 - g + dy)`;
- frame: object `ObjectSet.frame_at("anim"|"still", ..., tick, x=, y=)` (Animation option off: frame
  0); structure `frame_at("intact", 0, tick, start=0)`, destroyed (flag bit 0 or hp 0, not
  Indestructible, has a destroyed block) shows the destroyed pieces; bridges the piece rule
  with `clock = tick`. Burnt ground (tile bit 0x2000, dead object) is not drawn yet.

## 4. Window and culling

The exe draws cells with `-3 <= x - vx <= W + 2` and `-3 <= y - vy <= Hv + 6` (a structure cell
outside draws nothing; an object whose anchor cell is outside is not drawn), `(vx, vy, W, Hv)`
= `view_window(camera)`: the cells the viewport touches, relief ignored (INFERRED mapping of the
exe's window to our camera). On top of it items are culled by extent against the viewport (shadows
widened by the shear spread). **Data check** (`tests/test_engine_objects.py`, install): over every
object frame the largest extent from the anchor is 64 px left/right/down and 100 px up, so an
object anchored just outside the window (112 px to the viewport at 3 cells + half a cell) never
shows, even with relief 127 below (113 px). Structures are gated per footprint cell: only type
139 (FH - TH = 4) reaches up to 31 px into the viewport from a cell 7 rows below it and only with
relief above 96; the exe window rule is applied anyway (it is the game's behaviour).
Pixel parity with E4 holds at all 49 positions probed on maps 10 and 52.

## 5. Shadows (Shadows option)

Each sprite casts a shadow of its covered pixels (frame of the sprite, unmirrored), blended
`dst * (16 - k) / 16` per channel; main `k = 0x6226cc` (4 by day), the `b.256` shape (Smoothing
only) the lighter `k = 0x6226d0` (2). Shear = `shadow_shear(angle)` (16.16, `shadow_row_offsets`);
the shadow of a sprite of height `h` places row `i` `off[i]` px right of `x`. Anchors
([lighting §5](../mechanics/lighting.md#5-shadows-confirmed)):

- object: `x = 32X + 16 - ((CenterX - Width/2) + w0/2) - dx`, `y = 32Y + 16 - ((CenterY -
  Height/2) + h0/2) - relief`, `dx = trunc(tan(beta) (h/2 + Height/2 - CenterY))`, `h` current
  frame height of the main sprite, `w0, h0` = frame **0** of the sprite being shadowed (the exe's
  quirk, reproduced);
- structure piece: `x = 32 cx + trunc(tan(beta) ((FH - r) 32 - ShadowY))`, `y` = the piece's `y`.
  `ShadowY` of 11 records is +20000 and of 11 others -20000; the formula throws that shadow
  thousands of pixels away (INFERRED: "no shadow"); it is culled.

## 6. Light and smoothing

`lit`: every object/structure item carries `light_row = ambient >> 2` (3 by day, 8 at night), the
cell's row of the light map without lights; the sprite colours go through BRIGHT2 row `r` of the
file's palette (`shade_table(pal, 16, BRIGHT2)`, 8-bit arithmetic, 16-bit rounding is not
reproduced). Lights from the light map (structure `LightRadius`, burning cells) are not applied
(fixed daylight). `smoothing`: `b.256` is its own item (`blend half`) right after its sprite, same
row and the **main** file's table, blended `(src >> 1) + (dst >> 1)`. Shadows take no row. With
`lit=False` the file palette is used: that plus `shadows=False` is exactly the E4 reference.

## 7. Backend execution

`SpriteCache` (LRU, key sprite, frame, mirrored, blend, light row, shear): opaque sprites become
RGBA surfaces (alpha 255 where the game writes) copied by `Surface.blit` (exact); `half` and
`shadow` entries are boolean masks (x first) applied in numpy on `surfarray.pixels3d` of the
clipped rectangle with the core's formulas (pygame's alpha blending is not used). A shadow mask
is the sprite mask sheared once per `(frame, shear)`. The surface must not be locked during a
blit, so each numpy item takes and drops its pixel view.

## 8. Debug toggles

`engine/ui/debug.py` `DebugFlags(passability, markers, depth)`; F1/F2/F3 in the event loop (UI state,
never a command), CLI `--debug passability,markers,depth`. The view turns them into items drawn after
everything: `passability` (red tint of blocked cells, mover mask 0x41, `world.block`), `markers`
(footprint cell outlines, hotspot crosses), `depth` (`P<pass> r<row> c<col> s<slot>` at each sprite).

## 9. CLI

`python -m engine run MAP` and `screenshot MAP X Y DEST [--tick N] [--size WxH] [--no-shadows]
[--no-light] [--no-smoothing] [--no-objects] [--debug LIST]`. X, Y stay world pixels.

## 10. Tests and goldens

`tests/test_engine_objects.py`: synthetic order/culling/shadow/blend rules without game files; with
the install, pixel parity with E4 (`map render --relief --layers terrain,objects,structures`) at
`shadows=False, lit=False` on 6 positions (maps 10, 52: forest, shore with rock and camp, two
bridges, village), animated objects at tick 20, and `tests/golden.json["screenshots"]` (SHA-256 of
the 1024 x 768 RGB bytes: the 6 parity shots and 2 fully enabled regression shots; the latter are
NOT parity, there is no reference). Regenerate with `tools/update_golden.py` (positions in its
`PARITY` / `SHOTS`).

## 11. Measured (1024 x 768, SDL dummy, this machine)

| view | items | list build | first frame (cold caches) | warm frame |
|---|---|---|---|---|
| map 10 dense forest, all options | 696 | 5 ms | 0.95 s (mostly terrain cells) | 82 ms |
| map 10 shore, all options | 642 | 5 ms | 0.96 s | 48 ms |
| map 52 village, all options | 426 | 6 ms | 0.90 s | 25 ms |
| map 52 sparse, all options | 36 | 3 ms | 0.87 s | 7 ms |
| map 10 forest, plain (E4 options) | 344 | 4 ms | 0.11 s (terrain warm) | 31 ms |

The numpy blends dominate (about 0.15 ms per shadow or overlay item); a shadow-heavy forest runs
at about 12 frames per second, the game's tick rate is at most 32 per second.

## Open questions

- Window origin: the exe's `(vx, vy)` (`view+0x5c/+0x60`) against our camera with relief (here floor
  of the camera in cells, relief ignored). Starting routine `FUN_00406f43`.
- Structure `ShadowY` = +-20000 (22 records), shadows of destroyed and flat structures (drawn here
  like any structure). Starting routine `FUN_00461890`.
- Burnt ground (tile bit 0x2000, `DeadObject` frame), fog gates, light-map lights on objects
  (structure `LightRadius`, burning cells), day/night: not drawn; see
  [lighting.md](../mechanics/lighting.md). Starting routine `FUN_00404a2a`.
