# Engine rendering: draw list and backend (G2b, units G3a, interface G3b)

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
(`opaque`, `half`, `shadow`; `alpha` reserved for invisible units), `light_row`, `shadow`, `shadow_level`,
`remap` (units: `(human.pal row, variant)`; None for structures, objects, piles: no owner table, CONFIRMED lighting.md §4),
`depth`, `shear` (16.16), `text` (depth label; `"hotspot"` marks the cross marker).
`DrawList` is a list with `missing` (entities without sprite: the game draws nothing) and
`culled` (cells outside the window). `DrawOptions(shadows, lit, smoothing, animate, objects, units)`
default to the game's defaults (every option is 1); the light is the fixed default daylight
(`daylight(0, False)`) like the terrain.

## 2. Order

`depth = (pass, row, -col, slot, seq, part, sub)`, sorted ascending (stable, total, deterministic).
CONFIRMED order of `FUN_00406f43` (every pass: rows top to bottom, columns right to left):

| pass | content | here |
|---|---|---|
| P0 | structure shadows (Shadows option; bridges none) | yes |
| P1 | flat structures (`Flat`) | yes |
| P2 | corpses, backpacks | backpacks (ground piles) yes, corpses not yet |
| P3 | per cell: (a) non-flat structure slice, (b) ground unit, (c) steam, (d) map object, (e) fire | slots 0, 1, 3 |
| P4 | flyer shadows | yes |
| P5-P6, P8 | projectiles, cell effects, overlays | not yet |
| P7 | flyers | yes |

`slot` 0 structure, 1 unit, 2 steam, 3 object, 4 fire (P2: 0 corpse, 1 backpack); `seq` = the world's stamp order (a
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

## 12. Minimap

Spec: [minimap design](../superpowers/specs/2026-10-16-minimap-design.md) (cheap variant, decided
2026-10-16). Code: `allods2/minimap.py` (image), `engine/view/minimap.py` (geometry, camera
rectangle), `engine/ui/minimap.py` (click/drag), `python -m engine minimap MAP DEST.png`.

| Fact | Where in the exe | |
|---|---|---|
| Generated at load, nothing in the `.alm`; builder | `FUN_004ab96c` (from `FUN_004ab896`) | CONFIRMED |
| Surfaces on the view object: base `+0x60`, fogged copy `+0x64`, shift `k` `+0x68` | same | CONFIRMED |
| Cell colour `table[13 - (v & 0xf)][v >> 4]`, `v = cell & 0x1fff`; table = `graphics\interface\MiniMapData.bmp`, 52 x 14, global `0x626cb0`, path `0x5f2260` | `0x4abb45`-`0x4abc3a` | CONFIRMED |
| Cells `8 <= x < w-8`, `8 <= y < h-8` only | `0x4abb53`, `0x4abb79` | CONFIRMED |
| `k` from `max(w, h)`: `> 0x90` -1, `> 0x50` 0, `> 0x30` 1, else 2; image `((w-16) << k, (h-16) << k)`, for -1 `(w-16) >> 1` with a 2x2 average | `0x4abc44`-`0x4abd82`, `0x4abe65`-`0x4ac01d` | CONFIRMED |
| 80x80 and 144x144 maps give 128x128; 256x256 gives 120x120 | same | CONFIRMED (computed) |
| Base never depends on passability, objects or units; only fog changes it (dirty flag `view+0xdc`, redraw at most every 10 view-clock ticks) | `FUN_004ac414` | CONFIRMED |
| Image centred on panel point (72, 82): `x = 72 - W/2`, `y = 82 - H/2`; panel origin `FUN_004d3a23(this+8)` | `FUN_004ac414` | CONFIRMED |
| Fog: OR of the `0xc000` bits of cells (c,r), (c+1,r), (c,r+1), (c+1,r+1); 0 -> pixel of surface `DAT_00626be0`, `0x8000` -> 50 % blend with it, else base | `FUN_004ac414` | CONFIRMED |
| Minimap objects draw themselves after the image (vtable `+0x34`, args origin, `k`) | `FUN_004ac414` (list `FUN_00420140`) | CONFIRMED |
| Camera rectangle: white 1 px outline from `((view+0x5c) - 8) * s` , `((view+0x60) - 8) * s`, size `(view+0x64, view+0x68) * s - 1`; `/2` for `k = -1` | `FUN_004569a3` call | CONFIRMED |
| Final per-channel pass | `0x4ac030`-`0x4ac413` | not identified |

