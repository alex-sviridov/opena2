# Lighting and time of day

Implementation: `allods2/graphics/lighting.py`; the palette side is in
`allods2/graphics/palette.py`. Binary: `allods2.exe` English 1.30, sha256
`2a8bdf9d…fe43`. Everything below was checked in REA pseudocode and, for
the floating-point parts, in the x87 assembly.

The game does no per-pixel lighting. A light value is a **row number** in
a palette's shade table ([palettes §5](../formats/palettes.md)), where
row 0 is the brightest:

| Drawn thing | Table | Rows | Row → brightness |
|---|---|---|---|
| terrain tiles | BRIGHT32 | 96 | `(96 − r)/32`: r = 64 is ×1 |
| units, structures, objects | BRIGHT2 | 16 | `2(16 − r)/16`: r = 8 is ×1 |

## 1. Time of day (`FUN_0047a208`), CONFIRMED

Input: game time `t` in minutes (FUN_0041f200 passes `(clock >> 4) + 360`,
so a game starts at 06:00). With `h = (t / 60) mod 24` and `m = t mod 120`
(all integer, truncating):

| Hours | Tint R, G, B (0x62c888..a) | Ambient (0x62c88c) | Diffuse (0x62c890) | 0x62c894, 0x62c898 | Sun angle α (0x62c8a0) |
|---|---|---|---|---|---|
| 06–17 | 0, 0, 0 | 14 | 32 | 4, 2 | `((t + 360) mod 720)·π/2/720 − π/4` |
| 18–19 | 24m/120, 0, 8m/120 | 14 + 10m/120 | 32 − 12m/120 | 6, 3 | +π/4 |
| 20–21 | 24 − 24m/120, 12m/120, 8 + 40m/120 | 24 + 8m/120 | 20 − 12m/120 | 6, 3 | +π/4 |
| 22–01 | 0, 12, 48 | 32 | 8 | 8, 4 | `π/4 − ((t + 120) mod 240)·π/2/240` |
| 02–03 | 24m/120, 12, 48 − 48m/120 | 32 − 4m/120 | 8 + 12m/120 | 6, 3 | −π/4 |
| 04–05 | 24 − 24m/120, 12 − 12m/120, 0 | 28 − 14m/120 | 20 + 12m/120 | 6, 3 | −π/4 |
| option off (`DAT_0062c938 = 0`) | 0, 0, 0 | 14 | 32 | 4, 2 | +π/4 |

π and π/4 are the stored doubles 3.1415926 and 0.78539815. During the day
the sun sweeps from −π/4 to +π/4. At night a second sweep runs every 4
hours (INFERRED: the moon). All values are continuous at the boundaries.

FUN_0041f200 runs this every 20 game minutes, then calls FUN_004ad552
(§2) and FUN_0048392f (rebuilds the shade tables with the new tint).

`0x62c894` / `0x62c898` are passed as an argument to the sprite method
`+0x3c` (FUN_00427344, the shadow blitters). **INFERRED**: shadow length or
offset.

## 2. Terrain light map (`FUN_004ad552`), CONFIRMED

Per vertex `(x, y)`, for x in 1..w−2 and y in 1..h−2, from the signed
height map `H` (bytes, read with `movsx`), with `A` = ambient, `D` =
diffuse (both as bytes), `τ = tan|α|` and `run = 32 / cos|α|`:

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

The terrain blitter (FUN_0045c757 for flat tiles, FUN_0045c8ce for the
general case) gets the four corner light values of a 32×32 tile. It
interpolates them bilinearly in 1/512 steps (rounding by +0x100) and draws
texel `i` as `table.row(light)[i]`. Terrain draws come from FUN_00404eb5,
FUN_00405434, FUN_00405908 and FUN_00405d9b.

### Worked example

Day (A = 14, D = 32) on flat ground: d = 0, so θ = 0 and
`L = 62 − 32·sin(π/6) = 46`. Row 46 is ×1.56. At night (A = 32, D = 8):
`L = 68 − 8·0.5 = 64`, which is ×1.0, and the blue tint is added on top.
Ground rising toward +y (down the screen) gets a larger d and is darker;
ground falling toward +y is brighter.

Implementation: `terrain_light(heights, angle, ambient, diffuse)`.
`math.sin`/`atan2` in Python can differ from x87 by 1 ulp, so a value that
lands exactly on an integer could truncate differently. INFERRED to be
rare.

## 3. Light map (`view + 0xa8`), CONFIRMED

One byte per map vertex in the visible window (stride `w + 7`, offset
(+3, +3)), using the terrain row scale: 0 is the brightest, and **0xFF is
"no light"**. It is rebuilt every frame by FUN_004040e2:

1. Copy the old map to `+0xac` (only when `DAT_00625778 == 2`), then fill
   `+0xa8` with 0xFF.
2. Each object in the view list gets virtual calls `+0x38` and `+0x40`.
   Light-emitting objects stamp into the map there.
3. **Static map lights** (the list behind FUN_00422580 / FUN_004225a0,
   whose entries are `{next, ?, cell x | y << 8, flags}`) stamp radius 1
   with a value chosen by animation phase `flags >> 1`:
   `36, 24, 12, 0, 12, 0, 12, 0, 20, 28, 36` for phases 0–10, and nothing
   for other phases. This makes torches flicker.
4. FUN_00404ad1 then derives the object rows (§4).

