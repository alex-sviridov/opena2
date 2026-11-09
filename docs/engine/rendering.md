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
| P5-P6 | projectiles, cell effects (fire / earth walls in P3 slot 5, poison clouds after the missiles in P6) | yes ([§ Unit and cell effects](#unit-and-cell-effects)) |
| P8 | overlays | not yet |
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
  with `clock = tick`. Burnt ground (tile bit 0x2000) overlays `dirt.bmp`; an object on a burnt cell with a `DeadObject` draws the dead object's frame 0 (`drawlist._objects`, CONFIRMED `0x408b0f`).

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
blit, so each numpy item takes and drops its pixel view. `SurfaceCache.layer` keeps whole terrain layers (cell, phase, light, x per item), and `_objects` memoises its items per frame state ([architecture](architecture.md#open-questions)); both are pixel-identical to the uncached path.

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
| Minimap objects draw themselves after the image (vtable `+0x34`, args origin, `k`) | `FUN_004ac414` (the view's object map `view+0x9d0`, `FUN_00420140` / `FUN_00420160`) | CONFIRMED. **Draw order of overlapping dots** (CONFIRMED): the map is an MFC `CMap<word id, object>` with 17 buckets and hash `id >> 4` (`0x422420`, `0x4223b0`); a new entry goes to the head of its bucket (`0x4222c0`); the walk visits buckets ascending, each chain head first, so a later walked dot overwrites an earlier one: bucket `(id >> 4) % 17` ascending, inside a bucket the oldest registration last (so on top). Registration: structures (`FUN_004a449c` `0x4a48cc`, id `0x6000 + uid`), then the map units (`0x4a52d8`), then run-time objects. Structures and units share this one walk. Engine `engine/view/objmap.py`, `minimap.draw_dots` |
| Camera rectangle: white 1 px outline from `((view+0x5c) - 8) * s` , `((view+0x60) - 8) * s`, size `(view+0x64, view+0x68) * s - 1`; `/2` for `k = -1` | `FUN_004569a3` call | CONFIRMED |
| Final per-channel pass (part of the builder, not of the draw): per cell block (`1 << k` pixels; k = -1 one pixel per 2 x 2 cells) `L = 0x60 - (sum of the four bytes of the terrain light map `map+0x18` (FUN_004a5dd2 output, `FUN_0041e930`) at (x, y), (x+1, y), (x, y+1), (x+1, y+1)) / 4`, each 5-6-5 channel `c := min(max, (c * L) >> 5)` (flat daylight light 46: L = 50, x 1.56; light 64 = x 1) | `0x4ac030`-`0x4ac413` | CONFIRMED. **Built after the light map exists** (CONFIRMED): the image is rebuilt only by message `0x404` to the minimap window (`FUN_004ab896` -> `FUN_004ab96c`), whose single sender is `FUN_0041d3b9` (`0x41d46b`), and that routine runs `FUN_00474d98`, the full `FUN_004a5dd2(1, 1, 0, 0)`, `FUN_00404910`, `FUN_0047e345` *before* it posts `0x404`; the scenario load calls it with force 1 (`0x41c028`), so the first image already has the light (day/night option off = default daylight). With ShowTimeFlow on the picture is rebuilt at every light step (every 320 ticks), also on the option toggle: the engine builds once (default option off) |
| k = -1 image: average of the 2 x 2 cells' words, `sum((w >> 2) & 0x39e7)` (floor(c / 4) per channel, 565) | `0x4abe65`-`0x4ac01d` | CONFIRMED |
| Fog background `DAT_00626be0` = the panel bitmap (`CrystalR.bmp`) blitted at the panel origin first; the image is drawn over it at `(72 - W/2, 82 - H/2)`; the 0-bit fog blocks copy its pixels at that offset, the `0x8000` blocks blend with the pixel just drawn (the blend `((a >> 1) & M) + ((b >> 1) & M)`, `M = 0x7bef`, works on 5-6-5 words) | `FUN_004ac414` | CONFIRMED |
| Dots: units `0x465f3f` (stage < 2, flag `0x80` clear, not invisible unless player flag 8 = viewer, four tiles at the cell OR `0xc000`); **structures and bridges `0x46213e`** (vtable slot 13 of `0x5cd520`, `0x5cea88`, `0x5ceae0`): rectangle at the object's cell, `TileWidth x TileHeight` cells (bridge: its size), same colour and sight gate, no other gate; rectangles are half open (`FUN_00456348`) and k = -1 halves the position but not the size | | CONFIRMED. Colour of a dot whose owner matches no player record (owner 0, neutral): the builders store the player of key 0 (the section 5 record 1 = the human) as the default owner (`0x4a4934`, `0x4a51ea`), so such a structure is drawn in the human's colour (the engine used to draw none). "Viewer" of the invisibility gate = the client's local player object `view+0x9cc`; the gate is bit 8 of its word for the unit's owner (`FUN_0041e860`), only the viewer's own entry has it ([vision](vision.md)) |

Engine: the image is built like the exe (565 words, 2 x 2 average, light pass with the default-daylight terrain light `allods2.minimap.minimap_light`, `Minimap` computes it once); fog blocks, dot gates and structure dots ([vision §3](vision.md), `draw_structure_dots`, sizes `load_structure_sizes`); unit dots: section 13; dot colours are the 5-6-5 words of the shade table / BMP loader, i.e. **truncated** `c >> (8 - bits)` (CONFIRMED: `FUN_00424c84` for the 24-bit BMP table [bitmaps](../formats/bitmaps.md), `FUN_00425bee` for the shade tables [palettes §5](../formats/palettes.md)), shown with the high bits replicated; dots go through `exe_order`.
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
| Filing position | `pos - 0x80 + size * 0x80` (1/256 cell, `size` = units.reg `TileSize`); the cell is `>> 8` of it: a 1x1 unit is filed under its own cell, a 2x2 or 3x3 one under the cell of its footprint centre (`cell + 1`). The exe has one slot per cell and layer (CONFIRMED: `FUN_0040403b` `0x404187` walks the view's object map and calls vtable `+0x38` = `FUN_00463093` -> `FUN_00460591`, one pointer store per cell of layer array 2 (ground unit, death stage < 2), 3 (flyer) or 4 (bones); the last walked object wins, order = [objmap](../../engine/view/objmap.py)); `_unregistered_units` drops the losers, so two units sharing a cell (simulation 11.4b) look like one |
| Screen position | `px = X * 32 >> 8`, `py = Y * 32 >> 8 - z`; `z` = vertex-bilinear ground height of the footprint (`objects.ground_height(size)`, not the cell relief); sprite top-left = `p - ((CenterX - Width/2) + w/2, (CenterY - Height/2) + h/2)` with the **current** frame's `w, h`; `b.256` overlay the same with its own size, 50 % (Smoothing) |
| Frame | `UnitSet.frame_at(action, facing >> 4, world.tick - action_start_tick)`; `idle` falls back to `stand` for types without `IdlePhases`; the idle counter starts at 0 and advances one per tick for **every** unit, in sight or not (`0x45fa00`, `FUN_0046617c`; the "frozen outside sight" of animation §1.6 concerns structures and objects only) |
| Hero set | party heroes (`xp.is_hero`) are drawn from `graphics/units/heroes|heroes_l/<weapon name>[_]/` picked from the equipment every frame (`FUN_0046a215`, [animation 1.3](../formats/animation.md)): a fighter in no slot-8 armour `heroes_l`, else the armour material's folder, mages `heroes`; dying = `unarmed` / `mage_st`; `engine/herolook.py`; map humans keep their units.reg set |
| Team colour | `Palette = 0` types: `human.pal` row = `Player.colour` of the owner; `Palette > 0`: `palette<face - 1>.pal` (`Unit.face`, INFERRED mapping); `DrawItem.remap = (row, face - 1)`; the `b` overlay uses the main sprite's table |
| Light | BRIGHT2 row of the cell the unit is filed under (no interpolation); the hovered unit is forced to row 0 (not drawn yet: no cursor) |
| Shadow | like an object's: main `k = 0x6226cc`, `b` `0x6226d0` (Smoothing only); anchor `x = px - anchor - dx`, `dx = trunc(T (h/2 + Height/2 - CenterY))`, `y = py - anchor - z`; current frame, mirrored with the sprite |
| Flyers | `Z != 0` (bat 70, dragon 71, succubus 105; 494 map units): own view class, layer `+0x90`; shadow in **P4** with the *unsheared* blitter at `x + trunc(shear16 / 2000)`, drawn on the ground (`U+0x10` excluded); sprite in **P7** raised by `U+0x10 = 16` (`FLYER_ALTITUDE`, constructor `0x46bfc1`), so flyers cover every ground unit; a flyer and a ground unit on one cell both draw |
| Layers | alive and the fresh corpse (death stage 0, 1) stay in the P3 slot; bones (stage 2-4) move to the corpse layer (P2); stage 5 is not drawn; re-decided every frame. A walker at HP 0 stays at stage 1 for good |
| Effects | Invisibility and Stone Curse: [Unit and cell effects](#unit-and-cell-effects) |
| Not drawn yet | corpses' stone state (INFERRED unchanged), selection |

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
16-bit table: truncated to 5-6-5, CONFIRMED). Gates: viewer's own units and any unit in sight, not invisible, not corpse
(stage < 2, flag 0x80 clear). With fog on (J2) a dot needs a seen cell, without fog every unit gets one;
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
- **Info panel** (J1, [ui-layout §11.1](ui-layout.md#111-unit-info-panel-window-7), built): two modes (TAB / the mode button). Picture mode = HumanBackR (strip C HumanBackL) + the 160x240 portrait at (0, 2) of the panel: a paper doll for human units (`.256` layers composited by `Canvas.draw_256`, each
  with its embedded palette, keyed by black) or `graphics/infowindow/<InfoPicture>[face].bmp`; text mode = TextBackR / TextBackL + the font2 rows of the exe (gold labels, sage values, orange headers) placed by the exact measure (`text.draw_text_exact`); the four buttons (book, backpack, mode, disk) in
  both; the empty / multi-selection texts. Code: `engine/ui/info.py` (rows, portrait recipe), `backend_pygame/panels.py` (drawing). No Level row, no owner line, signed HP, Mana "0/0" for non-casters.
- **Command bar** (J1, ui-layout 11.2): CommandBarR (Heads for no / foreign selection), CommandEmpR over the disabled cells (mask `0xef`, Cast by the slot mask), CommandDnR on the pending mode's cell (`engine/ui/bar.py`, `Panels.draw_bar`).
- **Dialogs** (J1, ui-layout 11.4-11.5): `lm.256` frames (corners 48x48, edges tiled, 96x64 centre tiles, an 8 px drop shadow = the same sprites darkened by level 6, cached as one RGBA surface per size), bevel text buttons in font1, message-style text; drawn last, over the panels, before the cursor.
- **Cursor**: `choose_cursor` (pure) picks arrows / default / select / pickup / move / attack / swarm / town / the pending-mode
  cursors (H3 stage B, table in [ui-layout §6](ui-layout.md)); over the minimap image `choose_minimap_cursor` gives the `s*` cursors; `CursorSprites` decodes the frame of
  `load_cursor_set(name).frame_at` (wall-clock ms) and the window blits it last at `mouse - hotspot`; the OS cursor is hidden.
- **Message list** (CONFIRMED `FUN_004021fe` add, `FUN_00402585` ageing, `FUN_0040261a` draw, `FUN_0040212b` rect): a queue of lines (text, colour table, lifetime) wrapped
  to the view width, drawn top-down from (8, 8) of the view (game mode 2; mode 3 (0, 0xdc) with font2) in **font1**, colour table `0x61fa80` (17i grey ramp, white at the top) with the
  drop shadow, `font height + 2` pixels per line; at most `(view height / pitch) / 2` lines (oldest dropped). Only the first line has a clock (`age += dt`, removed when `age > its lifetime`,
  then `age := 0`), so a later message lives its own time after the earlier one is gone. Lifetimes: level-up lines 3000 ms ("No way" also 3000 ms but **only with `-trace`**, [ui-layout §11.5](ui-layout.md#115-on-screen-messages)), option toggles (formation `0x61+`, retreat `0x5e+`,
  Show Health `0x64/0x65`, Flying damage `0x66/0x67`) **2000 ms** (`push 0x7d0`). Engine: `engine.ui.MessageLine` (queue, `lines(now)`, `entries(now)` with the colour slot: system = `highlight`, log = `normal`), `Interface.draw(..., message=entries)`, `interface.message_line`; sources in [ui-layout 11.5](ui-layout.md#115-on-screen-messages) (pickups: `engine/ui/messages.py`).
  No click marker (CONFIRMED absent).
- Tests: `tests/test_engine_{layout,cursor,pick,selection,selection_input,interface,orders_ui}.py`, `test_engine_ui_{widgets,info,modal,screens}.py`; goldens `["interface"]` (map 10,
  640x480, the first human unit selected, the real panel) and `["ui"]` (the J1 scenarios): all text is drawn with the game's fonts, so they no longer depend on the pinned pygame-ce font (only on the interface art and font data).

## Unit and cell effects

CONFIRMED (`FUN_004632a1` unit draw, `FUN_00464487` unit shadow, `FUN_00460d4b`, `FUN_0040af69`, `FUN_0041c18c`; the draw list builds them in `_unit` /
`_cell_effects`). The client keeps a list of effect ids at the view unit (`unit+0x130`, u32 `id << 16 | 0xffff`; added by message 0x88 `FUN_005044ba`
from the server's effect attach, or by the projectile tick `FUN_0046c1d0` when a hit sprite lands, removed by 0x89 `FUN_00504498`).
`FUN_00460d4b(id)` is its only reader, and every caller (draw, shadow, minimap dots, hover) asks for **0x20 (Invisibility)** or **0x2c (Stone Curse)**:
no other unit effect (Bless, Curse, Poison, Haste, Shield, ...) changes how the unit is drawn, and **they show no sprite at all** ([Status effects](#status-effects-k9) below).
Engine: `Unit.effect_mask` bit 12 / 18 (or `Unit.hidden`) stands for the list entry (no client delay).

| Effect | Drawing |
|---|---|
| Invisibility (0x20) | the owner is not the viewer (`FUN_0041e860` = player flag 8): sprite, `b` overlay, both shadows and the pick rect are skipped. The viewer's own unit: main sprite through the 50 % blit (vtable `+0x34`, `blend = "half"`; the `b` overlay stays 50 %), main shadow at the lighter level `0x6226d0` (k2), **no `b` shadow** |
| Stone Curse (0x2c), death stage <= 2 (`0x463b5c`: `jg` skips above 2; corpses of stage 1 and the first bones included, the effect pass runs for dying units) | frame index = the facing alone (`(facing - 8) & 15`, mirrored when `Flip`): the unit stands frozen at phase 0 of its action; palette = the 16-level **GRAY** table of the unit's palette (`DrawItem.gray`, `shade_table(..., GRAY)`, no tint, same light row / hover row 0; unlit = row 8) for the sprite and the `b` overlay; the shadow uses the frozen frame. Engine: living units only (corpses INFERRED unchanged) |

**Cell effects** (`FUN_0040af69(x, y, flags, mode)`, called from the cell loops at `0x4095d0` mode 1 (pass 3, after the cell's fire) and `0x409b07` mode 0 (pass 6, rows
0..Hv+3, columns 0..W-1); both need the cell's four tile words OR `0xc000`): `flags` = the view's per-cell dword (`FUN_0041c18c`, message 0x87: bit `1 << spell` set / cleared
over a bit mask of cells); `x = 32 col + 16`, `y = (+0xb8 + +0xbc) / 2` (min top edge + max bottom edge of the view vertex table, [terrain](../formats/terrain.md), C halving), both view-relative
(cell origin `vx, vy` = camera `// 32`); `n = |clock / 2 + x * y|`:

| Bit (spell) | Projectile id / sprite | Frame | Pass |
|---|---|---|---|
| 3 Wall of Fire | 15 `firewall` (128x128) | `3 + n % 5` | 3, slot 5 (after the cell's other entities), mode 1 only |
| 17 Wall of Earth | 43 `wall` (32x64) | `n % Phases` (= 0) | 3, mode 1, after the fire |
| 6 Poison Cloud | 21 `poison` (64x64) | `n % Phases` (15) | 6, after the missiles, mode 0 only |

The sprite is the record's `Width x Height` box centred on `(x, y)` (top-left `x - W/2, y - H/2`), `.16a` alpha blit, no light row. Engine: the flags come from the server's cell slots
(`World.cell_fx` slot 0 / 3 / 2, [effects 6.4](effects.md#64-cell-effect-slots)), clock = tick (CONFIRMED: `view+0xa88` is incremented once per server step by the view's message `0x401` handler `FUN_0040bcd8`, which `FUN_00488aa1` posts after each `FUN_004f08c0` step, `0x488b4a`; the fog cadence uses the same counter). Light (15) and Darkness (14) set / clear the light
vertex values (`0x50` / 0) of the cell and are not sprites. **Burnt ground** (CONFIRMED `0x41c390`-`0x41c455`): the first flag of spell 3 on a cell sets tile bit `0x2000` and never clears it; the terrain draw (`FUN_00404e0e` `0x405041`, ignored on water) overlays `dirt.bmp` variant `(x + 5 y) & 3` ([terrain](../formats/terrain.md)). Engine: `World.scorch` (called when a Wall of Fire carrier stamps a cell, `effects._stamp_cell`) sets the bit in `World.cells` (client state; the block layer reads `terrain`) and bumps `World.cells_version`, which drops the terrain surface cache. Per-cell registration: **one pointer per cell and layer** (`FUN_00460591`: ground units and bodies of stage < 2, flyers, bones of stage >= 2 or unit flag `0x80` in `FUN_00463093`), registered by walking the object map in hash order ([objmap](../../engine/view/objmap.py), minimap row above), so of two objects of one layer on one cell only the last walked is drawn and pickable (`drawlist._unregistered_units`; shadows INFERRED to follow). Unit flag `0x80` is set on every map-loaded client unit (`0x4a52f1`) and by client message `0x74`, cleared by `0x69`; the sender is `FUN_005053a8(.., flag, ..)` (type `0x69 + 0xb * (flag != 0)`), called by `FUN_005102a3` (unit leaves the map, `+0x4c |= 8`: `0x74`), `FUN_00510318` / `FUN_005103ae` (back on the map: `0x69`), the server start `FUN_004f1d9c` (`0x4f226c`) and the per-player message filter `FUN_005039e2`; the senders are all `FUN_005053a8(creature, off_map, player)`: **0x74 (set) is sent when the creature's `+0x4c & 8` is set** (`FUN_005102a3`, and the tail of the general creature state sender `FUN_00502019`
after it has sent its state to a player: `FUN_005053a8(c, (+0x4c & 8) != 0, player)` when the creature is off the map or the mask bit `0x40000000` is set), **0x69 (clear) otherwise**, so the
clear at the mission start is that same tail: the entering player's full-state send (`FUN_004f1d9c` `0x4f21fb`: `FUN_00502019(hero, 0, 0xffffffff, ...)`, which loops over the players) and the per-creature state
sends of the creature pass (`FUN_0052b459` calls it every step; mask bit `0x40000000` is raised by `FUN_005053a8` itself for a player not yet allowed to see the creature) ([CONFIRMED] sender mechanism). **`FUN_0052be01` is not a sender** (CONFIRMED `0x52be01`-`0x52be68`): `this` = a creature list, `param = player`; for every element it does `word[elem+0x18] &= ~word[player+0x30]` (clears the entering player's mask bit; no message). `FUN_004f1d9c` calls it three times (`0x4f213a` on the creature manager `0x68d2dc`, `0x4f215e` on `[[this+0x7c]+0xc]`, and `0x4f218d` on each player's unit list `+0x24`, around `FUN_0052ada6` on `[[this+0x7c]+8]`), so no state mask is sent for map-loaded monsters there: they get their first state (and the `0x69`/`0x74` tail) from the full-state send `0x4f21fb` and the per-step creature pass. The meaning of the `+0x18` word is INFERRED (a per-player flag mask of the object). The engine places every unit at load and has no flag `0x80`. Tests: `tests/test_engine_unit_fx_draw.py`.

## Status effects (K9)

**The original draws no status effect except Invisibility and Stone Curse. CONFIRMED (REA), so the engine draws none either.**

- *The client effect list has no drawing reader besides the two.* `FUN_00460d4b` (the list search) has seven callers: the map draw `0x406f43`, the message loop `0x40d9b2` (messages `0x88` add `id << 16 | 0xffff` at `0x414d48`, `0x89` remove at `0x414e28`), the unit draw `0x4632a1`, the unit shadow `0x464487`, the pick `0x4653a5`, the minimap dots `0x465f3f` and the projectile tick `0x46c1d0`; every caller asks for `0x20` (Invisibility) or `0x2c` (Stone Curse). No caller is in the UI, so **no status icon exists in the info panel** (the engine's `ui/info.py` reads no effect, tested).
- *The spell sprites that look like status overlays never live.* Projectile ids `2n + 8` with a sprite (`p_fire` 16, `poison_d` 20, `p_water` 24, `p_air` 34, `p_earth` 46, `bless` 48, `shield` 62, `Curse` 64, ...) are made by the cast action `FUN_0046707e` (at the caster's ShootDelay tick) with the lifetime `obj+0xa8` of its switch: `10 / 0x12 / 0x28` -> `dist / 200`, `0xc` -> `dist / 0x180`, `0x1c / 0x1e` -> 13, `0x36` -> 21, `0x38 / 0x3c` -> 1, **every other id -> 0**. `FUN_0046c1d0` removes an object whose `+0xa8` is 0 on entry, and the view step ticks the unit list first and the projectile list second (`0x40bf30`, the vtable `+0x3c` call at `0x40bf7f`), so the object made in a unit's tick is removed in the same step, **before any draw**. The hit-sprite cases of the tick (`0x10 0x14 0x18 0x22 0x2c 0x2e 0x30 0x32 0x3e 0x40 0x42`: follow the target, phase `age`, add the effect) never run past that test. So Bless, Curse, Haste, Slow, Shield, the four protections, Poison (the cast), Stone Curse and Invisibility show **only the caster's cast animation** and the cast sound `500 + id`; the effect list entry (and so Invisibility / Stone Curse) comes from message `0x88`.
- *Lifetime-1 ids:* Heal `0x38` draws nothing (`FUN_0046cb7b` case `0x38`), Drain Life `0x3c` (sprite 60 `Drain`, 12 x 12) draws frame 1 at the target's footprint centre for one step; both built ([Arrows and shots](#arrows-and-shots-k9) `Flash`). Teleport `0x36` is the long one (21 steps, two copies).
- Engine: `Unit.effect_mask` bits 12 / 18 (Invisibility, Stone Curse) as above; every other bit draws exactly like no effect (`tests/test_engine_arrows.py::test_every_other_status_effect_draws_exactly_like_no_effect`, all 27 bits).

## Arrows and shots (K9)

The shooters' projectiles are client objects (`obj+0x24` = projectile id; class `0x5d1178`'s sibling `FUN_0046c0fa`), made by the shoot action and never seen by the server (the server's hit lands `windup + (dist * 256 + 128) / 200` after the swing start, [combat §3](combat.md)). Engine: `World.arrows` (`Arrow`, **client only, not dumped**, so every world-dump hash is unchanged), `effects.spawn_arrow` / `arrow_system`, `drawlist._arrows`.

| Fact | Routine | Tag |
|---|---|---|
| Who: unit types with `Projectile != 0` in `units.reg` (14 / 93-96 -> 1, 15 / 86-88 / heroes `xbowman` -> 2, 65 / 101 -> 3, 79 -> 4, 26 -> 5, 27 -> 6, 70 / 105 -> 7); the ranged swing (message `0x72`, range > 1) starts the client's shoot action (action 7) | `0x4133b3`, [animation 2.4](../formats/animation.md) | CONFIRMED |
| When: the action's tick `ShootDelay` (`UnitSet.attack_events("shoot")`: 21 / 9 / 22 / 10 / 0 / 0 / 2 / 6; a delay past the 25-tick sequence never fires); the routine returns making nothing when the target id (`+0x8e`, the id `+4` of the attacker's target object, `FUN_00504155`) is not in `view+0x9d0`. **That table holds units and structures** (builder `0x4a4880`/`0x4a48d2` adds the structure view `0x6000 + uid` to it, `0x82` looks structures up there, `FUN_0040403b` runs `FUN_0046025d` on every object of it each frame), so a structure target gets an arrow: lifetime from its `+8 / +0xc` (anchor cell centre), aim at `+0x5c / +0x60` = `pos - 0x80 + size * 0x80` with `size` = TileWidth / TileHeight (vtable `+0x20` `0x4620fc` reads structures.reg `+0x10`), altitude 0 | `FUN_00466e18` `0x466e18` | CONFIRMED (K9 follow-up) |
| Start: the unit's position `+8 / +0xc` (**not** `+0x5c`: the cast action's `FUN_0046707e` uses the footprint centre, the shoot action does not, asm `0x466f18`) `+ (ShootOffset[k] - Center) * 8` per axis (1 px = 8 units), `k = (direction - 8) & 14` (the 8 direction pairs of the table), altitude `+0x10` = 0. The point is the sprite's pixel offset applied in the **ground plane** (the iso-lite view maps world y to screen y), so the arrow leaves the hands | `0x466e9d`-`0x466f4f`; same formula as the bolt (`effects.shoot_origin`) | CONFIRMED |
| Lifetime `+0xa8` = `trunc(sqrt(dx^2 + dy^2)) / 200` of the **unit positions** `+8 / +0xc` (1/256 cell; 0 under 0.78 cell: the object is removed unseen); homing flag `+0x8c = 1`, age `+0x9c = 0` | `0x466fa1`-`0x466fdb` | CONFIRMED |
| Step (`FUN_0046c1d0`, default case, once per view step after the units): remove when `+0xa8 == 0` on entry; else target `T` = the target's footprint centre `(+0x5c, +0x60)` and altitude `+0x10` (read **every step**: a moving target is followed); `+0x8d` = `FUN_004608de(T)`; step = `(T - p) / +0xa8` per axis (C division); age + 1; `p += step`; phase `(age / 2) mod Phases`; `+0xa8 -= 1`. The last step lands exactly on `T`; the object stays one more step, then goes | `0x46c1d0` | CONFIRMED |
| Facing: `FUN_004608de(x, y)` on the object: `a = |dx|, b = |dy|`; code 0 if `a >= 4b`, 1 if `3a >= 4b`, 4 if `b >= 4a`, 3 if `3b >= 4a`, else 2; `dy > 0`: `dx > 0` ? code + 4 : 12 - code; `dy <= 0`: `dx < 0` ? code + 12 : 4 - code; `& 15`. 0 north, 4 east, 8 south, 12 west (`direction16`, also used for the spell missiles: the old rounded `atan2` was INFERRED) | `0x4608de` | CONFIRMED |
| Frame: `d = (facing - 8) & 15`, mirrored when the record's `Flip` and `d > 8` (`d := 16 - d`; ids 1-7 have `Flip 0`), frame `phase + Phases * d`, or `phase` when `RotationPhases == 1` (id 4, the sling stone). Data: ids 1-3 are 16 facings, no alpha, no palette (`projectiles.pal`); 5-6 (catapult stones) palette 1: opaque + the `b.256` half overlay; 4 palette 1, one picture; 7 below | `FUN_0046cb7b` `0x46cb7b` | CONFIRMED |
| Screen anchor: `x = obj+0x2c >> 3`, `y = obj+0x30 >> 3` (world units / 8), the sprite's top-left is that point minus `Width / 2`, `Height / 2` minus the ground relief `+0x6c` minus the altitude `+0x10`: **no chest height, no arc, no shadow** | `FUN_0046025d` `0x46025d`, `0x46cb7b` | CONFIRMED |
| Impact: **nothing is drawn** (no stuck arrow, no spark): the object is only removed; the hit is the server's damage message and the floating number | `0x46c1d0` has no hit case for ids 1-7 | CONFIRMED |
| Id 7 (Sonic Bat, Succubus): no sprite; `FUN_004a6b4b(x, y - relief - z)` bends the already drawn pixels around the anchor ([animation 4.5](../formats/animation.md)): a `"lens"` draw item, applied in draw order in `draw_items` (`allods2/anim/lens.py` `apply_lens`), clipped to the viewport like the exe's redraw rectangle (below) | `0x46cb7b` case 7 | CONFIRMED |

**The spell flights use the same objects** (K9 follow-up, CONFIRMED `FUN_0046707e`): a unit-target cast of Fire Arrow (id 10), Fire Ball (12), Ice Missile (18) or Diamond Dust (40) makes a client `Arrow` (`spell=True`) on the cast action's ShootDelay tick (`effects.spawn_cast_fx` from `spells.cast_start`; the first tick of the action is the cast start), **independent of the server's carrier** (which keeps its own release time and flight for the damage). Lifetime `trunc(dist / 200)` (Fire Ball `/ 0x180`) with `dist` from the caster's `+8` to the target's footprint centre `+0x5c`; start = the cast action's `shoot_origin` (footprint centre, ShootOffset point, altitude 0; `MISSILE_Z` is gone); age 0 at creation (the old INFERRED age -1 of carriers is wrong for these: the first drawn age is 1); facing `direction16` from the position before each step; the trail of ids 10 / 12 is the last 6 pre-move positions (`Arrow.trail`, `FUN_0046c1d0` after the switch); the missile light follows the sprite. The target must exist at the spawn tick; a hidden caster (a script's trap) has no view, so **its Fire Arrow is invisible** (damage only). All other cast ids have lifetime 0 (Status effects above). The server carrier is drawn only in the cell form (`Carrier.target is None`, a cell cast: INFERRED, the exe makes that projectile from message `0x8b`, which this engine does not model separately). `Carrier.start / flight / aim` stay as the dumped record.

**Sampling time** (CONFIRMED `FUN_0046617c`, K9 follow-up): the spawn routines read the shooter's position and facing at the ShootDelay tick; the engine's `arrow_system` does the same, the bolts and the missile carriers sample them at the cast start / release, which is exact because the cast and shoot actions never change the unit's position or facing ([effects §11](effects.md)).

**One-shot cast sprites** (`World.flashes`, `Flash`, `effects.spawn_cast_fx`, `drawlist._flashes`): Teleport (spell 23, id `0x36`, record 54 `teleport` 96 x 96, 21 phases): two objects made at tick 0 of the cast action (`0x36` fires at once, `FUN_0046707e` + the copy constructor `0x46c154`), at the caster's `shoot_origin(table=False)` and the destination cell centre, frame `age - 1`, 21 steps; Drain Life (spell 26, id `0x3c`): frame 1 on the target for one step at ShootDelay. Both `.16a` alpha, altitude 0.

**Draw order**: P6 (`PASS_PROJECTILE`) beside the spell missiles, one item per object at its cell row (`_arrows`, `_flashes`), after units and before the cell effects of that pass; no fog gate (the projectile list calls `FUN_0046cb7b` with none, as for explosions).

**Tests**: `tests/test_engine_arrows.py` (synthetic: the 16 direction codes and band edges, all 16 facings -> frames, spawn / step / landing / removal, a moving target, close shots and missing units make no arrow, no shadow, the palette overlay, the lens item and its backend application, Teleport / Drain Life lifetimes and phases, 27 status bits draw like no effect), `tests/test_engine_arrows_maps.py` (map 73 with four shooters: arrows appear, the world dump hash is identical with the arrow spawn switched off, screenshot goldens `golden.json["arrows"]` of two frames of a volley, regenerate with `tools/update_golden.py --only arrows`).

**VERIFY IN GAME** (compare with the original by eye; none of these could be checked without the running game, all are decisions of the exe's code that the engine follows):
1. An archer volley (map 73 / 90): the arrow's start point (hands, `ShootOffset`) and that it flies in the ground plane with no arc; the arrow vanishing on the last step with no impact drawing.
2. Shooting at a **structure**: the arrow flies to the footprint centre of the building (CONFIRMED path, never seen in the original).
3. A poisoned / blessed / hasted / shielded unit: nothing on the unit except the caster's cast animation (CONFIRMED by the lifetime-0 chain; the only creators of a projectile object, the callers of the constructor `FUN_0046c0fa` (REA), are the message loop `0x40d9b2` (the cell / point / hidden-caster forms `0x86` odd id, `0x8b`, `0x8c`, whose lifetime is in the message: the server sends the flight ticks of missile spells and 22 for the Fire Ball impact, 0 for the rest), the arrow `0x466e18`, the cast action `0x46707e` and the savegame loader `0x48c8a3`).
4. An invisible unit: the viewer's own is 50 %, the enemy's absent (already built).
5. A Sonic Bat's lens: radius 19, anchor, that the bulge moves with the missile. The clip is answered (K9 follow-up): `FUN_004a6b4b` tests every target pixel and every source pixel with `PtInRect` (`0x41e3d0`, user32, half-open) against a copy (`FUN_0045337c`, `CopyRect` of the global clip rect `0x61b5a0`) of the clip set by `SetClipRect` `FUN_0045332a(view+0xf4)` at `0x40960c`, just before the projectile list. `view+0xf4` is the view's accumulated redraw rectangle: every projectile tick (`FUN_0046c1d0` `0x46c230`-`0x46c242`) merges its own box `(x - 64 .. x + 96 aligned to 32, y - relief - 64 .. + 64)` into it, so the lens (radius 19 around `(x, y - relief)`) always lies inside it and is cut only by the viewport edge, which is what the engine's frame bounds do (`apply_lens`, half-open, tested). Only difference left: a lens centred within 19 px of the viewport edge could read a source pixel from the screen buffer outside the viewport (panel pixels of the previous frame) where the engine skips it (INFERRED, a few pixels at the border).
6. A moving target: the arrow turns toward it every step (facing from the pre-step position, CONFIRMED). The big-unit question is answered (K9 follow-up): `FUN_0046025d` computes `+0x5c / +0x60 = pos - 0x80 + size * 0x80` and both unit view classes (vtables `0x5cd5d0`, `0x5cd660`) return units.reg `TileSize` for `size` on both axes (slots `+0x20` / `+0x24` = `0x4631ce` / `0x4631f2`, record `+0xf0`; 2 for Troll, Ogre, Catapult, 3 for the Dragon), so the engine's footprint centre is exact. The old code read a `Unit.size` attribute that does not exist (always 1): fixed (`effects.tile_size`, `lights.tile_size`).
7. Teleport's two flashes (a scripted cast; `Teleport` of the monsters is not built).

## Structure pick rects and dynamic lights (CONFIRMED, engine `drawlist.pick_cell`, `lights.py`)

**Pick rect registration** is in the cell scan of `FUN_00406f43`: `0x408068` for Flat structures (the flat pass), `0x4086b7` for the others (`FUN_00404d99` appends the rect and the object id; `+0x30` of
vtable `0x5cd520`, `0x461b2b`, is the structure's HP bar, not the rect). Both test the visibility state `obj+0x7c` (`FUN_0041eb60`) `== 0` (draw: `< 2`); **no death test**, so a destroyed structure and a Flat one
stay pickable (the hover loop `FUN_004180c6` skips only Indestructible and not Usable). The rect is registered **once per cell of the structure's box** `x .. x + W - 1`, `y .. y + TH - 1`
(`obj+0x40..+0x4c` from `FUN_0046025d`, clipped to the drawn window `-3 .. W + 2`, `-3 .. Hv + 6`; `FUN_00460591` kind 1 fills one array slot per cell), in the cell order of the scan (rows ascending, x descending), so the
copy that matters for the order against units is the **last** one: the clipped box's smallest x in its largest y row (`drawlist.pick_cell`; a Flat structure registers in the flat pass, before every cell pass). Rect offset: see
[ui-layout 7](ui-layout.md#7-picking).

**Dynamic lights** (`FUN_0040403b`, `FUN_00404a2a`, [lighting 3-4](../mechanics/lighting.md)): `engine/view/lights.py` builds the light map each frame from structures with `LightRadius` (5 types: Tower 1/2, Well 2/3, Campfire;
vertices `x .. x + W`, `y .. y + TH`, value by `LightPulse` and the tick) and missile carriers (ids 10 / 18 / 40 radius 0, 12 radius 1, value 16, at the missile's cell); `DrawList.lights`. The cell rows
(`FUN_00404a2a` step 3) go to structures (per footprint cell), map objects and units (filing cell); `build_terrain_items(lights=)` gives lit cells `TerrainItem.lit` = min(terrain light, light) per corner (the surface cache keys on it).
`DrawOptions.lights` (the Lighting option) is on by default but needs `lit`, so the parity modes are unchanged; the only golden that moved is `full-52-village` (towers and a well in view). Later sources overwrite earlier
ones (order INFERRED: structures, then missiles). **Light / Darkness cell flags** (`FUN_0041c18c`): setting writes 0 / `0x50` into the *terrain* light of the cell's four vertices and does **not** call `FUN_004a5dd2`
(CONFIRMED: the write survives); clearing calls `FUN_004a5dd2(x, y, 2, 2)` for the same four vertices (a neighbour's write on a shared vertex is lost with it), and a day/night recompute (whole map) drops all of them
(`World.light_write`, `TerrainView.light`).

## Open questions

- Fire explosion (projectile 13, built, `engine/sim/effects.py` `spawn_explosion` / `explosion_system`, `World.explosions`, `World.burn_fx`, `lights.explosion_phases`, `drawlist._explosions`). CONFIRMED: the Fire Ball area carrier's first visit `FUN_00518833` calls `FUN_005045a5(c, 1)` which sends message 0x86 (cell form, handler `0x414f00`-`0x4151c1`: projectile id msg+0xc, cell msg+0xd/+0xe at `cell * 256 + 128`, `+0xa8` = lifetime u16 msg+0xf = `0x16` = 22, age -1, z 0, cast sound `500 + id`). The tick `FUN_0046c1d0` case 0xd: age +1 per tick, phase `+0x74` = `(age / 2) mod Phases` (record 13: Phases 11, RotationPhases 1, A16 1, 128 x 128), so the light table `+0x74` 0..10 of `FUN_0046d0ef` is walked once over ages 0-21; at age 4 each of the 3 x 3 cells without tile bit `0x2000` is `SetAt` (counter 0) into the burning list when it holds a map object with `DeadObject != -1` or is water (tile `& 0x1fff >> 6` in 8..11), at age 8 bit `0x2000` is set on every cell that is not water or holds an object; removed when `+0xa8` is 0 on entry (age 22). Steam therefore starts at tick `born + 4`, lasts counter < 18; the list entry 22. INFERRED: the carrier's id `+0xe` is 13 (`2n + 9`); the age-0 tick (same tick as the carrier's visit) and the order of the client tick against the server step. The explosion sprite is drawn in P6 beside the missiles (`.16a` alpha, centred, no z).
- Lightning / prismatic spray bolts (28 / 30): built (`World.bolts`, `lights.bolt_*`, `drawlist._bolts`), CONFIRMED chain, messages, lifetime, phase table, sprite frames and light formula in [effects §11](effects.md#11-prismatic-spray-chain-and-the-lightning--spray-bolts-confirmed-unless-tagged-engine-spellsspray_chain-aispray_targets-effectsspawn_bolt-lightsbolt_); the exact polyline, the ShootDelay spawn tick and the ShootOffset origin are CONFIRMED there too. Built also: burning cells from a Wall of Fire flag on a cell whose object has a `DeadObject` (`World.burn_start`, `lights.light_map`); their fire sprite is drawn (see next item).
- Burning trees (CONFIRMED, built): the client never replaces the object (CONFIRMED `FUN_0041c18c`: it only adds the list entry and sets the tile bit); no server-side replacement or other message was found (INFERRED). The flag sets tile bit `0x2000` at once; the object draw (`FUN_00406f43` `0x408b0f` / `0x408c10`) then swaps the picture to frame 0 of the `DeadObject`'s file (`objects.reg +0x44`; the charred `<tree>\dead\sprites`, Index ignored; anchor, `Width`/`Height` stay the original record's) from that frame on, and the object keeps its id, cell, block and pick (nothing is created or removed). The burning-list entry `{cell, 0}` (only if the bit was clear and `DeadObject != -1`) draws the `firewall` fire sprite over it for 22 view steps and lights it ([animation §4.6](../formats/animation.md#46-burning-cells)); the burnt picture is permanent. The `fire\f*` objects (IDs 1, 4, 7, ...) are ordinary records with the same DeadObject; no code special-cases them (INFERRED: unused by maps). `hydra` / `bracelet` data: irrelevant. Drawn (`drawlist._burning_sprites`): the list's `firewall` fire (projectile 15, frame `counter >> 1`, slot 4 after the object, `0x409406`) and, on a water cell (tile `& 0x1fff >> 6` in 8..11) while counter < 18, `steam` (projectile 8, slot 2 before the object, `0x40883f`-`0x40895c`), both centred on `(32 X + 16, 32 Y + 16 - relief)` by the record's Width x Height, `.16a` alpha. Gates (CONFIRMED, `FUN_00406f43`): steam tests the Lighting option (`cmp [0x5f17f0],0` at `0x40883f`, off = no steam); the fire block sits inside the map-object gate (`0x408981` and `0x408a77` jump past it when the cell's object byte is 0 or `FUN_0040b117` = 1, i.e. every fog vertex of the object's box is level 16), so a burning water cell without an object shows steam only; neither block, nor the cell-effect/explosion/bolt sprites, tests the tile fog bits (`0xc000` words are read only for the object's burnt-dead swap `0x408afc` and the terrain `0x409547`). The projectile list (`view+0x9ec`, P5 `0x40984e`-`0x4098a8`) calls `FUN_0046cb7b` with no fog test (no `0xc000` or light-array read in it): explosion and bolt sprites draw in fog and unexplored cells, only the final fog pass darkens them. The `FUN_0040b117` black-box skip for the fire is not modelled (INFERRED: invisible, except a fire sprite larger than the object box poking into a lit cell). The Wall of Fire flag path (`0x41c390`-`0x41c403`: bit `0x2000` clear, object byte non-zero, `DeadObject != -1`) never queues a water cell, so steam comes from the fire explosion's age-4 queue (above).
- Item-only piles: the item field `+0x1c` (pile frame), see [map.md](../formats/map.md#open-questions).
- Interface (G3b): structure pick rects, bottom bars and command-bar contents, portraits: see [ui-layout open questions](ui-layout.md#open-questions).