Engine deviations (DECISION): `k = -1` takes every second pixel; no final pass, no fog; unit dots: section 13;
camera position is `camera / 32` in cells with relief ignored; the panel is the right column's top, flush at
`(W-160, 0)`, image centre at panel point (72, 82) (CONFIRMED, [ui-layout §4](ui-layout.md); replaces the 8 px margin). The image is built once per
`Minimap` (no World hook: the exe's picture never depends on passability or objects);
`invalidate()` is there for terrain edits. Click or drag centres the camera on the cell under the
pointer: view state, not a command. Tests: `tests/test_engine_minimap.py`, goldens
`tests/golden.json["minimaps"]` (maps 10, 20, 52).

## 13. Units, team colours, piles (G3a)

World side: [architecture §9](architecture.md#9-world-state); code `engine/view/drawlist.py`
(`_unit`, `_item`, `unit_position`, `unit_frame`, `unit_remap`, `backpack_frame`). All CONFIRMED by REA
(`FUN_004632a1` draw, `0x464487` shadow, `FUN_0046025d` filing, `0x463093` layer register, `FUN_00406f43`).

| Rule | Value |
|---|---|
| Filing position | `pos - 0x80 + size * 0x80` (1/256 cell, `size` = units.reg `TileSize`); the cell is `>> 8` of it: a 1x1 unit is filed under its own cell, a 2x2 or 3x3 one under the cell of its footprint centre (`cell + 1`). The exe has one slot per cell and layer (the last unit visited wins, order INFERRED = id-map bucket order); the engine draws all, there is no shared cell in the 46 maps |
| Screen position | `px = X * 32 >> 8`, `py = Y * 32 >> 8 - z`; `z` = vertex-bilinear ground height of the footprint (`objects.ground_height(size)`, not the cell relief); sprite top-left = `p - ((CenterX - Width/2) + w/2, (CenterY - Height/2) + h/2)` with the **current** frame's `w, h`; `b.256` overlay the same with its own size, 50 % (Smoothing) |
| Frame | `UnitSet.frame_at(action, facing >> 4, world.tick - action_start_tick)`; `idle` falls back to `stand` for types without `IdlePhases`; the idle counter starts at 0 and advances one per tick for **every** unit, in sight or not (`0x45fa00`, `FUN_0046617c`; the "frozen outside sight" of animation §1.6 concerns structures and objects only) |
| Team colour | `Palette = 0` types: `human.pal` row = `Player.colour` of the owner; `Palette > 0`: `palette<face - 1>.pal` (`Unit.face`, INFERRED mapping); `DrawItem.remap = (row, face - 1)`; the `b` overlay uses the main sprite's table |
| Light | BRIGHT2 row of the cell the unit is filed under (no interpolation); the hovered unit is forced to row 0 (not drawn yet: no cursor) |
| Shadow | like an object's: main `k = 0x6226cc`, `b` `0x6226d0` (Smoothing only); anchor `x = px - anchor - dx`, `dx = trunc(T (h/2 + Height/2 - CenterY))`, `y = py - anchor - z`; current frame, mirrored with the sprite |
| Flyers | `Z != 0` (bat 70, dragon 71, succubus 105; 494 map units): own view class, layer `+0x90`; shadow in **P4** with the *unsheared* blitter at `x + trunc(shear16 / 2000)`, drawn on the ground (`U+0x10` excluded); sprite in **P7** raised by `U+0x10 = 16` (`FLYER_ALTITUDE`, constructor `0x46bfc1`), so flyers cover every ground unit; a flyer and a ground unit on one cell both draw |
| Layers | alive and the fresh corpse (death stage 0, 1) stay in the P3 slot; bones (stage 2-4) move to the corpse layer (P2); stage 5 is not drawn; re-decided every frame. A walker at HP 0 stays at stage 1 for good |
| Not drawn yet | invisibility (effect 0x20: skipped unless the owner is visible to the viewer, else 50 %), stone curse grey table (0x2c), fog `S`, hover row 0, corpses, selection |

**Piles** (`Item`, P2 after corpses, `FUN_00461292`, `0x4611bf`): sprite `graphics/backpack/sprites.256`
(+ `spritesb.256`), frame `min(5, floor(log10(gold)))` (0 when empty; the items' own `+0x1c` is not decoded,
so item-only piles show frame 0), anchor the cell centre, `x = X - w0/2`, `y = Y - h0/2 - relief - 4` with frame-0
size, shadow `dx = trunc(T h0/2)` main + `b` (no Smoothing gate), `b` overlay with Smoothing, cell light row, no owner colour.
Groups on one cell merge into one pile (gold added).

**Depth** is the pass order of §2; units sort by `(pass, filing row, -filing col, slot, seq)`, so inside a
cell structure < unit < object, and a unit behind an object (smaller row) is drawn first. Units do not sort
differently from objects except the pass (flyers: P4 / P7) and the size-aware filing cell.

**Minimap dots** (`FUN_004ac414` -> unit vtable `+0x34` = `0x465f3f`, after the terrain and before the camera
rectangle): a `1 << k` square at `((c - 8) << k, (r - 8) << k)` of the unit's cell `pos >> 8` (k = -1: one pixel at `>> 1`),
colour = palette entry 164 of the owner's `human.pal` row (`allods2.minimap.load_dot_colors`; the exe reads it from the
16-bit table, 5-6-5 rounding not reproduced). Gates: viewer's own units and any unit in sight, not invisible, not corpse
(stage < 2, flag 0x80 clear). The engine has no fog yet, so it draws a dot for every unit (DECISION until fog);
`python -m engine minimap MAP DEST --units`.

**Tests**: `tests/test_engine_unit_draw.py` (synthetic depth, filing cell, flyer layers, animation clock at 30 vs 60 fps
render rate, minimap dots), `tests/test_engine_objects.py` (pixel parity with `map render --relief --layers all` at
4 positions: units, a 2x2 ogre, bats, piles; goldens `["screenshots"]` incl. 4 parity + 2 full unit shots),
`tests/test_engine_units.py` (world). `map render` (E5) follows the same filing, flyer and pile rules.

## 14. Interface, cursor, picking, marker (G3b)

Facts: [ui-layout](ui-layout.md); spec: [interface and selection](../superpowers/specs/2026-10-17-interface-selection-design.md).
Code: `engine/ui/layout.py`, `cursor.py`, `selection.py`; `engine/view/pick.py`, `drawlist.py`;
`engine/backend_pygame/interface.py`, `cursor.py`, `text.py`, `render.py` (`draw_bar`).

- **Window**: black; the viewport (map, `W-160` x `H//32*32`) blits at (0, 0); then the left strips (inside the view,
  at `W-176`), the right column panels (minimap crystal, heads or command bar, info back, 800/1024 extra) at their
  layout rects, the minimap image at its panel point, the info panel texts. Panel graphics are `graphics/interface/*.bmp`
  through `allods2.graphics.bmp`, no colour key. Strip B / bar panel = Heads for no or foreign selection, else CommandBar.
- **Picking**: every drawn unit registers a `PickRect` (type `SelectionX1..Y2` offset by the sprite anchor, ground height
  and flyer altitude, unmirrored: INFERRED) in `DrawList.picks`, in draw order; `pick_at` = last rect meeting the 3x3 box,
  `pick_in_rect` = overlap > 10 px^2 (CONFIRMED, ui-layout §7-8). No pixel test.
- **Marker**: a `bar` `DrawItem` (pass overlay) on the pick rect's top edge for each selected unit (all units with
  Ctrl+H): 4 rows, track `x1+4..x2-4`, grey `0x40/0x80/0x60/0x40` empty, fill dark/bright/mid/dark in green, yellow
  (< max/2) or red (< max/4), fill >= 1 px while hp > 0, 4x4 `Ball.bmp` caps at `x1` and `x2-4` (CONFIRMED geometry and
  colours, ui-layout §9). No mana bar, name or squad number yet; no circle.
