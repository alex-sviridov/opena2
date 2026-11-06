# Lighting and time of day

Code: `allods2/graphics/lighting.py` (palette side:
`allods2/graphics/palette.py`). Checked in REA pseudocode and, for
floating point, the x87 assembly.

No per-pixel lighting: a light value is a **row** in a shade table
([palettes §5](../formats/palettes.md)), row 0 brightest. Terrain:
BRIGHT32, 96 rows, `(96 − r)/32` (r 64 = ×1). Units, structures,
objects: BRIGHT2, 16 rows, `2(16 − r)/16` (r 8 = ×1).

## 1. Time of day (`FUN_00474d98`), CONFIRMED

Game time `t` in minutes (`FUN_0041d3b9` passes `(clock >> 4) + 360`: a
game starts at 06:00); `h = (t / 60) mod 24`, `m = t mod 120`, integer:

| Hours | Tint R, G, B (0x6226c0..a) | Ambient (0x6226c4) | Diffuse (0x6226c8) | 0x6226cc, 0x6226d0 | Sun angle α (0x6226d8) |
|---|---|---|---|---|---|
| 06–17 | 0, 0, 0 | 14 | 32 | 4, 2 | `((t + 360) mod 720)·π/2/720 − π/4` |
| 18–19 | 24m/120, 0, 8m/120 | 14 + 10m/120 | 32 − 12m/120 | 6, 3 | +π/4 |
| 20–21 | 24 − 24m/120, 12m/120, 8 + 40m/120 | 24 + 8m/120 | 20 − 12m/120 | 6, 3 | +π/4 |
| 22–01 | 0, 12, 48 | 32 | 8 | 8, 4 | `π/4 − ((t + 120) mod 240)·π/2/240` |
| 02–03 | 24m/120, 12, 48 − 48m/120 | 32 − 4m/120 | 8 + 12m/120 | 6, 3 | −π/4 |
| 04–05 | 24 − 24m/120, 12 − 12m/120, 0 | 28 − 14m/120 | 20 + 12m/120 | 6, 3 | −π/4 |
| option off (`DAT_00622770 = 0`) | 0, 0, 0 | 14 | 32 | 4, 2 | +π/4 |

π, π/4 = stored doubles 3.1415926, 0.78539815. By day the sun sweeps −π/4
→ +π/4; at night a second sweep every 4 hours (INFERRED: moon). All values
are continuous at the boundaries (within 1 unit of truncation; e.g. 22:00
tint = (0, 12, 48)). The tint is added to every palette in modes 1–3
([palettes §7](../formats/palettes.md)). `FUN_0041d3b9` runs this every
20 game minutes, then `FUN_004a5dd2` (§2) and `FUN_0047e345` (rebuilds the
tinted tables). `0x6226cc/0x6226d0` are the shadow levels (§5), passed to
sprite method `+0x3c` (`FUN_00424af4`, shadow blitters).

## 1a. When the exe recomputes light, CONFIRMED

`FUN_0041d3b9(force)` (checked in REA, GOG build) is the only path to
`FUN_00474d98` and (besides `FUN_0041c18c`, which re-lights a 2x2 patch for
cell flags 14/15) to `FUN_004a5dd2`. Callers: scenario load `FUN_0041bee2`
(force 1), the view's message 0x401 (force 0), the option toggle `FUN_0040c8a0`
(key `N`, only in debug mode `DAT_006227d8`; force 1), the options dialog
`FUN_00442e8b` (force 1 when `DAT_00622770` changed). With force 0 it runs
only when the view is in game state (`+0x404 & 1`), `DAT_00622770 ≠ 0`,
`clock & 15 == 0` and `m = (clock >> 4) + 360` is a multiple of 20: every 320
ticks, starting at tick 0. The sequence is `FUN_00474d98(m)`, `FUN_004a5dd2`
(whole map), `FUN_00404910`, `FUN_0047e345`, then redraw flags.