**Stamp** (FUN_004063c5, only when the **Lighting** option `0x5fb978` is
on): `value` is written at every vertex `(cx + dx, cy + dy)` with
`dx² + dy² < r·(r + 1)` (r = 0: the centre only). The squares come from a
41×41 u16 table centred at `0x62ba88` (row stride 0x52) that the startup routine FUN_00479bc6 fills with `dx² + dy²` for |dx|, |dy| ≤ 20.
Vertices outside the window are skipped.

**Projectile lights** (FUN_00472562, by `projectiles.reg` ID at `+0x24`):

| ID | `File` | Radius, value |
|---|---|---|
| 10 firebolt, 18 icemissile, 40 meteorit | | 0, 16 |
| 12 fireball | | 1, 16 |
| 13 fireexpl, phase `+0x74` | | 0: (1, 16); 1: (2, 8); 2–3: (3, 0); 4: (3, 8); 5: (3, 16); 6: (3, 24); 7: (3, 32); 8: (3, 40); 9–10: (3, 46) |
| 28 lightnin, 30 chain | | each segment writes `phase·10` to its 2×2 vertices directly |

The ID → file names are **CONFIRMED** (data): `projectiles.reg`
sections `ProjectileN` hold `ID`, `File`, `Phases`, … .

**Terrain under lights** (FUN_00405d9b): tiles with any corner ≠ 0xFF
are redrawn with `corner = min(terrain_light, light)`, using the
terrain light from §2 where the light map is 0xFF.

Implementation: `stamp_light`, `projectile_light`,
`STATIC_LIGHT_PHASES`, `lit_terrain_corner`.

## 4. Object light rows (`FUN_00404ad1`), CONFIRMED

A byte per visible cell at `view + 0xb0` (stride `w + 6`), which the
object renderer FUN_00406fea passes as the row to each object's draw method
(vtable `+0x28`):

1. Fill with `A >> 2`: row 3 (×1.625) by day, row 8 (×1) at night.
2. Map light entries with flag 0x8000 force their cell to 0 (×2), and
   flag 0x4000 forces it to 12 (×0.5). Flag 8 stamps radius 1 into the
   light map with 0 or 12, chosen by `hash(x·y + view[0xa88]/2) mod 5`
   being odd.
3. For each cell, take the four light-map corners as `max(v − 32, 0)`. If
   all four are 223 (unlit), the cell keeps its value. Otherwise corners
   equal to 223 count as `A`, and the cell gets `min(A >> 2, sum >> 4)`.

So a light brightens nearby objects down to row 0 (×2). Values above 32
fade the effect out.

The unit draw (FUN_00468640) overrides the row with 0 for the hovered
unit (see [palettes §7](../formats/palettes.md)).

Implementation: `object_light_row(ambient)` (step 1),
`object_light_row_lit(corners, ambient)` (step 3).

## 5. Shadows, CONFIRMED

Drawn only when the **Shadows** option (`0x5fb970`) is on. The blitter
FUN_0045a33f walks the sprite's RLE stream for its shape, ignores the
pixel values, and replaces each covered destination pixel through blend
table `k`: `dst·(16 − k)/16` per channel (the tables from FUN_0045752b).

- **Darkness** `k`: `0x62c894` (4 by day, 6 at dusk/dawn, 8 at night,
  i.e. ×0.75 / ×0.625 / ×0.5). The lighter `0x62c898` (2 / 3 / 4) is used
  for a second set of objects (`0x630e7c`) and for translucent units.
- **Shear**: `trunc(tan(β)·65536)` in 16.16, with `β = α / 1.5`, except
  that `−0.05 < α < 0` gives β = −0.05 and `0 < α < 0.05` gives β = 0.05
  (FUN_004abba9, constants `0x5d8c10/18/20`). The top row starts
  `trunc(shear·h / 65536)` pixels to the right. After each row (row skips
  count too) the 16.16 accumulator gains `shear`, and the row moves left
  by its whole part. The bottom row ends up under the sprite.
- FUN_0045a027 / FUN_0045afc0 are the low-memory variants (not
  reproduced), and FUN_0045b2f1 is the mirrored variant.

Implementation: `shadow_angle`, `shadow_shear`, `shadow_row_offsets`,
`shadow_pixel`.

## 6. Options

The registry values are written as DWORDs by `FUN_00444790`
(`RegSetValueExA`) and read by `FUN_004449f2` under these names. The
options dialog (`FUN_00444c18`) labels the checkboxes with lines
`0x34`–`0x36` of a2mgr's `patch\patch.txt` (table `0x62ba40`, loaded by
a2mgr Ordinal_3). All three default to 1 (`.data`). **CONFIRMED**:

| Name | Flag | Dialog label | Effect |
|---|---|---|---|
| `Shadows` | `0x5fb970` | Shadows | draw shadows (§5) |
| `Lighting` | `0x5fb978` | Dynamic lighting | stamp lights into the light map (§3) |
| `Animation` | `0x5fb974` | Object animations | water, structure, object animation ([animation §3.2](../formats/animation.md#32-what-advances-each-kind-of-animation)); when 0, light changes also invalidate screen rectangles (FUN_00420330/390). Turning it off also clears `Lighting` (`0x4463de`) |
| day/night | `0x62c938` | §1 (toggled by key handler FUN_0040c989) |

## Open questions

1. What the object virtuals `+0x38` / `+0x40` stamp for units and
   structures (unit torches, burning buildings).
2. Where static map lights come from (`.alm` sections or spells such as
   Light), and what drives their phase.
3. What `+0xa0` / `+0xa4` hold. FUN_004040e2 sets them from the cell flags
   (0, 8 or 16; INFERRED: fog of war) and FUN_00406981 / FUN_00406c9e
   build the draw spans from them.
