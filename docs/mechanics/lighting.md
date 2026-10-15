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

## 3. Object light map (`FUN_00404ad1`), CONFIRMED

A byte per visible cell at `view + 0xb0`, which the object renderer
(FUN_00406fea) passes as the row to each object's draw method (vtable
`+0x28`):

1. Fill with `A >> 2`: row 3 (×1.625) by day, row 8 (×1) at night.
2. For each entry in the list returned by FUN_00422580 (a cell `x | y<<8`
   and flags): flag 0x8000 sets the cell to 0 (×2), and flag 0x4000 sets
   it to 12 (×0.5). Flag 8 calls FUN_004063c5 with 0 or 12, chosen by a
   hash of the position and `+0xa88`. **INFERRED**: light sources, with
   flag 8 flickering.
3. For each cell, sum the four corners of the map at `view + 0xa8`, each
   taken as `max(v − 32, 0)`. If the sum is not 4·223, any corner equal
   to 223 is replaced by `A`, and the cell gets `min(A >> 2, sum >> 4)`.
   **INFERRED**: `+0xa8` is the vision or fog map, and fully dark cells
   keep the step 1–2 value.

The unit draw (FUN_00468640) overrides the row with 0 for the hovered
unit (see [palettes §7](../formats/palettes.md)).

Implementation: `object_light_row(ambient)` gives the step 1 default.

## Open questions

1. What `view + 0xa8` holds and how it is built (vision/fog); FUN_00406981
   and FUN_00406c9e build the visibility spans from it and `+0xac`.
2. The light-source list behind FUN_00422580 / FUN_004225a0, and
   FUN_004063c5.
3. How `0x62c894` / `0x62c898` shape shadows (FUN_0045a33f / FUN_0045b2f1).
4. How `.alm` section 2 heights map to the runtime signed height map at
   `+0x10`.