`DAT_00622770` is the "ShowTimeFlow" option (`GameOptions/ShowTimeFlow` in
`game%d.sav`, [saves](../formats/saves.md)); its static default is 0, so a
new game has no time of day: the load call applies the option-off row (A 14,
D 32, α +π/4, no tint) over the map header's light fields. No script
instruction, trigger or unit touches the light; nothing else writes
`0x6226c0..d8`. For map 32 (J4) the header light is therefore never used and
the light is constant unless the option is switched on. CONFIRMED (`FUN_0041d3b9`
`0x41d3e2`): the clock is the client object's `+0x408`, the server step counter
that the type-100 handler stores each step ([simulation 2](../engine/simulation.md));
`m = (+0x408 >> 4) + 360`. The option has a visible control: the options dialog's
apply message `0x445` (`FUN_00442e8b`) reads widget `0xc` into `DAT_00622770` (beside
Shadows `0x1f`, Dynamic lighting `0x20`, Object animations `0x21`, widget `3` =
Smoothing `DAT_00622768`) and calls `FUN_0041d3b9(1)` when it changed. The engine's
options window is phase K (the menu entry is disabled), so the engine's only toggle
stays `TerrainView.set_time_flow` / the debug key `N`.

Engine: `TerrainView(time_flow=False)` is that default; `set_clock(tick)`
repeats the cadence above and `set_time_flow` is the toggle. Client-only
(view light, not simulation state): the replay hash is unaffected. A light
change bumps `TerrainView.version`, which empties the surface cache, so a
step costs one cold frame (~730 ms on a 1024x768 view, every 320 ticks and only
with the option on); off, there is no cost.

## 2. Terrain light map (`FUN_004a5dd2`), CONFIRMED

Per vertex `(x, y)`, x in 1..w−2, y in 1..h−2, signed heights `H`
(`movsx`), `A` = ambient, `D` = diffuse (bytes), `τ = tan|α|`,
`run = 32 / cos|α|`:

```
if α ≥ 0:
    d1 = H[y+1][x] − (H[y+1][x] − H[y+1][x−1])·τ − H[y][x]
    d2 = H[y][x] − ((H[y−1][x+1] − H[y−1][x])·τ + H[y−1][x])
else:
    d1 = (H[y+1][x+1] − H[y+1][x])·τ + H[y+1][x] − H[y][x]
    d2 = H[y][x] − (H[y−1][x] − (H[y−1][x] − H[y−1][x−1])·τ)

Li = (A + D div 2 + 32) − D·sin(0.5235987666666667 − atan2(di, run)),
     clamped to 0..94
light[y][x] = trunc((L1 + L2) / 2)        # fistp with truncation
```

The terrain blitters (`FUN_00457487` flat, `FUN_004575fe` general,
[terrain](../formats/terrain.md)) interpolate the four corner values
bilinearly in 1/512 steps (rounding +0x100) and draw texel `i` as
`table.row(light)[i]`. Terrain draws: `FUN_00404e0e`, `FUN_0040538d`,
`FUN_00405861`, `FUN_00405cf4`.

Example: day (A 14, D 32), flat: `L = 62 − 32·sin(π/6) = 46` (×1.56);
night (A 32, D 8): `68 − 8·0.5 = 64` (×1.0) plus the blue tint. Ground
rising toward +y (down screen) is darker, falling brighter.
`terrain_light(heights, angle, ambient, diffuse)`; Python `sin`/`atan2`
may differ from x87 by 1 ulp, so an exact-integer value could truncate
differently (INFERRED rare).

## 3. Light map (`view + 0xa8`), CONFIRMED

One byte per vertex of the visible window (stride `w + 7`, offset
(+3, +3)), terrain row scale, **0xFF = no light**. Rebuilt every frame by
`FUN_0040403b`:

1. Copy the old map to `+0xac` (only when `DAT_0061b5b0 == 2`), fill
   `+0xa8` with 0xFF.
2. Each view-list object gets virtual `+0x38` and `+0x40` (vtables
   `0x5cd520`, `0x5cd5d0`, `0x5cd660`, `0x5cd6f0`, bridges
   `0x5cea88`/`0x5ceae0`). `+0x38` = `FUN_00460591(kind)` only records the
   object in a per-cell view array (1 structure, 2 ground unit, 3 flyer, 4
   corpse or flag `0x80`). `+0x40` is the light: **units and flyers emit
   none** (`FUN_0046dde0` empty), projectiles `FUN_0046d0ef`, structures
   `FUN_00462386` (below).