- **Info panel** (text via `text.draw_text`, pygame's default font until G3c): the unit's `DescText` centred at
  `(panel.w - 88, 0x1c)`, `HP` label at 0x2c, `cur/max` at (0x73, 0x36), owner name at (6, 0xe0). No portrait.
  Positions CONFIRMED (§10); title source and owner line are DECISIONs.
- **Cursor**: `choose_cursor` (pure) picks arrows / default / select / pickup; `CursorSprites` decodes the frame of
  `load_cursor_set(name).frame_at` (wall-clock ms) and the window blits it last at `mouse - hotspot`; the OS cursor is hidden.
- Tests: `tests/test_engine_{layout,cursor,pick,selection,selection_input,interface}.py`; golden `["interface"]` (map 10,
  640x480, the human unit selected) is tied to the pinned pygame-ce's bundled font.

## Open questions

- Burnt ground (tile bit 0x2000, `DeadObject` frame), fog gates, light-map lights on objects
  (structure `LightRadius`, burning cells), day/night: not drawn; see
  [lighting.md](../mechanics/lighting.md). Starting routine `FUN_00404a2a`.
- Cell effects (CONFIRMED, not drawn yet): `FUN_0040af69` draws spell-area cell sprites keyed by view message
  0x87: wall of fire (bit 3, P3 f, projectile 15, frame `3 + abs(clock/2 + x*y) % 5`), wall of earth (bit 17,
  P3 f, projectile 43), poison cloud (bit 6, P6, projectile 21, frame `abs(clock/2 + x*y) % phases`), at
  `(32 col + 16, mean of the cell's two diagonal heights)`; bit 3 also marks burnt ground. Needs the spell system ([spells §4](../data/spells.md#4-effect-handlers): carriers, shapes, registration `FUN_0055a325`). Blizzard stones and Acid Stream puffs are not cell effects but timed projectile objects (message 0x86, ids 23 / 27, [spells §9b](../data/spells.md#9b-field-carriers-summons-raising-tooltip)).
- Units: invisibility and stone-curse drawing, hover/selection, the exe's visit order when two units share a layer cell,
  the sender of client message 0x74 (flag 0x80, moves a unit to the corpse layer). Starting routine `FUN_004632a1`, `0x415bda`.
- Item-only piles: the item field `+0x1c` (pile frame), see [map.md](../formats/map.md#open-questions).
- Minimap: the final channel pass `0x4ac030`-`0x4ac413`, surface `DAT_00626be0` (fog background), fog gate of the
  dots (do structures draw dots too?). Starting routine `FUN_004ac414`.
- Interface (G3b): hover brightness, structure pick rects, bottom bars and command-bar contents, portraits: see [ui-layout open questions](ui-layout.md#open-questions).