3. **Burning cells** (list `view+0xa94` behind
   `FUN_00420590`/`FUN_004205b0`, entries `{next, ?, cell x | y << 8,
   counter}`; not static map lights) stamp radius 1 with value by
   `counter >> 1`: `36, 24, 12, 0, 12, 0, 12, 0, 20, 28, 36` for phases
   0–10, nothing otherwise. Origin, counter update (`FUN_0040c0b0`, via
   `FUN_0040b2b8`, removal at 22) and fire/steam sprites:
   [animation §4.6](../formats/animation.md#46-burning-cells).
4. `FUN_00404a2a` derives the object rows (§4).

**Stamp** (`FUN_0040631e`, only with the **Lighting** option `0x5f17f0`):
`value` at every vertex `(cx + dx, cy + dy)` with `dx² + dy² < r·(r + 1)`
(r = 0: centre only); squares from a 41×41 u16 table centred at
`0x6218c0` (row stride 0x52), filled at startup by `FUN_00474756` for
|dx|, |dy| ≤ 20. Vertices outside the window are skipped.

**Structure lights** (CONFIRMED `FUN_00462386`; Lighting option,
`LightRadius ≠ 0`, HP `> 0`): with view cell rect `(x0, y0)-(x1, y1)`
(`obj+0x40…+0x4c`, `FUN_0046025d`) and `R = LightRadius`, every vertex
`x0 + R − 1 ≤ x ≤ x1 + R`, `y0 + R − 1 ≤ y ≤ y1 + R` gets

```
v = 0x20                                         if LightPulse P == 0
m = clock mod 2P
v = 0x20 − ((P − m) >> 1) + clock mod P          if m <  P
v = 0x20 + ((P − m) >> 1) − clock mod P          if m >= P   (>> is arithmetic)
```

(`clock` = `view+0xa88`). Every record has `R = 1`, so exactly the
footprint corners are written (other `R` would shift, not grow, the
range). Records: Tower 1/2 (`P = 8`), Well 2 (no pulse), Well 3 (`P = 4`),
Campfire (`P = 6`). `P = 8`, clock 0…15: 28 30 31 33 34 36 37 39 32 30 29
27 26 24 23 21. `structure_light_value`, `structure_light_vertices`.

**Projectile lights** (`FUN_0046d0ef`, by `projectiles.reg` ID `+0x24`;
names CONFIRMED from `projectiles.reg`): 10 firebolt, 18 icemissile, 40
meteorit → radius 0, value 16; 12 fireball → (1, 16); 13 fireexpl by
phase `+0x74`: 0 (1, 16), 1 (2, 8), 2–3 (3, 0), 4 (3, 8), 5 (3, 16), 6
(3, 24), 7 (3, 32), 8 (3, 40), 9–10 (3, 46); 28 lightnin, 30 chain: each
segment writes `phase·10` to its 2×2 vertices directly.

**Verified (CONFIRMED `FUN_0046d0ef`, `FUN_0041c18c`, `FUN_0040c0b0`, GOG exe):** no light has a colour, a decay or a lifetime of its own: the map holds one
brightness byte per vertex (0 brightest, 0xFF none), rebuilt from scratch each frame, so "decay" is only the phase table of the source. Projectile 13 (fire
explosion) uses phase `+0x74` (ticks since the explosion started) as above (radius 3 plateau 46 = nearly dark at phases 9-10, i.e. a flash that fades out);
the burning list counter (`+1` per `FUN_0040b2b8` call, entry dropped at 22, `FUN_0040c0b0` `0x40c0b0`) indexes `BURNING_LIGHT_PHASES`. Lightning (28) and
prismatic spray (30) bypass the stamp: `FUN_0046d0ef` writes `phase * 10` (byte) straight into the 2 x 2 vertices at each segment point (cell `x >> 5`,
`FUN_00417f31(x, y)`; points inside the window only) and **without** the Lighting-option gate; every other projectile id only dirties the 5 x 5 cell
redraw rect (`FUN_0041e210`) when the option `0x5f17ec` is 0. Wall of Fire (cell flag 3, `FUN_0041c18c` `0x41c44f`-`0x41c4c0`): only when the cell's tile
bit `0x2000` was clear and its map object has `DeadObject != -1` does it add `{cell, 0}` to the burning list (then sets `0x2000`). Applied: lit terrain
corners and object rows as above. `hydra` / `bracelet` data: irrelevant (no light field in monsters / items; a structure's `LightRadius`/`LightPulse` is the only
data-driven light).

**Terrain under lights** (`FUN_00405cf4`): tiles with any corner ≠ 0xFF
are redrawn with `corner = min(terrain_light, light)` (terrain light from
§2 where the light map is 0xFF).

Built in the engine: structure, missile, Lightning / Prismatic Spray bolt (`World.bolts`, `lights.bolt_cells`; the points' cells by the row finder `FUN_00417f31`, [effects §11](../engine/effects.md#11-prismatic-spray-chain-and-the-lightning--spray-bolts-confirmed-unless-tagged-engine-spellsspray_chain-aispray_targets-effectsspawn_bolt-lightsbolt_)) and fire explosion (projectile 13, `World.explosions`) lights, burning cells from a Wall of Fire flag (`World.burn_start`, counter = ticks since the flag, INFERRED
one counter step per tick; stamped after the object lights), cell rows, lit terrain corners, and the Light / Darkness
vertex writes (`engine/view/lights.py`, [rendering](../engine/rendering.md#structure-pick-rects-and-dynamic-lights-confirmed-engine-drawlistpick_cell-lightspy)).
Implementation: `stamp_light`, `projectile_light`, `BURNING_LIGHT_PHASES`
(= `STATIC_LIGHT_PHASES`), `structure_light_value`, `lit_terrain_corner`.

**Fog levels** (`view+0xa0`, CONFIRMED `FUN_0040403b`
`0x4041d2`–`0x4044a2`): one dword per view cell (window `w + 7`, from
(−3, −3)), rebuilt every frame from tile bits `0xc000`: 0 in sight
(`0xc000`), 8 explored (`0x8000` alone), 16 never seen; then copied to
`view+0xa4` (previous frame). For cells in sight the loop also adds a
redraw rectangle from `view+0xb8/+0xbc` (± 0x60 px) when "Object
animations" is on. `fog_level`.

**Fog draw** (CONFIRMED, pass `0x40a06a`–`0x40a5bc` of the view draw
`FUN_00406f43`, after the object layers): columns `c = 0 … W−1` left to
right, cells `r = 0 … Hv+3` top to bottom. Cell `(c, r)` is drawn over
its own screen quad (x `32c … 32c+31`, corner y from the vertex table
`view+0xb4`, [terrain](../formats/terrain.md#vertex-table-fun_004065b1))
but its corners take the levels of cells `(c, r)`, `(c+1, r)`,
`(c, r+1)`, `(c+1, r+1)`, so fog edges sit half a cell down-right of the
cells.

- **Merge**: while column `c` and `c+1` levels satisfy
  `L[r] = L[r+1] = L[r+2]` and `r ≠ Hv+3`, the run grows; its quad spans
  the first cell's top vertices to the last cell's bottom vertices.
- All four levels 0 → nothing. All 16 → black fill, `FUN_00457944` (flat:
  `yTL = yTR`, `yBL = yBR`, `yTL + 32 = yBL`) or `FUN_00457a4d`; all 8 →
  halve (`px >> 1 & 0x6227f8`), `FUN_004582bc` / `FUN_004584d0`; mixed →
  `FUN_00457da7` (flat) / `FUN_00457f5b`. The relief fills fall back to
  `FUN_00457f5b` with four equal levels when the top and bottom edges
  overlap in y.
- Every routine covers `top(c) ≤ y < bot(c)` with the terrain blit's edge
  steps and applies **blend-table row k** (`FUN_0045225b`, `DAT_0061f5b8`,
  rows 0–16, each 16-bit channel `v → v·(16 − k) >> 4`, the shadow table
  of §5); black and halving equal rows 16 and 8. Per column (`K =
  0x10000`, one row = `2K` bytes):

```
t = TL·2K + c·((TR − TL)·2K >> 5)        # top-edge walk
b = BL·2K + c·((BR − BL)·2K >> 5)        # bottom-edge walk
step = (b − t) / span                     # C division, span = bot(c) − top(c) > 0
k(i) = (t + K + i·step) >> 17             # pixel top(c) + i
```

  i.e. `k = floor(walk + ½)` of a bilinear walk over the corner levels.
- Clipping (`0x61b5a0…774`): flat uniform cells test only y; any other
  quad is skipped unless `32c … 32c+32` is inside the clip x range, and
  needs `yTL` or `yTR` above the clip bottom and `yBL` or `yBR` at or
  below its top. Clipped rows still advance the walk.
- Each fill darkens what is already there. Top and bottom edge steps
  agree for every `n ≤ 127` except 63 and 127, where the bottom edge sits
  1 px lower so along such an edge one
  pixel row is darkened by both cells.

Example, flat cell with TL = 16 and TR = BL = BR = 0: column 0 rows
`16 16 15 15 … 1 1`, column 1 `16 15 15 … 1 0`, column 16 starts at 8,
column 31 is 1 then 0. `fog_shade`, `fog_quad_columns`, `fog_runs`,
`draw_fog`; `tools/terrain_render.py MAP --fog CX CY R`.

## 4. Object light rows (`FUN_00404a2a`), CONFIRMED

A byte per visible cell at `view + 0xb0` (stride `w + 6`), passed by
`FUN_00406f43` as the row to each object's draw (vtable `+0x28`):

1. Fill with `A >> 2`: row 3 (×1.625) by day, 8 (×1) at night.
2. Map light entries with flag 0x8000 force their cell to 0 (×2), 0x4000
   to 12 (×0.5); flag 8 stamps radius 1 into the light map with 0 or 12,
   by `hash(x·y + view[0xa88]/2) mod 5` odd.
3. Per cell, the four light-map corners as `max(v − 32, 0)`: all 223
   (unlit) → keep; else 223 corners count as `A` and the cell gets
   `min(A >> 2, sum >> 4)`.

The row of a cell goes unchanged to **every** piece drawn by that cell's call:
a structure footprint cell `(c, r)` passes `view+0xb0[cell]` to all pieces of
its column (the rows above too), so one row per footprint cell, never per
piece; objects use their own cell's row. Smoothing (`b.256`) is drawn with
the **same row byte** and the main sprite's table (`FUN_0041e690` = sprite
`+0x14`), blended 50 % over the destination; shadows take no row. Neither
structure nor object draw takes an owner palette (structure `+0x18`
5 arguments, object `+0x14` with the sprite's own table; mirror always 0):
CONFIRMED `FUN_00461649`, `0x40922c`; no team remap exists for them.

So a light brightens nearby objects up to row 0 (×2); values above 32 fade
it out. The unit draw forces row 0 for the hovered unit
([palettes §7](../formats/palettes.md)). `object_light_row(ambient)`
(step 1), `object_light_row_lit(corners, ambient)` (step 3).

## 5. Shadows, CONFIRMED

Only with the **Shadows** option (`0x5f17e8`). `FUN_0045506f` walks the
sprite's RLE stream for its shape, ignores pixel values, and replaces each
covered pixel through blend table `k`: `dst·(16 − k)/16` per channel
(tables from `FUN_0045225b`).

- **Darkness** `k` = `0x6226cc` (4 day, 6 dusk/dawn, 8 night: ×0.75 /
  ×0.625 / ×0.5) for the main sprite; the lighter `0x6226d0` (2 / 3 / 4)
  for the shadow of the `b.256` smoothing sprite (only with Smoothing
  `0x622768`; the backpack's `b` shadow has no Smoothing gate). Not a
  "second set of objects": `0x626ca4/0x626ca8` are the backpack sprite and
  its `b` file (`graphics\backpack`, loaded `0x477411`). Every sprite
  therefore casts two shadows over the same area (`b` is a halo, often larger),
  darkening twice where they overlap.
- **Callers** of the sprite shadow method `+0x3c` (`FUN_00424af4` → `FUN_0045506f`,
  mirrored `FUN_00456021`): view draw objects (`0x408ec4`, `0x40905b`),
  structure shadow `FUN_00461890` (`+0x2c`, `0x461ab0`, `0x461aeb`),
  backpack `FUN_00461292`, units `0x464d58`…`0x46533a`. Objects, structures,
  backpacks pass mirror 0; none of the three uses the mirrored blitter.
  Bridges (`FUN_0046282f`, `0x462a3d`) and projectiles (`FUN_0046dda0`) have
  an empty `+0x2c`: no shadow.
- **Shear**: `trunc(tan(β)·65536)` (16.16), `β = α / 1.5`, except
  `−0.05 < α < 0` → β = −0.05, `0 < α < 0.05` → 0.05 (`FUN_004a4429`,
  constants `0x5cea48/18/20`; the `tan` is `FUN_00582cd4`, `ftol` truncates).
  The top row starts `trunc(shear·h/65536)`
  px right; after each row (row skips count) the accumulator gains
  `shear` and the row moves left by its whole part; the bottom row ends
  under the sprite.
- **Anchor, map object** (`0x408cb9`–`0x409089`), `T = tan β`: shadow
  sprite top-left `x = 32X + 16 − ((CenterX − Width/2) + w0/2) − dx`,
  `y = 32Y + 16 − ((CenterY − Height/2) + h0/2) − relief`, with
  `dx = trunc(T · (h/2 + Height/2 − CenterY))` (`/2` truncates to 0; record
  fields as [animation §4.3](../formats/animation.md#43-objects)), `h` =
  height of the **current** frame of the main sprite, `w0`, `h0` = width,
  height of **frame 0** of the sprite being shadowed (main, then `b`
  separately; quirk: the draw itself uses the current frame, so a shadow is
  off by the half-size difference when frames differ; 2 of 135 object files,
  `pointer`, `stones`, and the `b` files differ more: 36 files). `dx` is the
  main's value for both shadows. Net effect: the shear pivot is the anchor
  `(32X + 16, 32Y + 16 − relief)`, pixels above it lean right by `T·Δy`.
  Passed to `+0x3c`: `(x, y, frame, k, shear16, 0)`.
- **Anchor, structure piece** (`FUN_00461890`, same cell/row/frame logic as
  the draw): piece `(c, r)` shadow at `x = 32·cx + trunc(T·((FH − r)·32 −
  ShadowY))`, `y` = the piece's draw `y` (`32·cy − g − 32·(rows above)`),
  piece frame as the draw, main `k = 0x6226cc`, then `b` (`FUN_0046e0b0`)
  `k = 0x6226d0` if Smoothing; so the pivot is the picture's bottom edge
  raised by `ShadowY`. Order: pieces bottom-up, main then `b`.
- **Backpack** `FUN_00461292`: `x = obj+0x64 − w/2 − dx`, `y = obj+0x68 − h/2 −
  obj+0x6c − 4`, `dx = trunc(T·(h/2))`, frame `obj+0x24`.
- `FUN_00454d57`/`FUN_00455cf0` = low-memory variants (not reproduced,
  `DAT_006227f0`), `FUN_00456021` = mirrored.

`shadow_angle`, `shadow_shear`, `shadow_row_offsets`, `shadow_pixel`.

## 6. Options

Registry DWORDs written by `FUN_00441372` (`RegSetValueExA`), read by
`FUN_004415d4`. The options dialog (`FUN_004417fa`; Object animations
checkbox labelled at `0x441e2d`) uses lines `0x34`–`0x36` of
`patch\patch.txt` (table `0x621878`, loaded at `0x481702`). All
default to 1 (`.data`). CONFIRMED:

| Name | Flag | Dialog label | Effect |
|---|---|---|---|
| `Shadows` | `0x5f17e8` | Shadows | draw shadows (§5) |
| `Lighting` | `0x5f17f0` | Dynamic lighting | stamp lights (§3) |
| `Animation` | `0x5f17ec` | Object animations | water, structure, object animation ([animation §3.2](../formats/animation.md#32-what-advances-each-kind-of-animation)); when 0, light changes also invalidate screen rectangles (`FUN_0041e210/390`); turning it off also clears `Lighting` (`0x442fc0`) |
| day/night | `0x622770` | — | §1 (toggled by key handler `FUN_0040c8a0`) |

## Open questions

None.
