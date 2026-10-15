# Terrain: `.alm` Tiles block → `tile<g>-<nn>.bmp` strips

Binary: `allods2.exe` English 1.30, sha256
`2a8bdf9dc69276cc8d4fee561a7473a6b0f709cf9758abddaf2cd3b1fdfdfe43`.
Addresses were read in REA (Ghidra 12.1.4) and in the x86 listing.
Implementation: `allods2/alm.py` (container), `allods2/graphics/terrain.py`.
Validation: `tools/validate_terrain.py`. Contact sheets:
`tools/terrain_contact.py` → `out/contact/terrain.png` (all strips, map
thumbnails); `tools/tile_contact.py` → `out/contact/tiles_<set>.png` (one
grid per set, each tile labelled with the cell value a map stores for it,
`tr.cell_value(set, strip, row)`; add `0x2000` for dirt). One tile as RGBA:
`TerrainSet.tile_rgba(set, strip, row, light=None)`.

The ground is a grid of 32 × 32 8-bit tiles. Each map cell holds a u16 in
the `.alm` Tiles block (section 1, [inventory §5.2](../inventory.md)); the
value selects a tile set, one of its four strip bitmaps, and a tile inside
the strip.

## Strip files: `FUN_0047b899(mask)`

**CONFIRMED.** For each bit `t` (0..31) set in `mask`, the loader reads four
8-bit BMPs into `DAT_00630b90[t][j]`, j = 0..3:

```
name(t, j) = "graphics\terrain\tile%d-%02d.bmp" % ((t >> 2) + 1, (t & 3)·4 + j)
```

(The exe uses `tile%d-0%d.bmp` below 10 and `tile%d-%d.bmp` above, strings
0x5fbcac / 0x5fbccc.) With a non-zero mask it also loads
`graphics\terrain\dirt.bmp` into `DAT_00630da4`. For each loaded set it builds
a 96-row BRIGHT32 shade table from the first strip's palette
(`FUN_00426be0(0x60, 3, 1)`, stored in `DAT_0062ca78[t]`; see
[palettes §5](palettes.md) and [lighting](../mechanics/lighting.md)).

| Set `t` | Files | Strip size | Tiles per strip |
|---|---|---|---|
| 0–3 | `tile1-00` … `tile1-15` | 32 × 448 | 14 |
| 4–7 | `tile2-00` … `tile2-15` | 32 × 448 | 14 |
| 8–11 | `tile3-00` … `tile3-15` | 32 × 256 | 8 (water, 4 animation frames) |
| 12 | `tile4-00` … `tile4-03` | 32 × 448 | 14 |
| — | `dirt.bmp` | 32 × 128 | 4 dirt overlays |

- **CONFIRMED** (data): all 52 strips exist and share one palette; `dirt.bmp`
  has its own, but its indices are pasted into tile memory (below), so they
  are read with the tile palette.
- **CONFIRMED** (`FUN_004280d4`, [bitmaps](bitmaps.md)): rows are flipped
  after loading, so tile `r` is the r-th 32-row block from the **top**.
- **INFERRED** (unused path): when `DAT_00625778 & 2`, the same sets are first
  loaded from `graphics\terrain.3d\` (strings 0x5fbc28…0x5fbc6c) and then
  released and replaced by the `graphics\terrain\` ones in the next loop.
  This install has no `terrain.3d` folder.
- Who passes which mask was not traced (INFERRED: the sets the map uses).

## Cell value

**CONFIRMED** (`FUN_00404eb5`, 0x405035–0x405185):

| Bits | Mask | Meaning |
|---|---|---|
| 0–3 | `0x000f` | tile index inside the strip (`· 0x400` bytes) |
| 4–5 | `0x0030` | strip `j` (0..3) |
| 6–12 | `0x1fc0` | set `t` |
| 13 | `0x2000` | dirt overlay (ignored on water sets) |
| 14–15 | `0xc000` | masked off by the terrain draw (`& 0x1fff` / `& 0xffff1fff`) |

```
tile(v, x, y):                       # x, y = map cell
    s   = (v & 0x1fff) >> 6
    j   = (v >> 4) & 3
    row = v & 0xf
    if 8 <= s <= 11:                 # water
        s = 8 + ((s + (x + 1)·y + (anim >> 2)) & 3)   if DAT_005fb974 else 8
    pixels = strip[s][j] + row·0x400
    if v & 0x2000 and not water:
        tmp = copy(pixels, 0x400)                     # buffer at view+0x3f68
        d = dirt + ((x + 5·y) & 3)·0x400
        for i in 0..0x3ff: if d[i] != 0: tmp[i] = d[i]   # FUN_00457e8d
        pixels = tmp
    return pixels                    # 32 × 32 indices, row-major
```

`anim` is the view's counter at `+0xa88`, incremented once per game tick by
`FUN_0040bdc1` (CONFIRMED; tick rate in [animation](animation.md#14-timing)).
`DAT_005fb974` is a display option that also switches off structure
animation (`FUN_004669e8`, CONFIRMED); INFERRED: the "animation" option. The water test uses the set **before**
animation, so the frame also depends on which of 8–11 the map stored.

**CONFIRMED** (data, `tools/validate_terrain.py`): all 216 maps walk
exactly; the Tiles block is `width · height` u16; every cell names a set
0–12 (5,840,128 cells); bits 14–15 are never set; 15,565 cells carry the
dirt flag; 994,050 are water. **19 cells in 4 maps** name a tile index
past the end of their strip; the game then reads past the bitmap
(undefined). The implementation leaves them black.

## Drawing a flat tile: `FUN_0045c757`

**CONFIRMED.** Used when the four vertex screen positions form an undistorted
32 × 32 square (`FUN_00404eb5` compares them); otherwise `FUN_0045c8ce`
draws a height-displaced tile (next section). Arguments: the screen
position, the four corner light values `L(x,y)`, `L(x+1,y)`, `L(x,y+1)`,
`L(x+1,y+1)` from the terrain light map ([lighting §2](../mechanics/lighting.md)),
the tile pixels and the set's shade table.

```
top = Ltl << 9;  bot = Lbl << 9
for c in 0..31:                               # column by column
    step = (bot − top) / 32                   # C division, truncates toward 0
    v = top + 0x100
    for r in 0..31:
        dst[r][c] = table.row(v >> 9)[tile[r][c]]
        v += step
    top += (Ltr − Ltl)·16
    bot += (Lbr − Lbl)·16
```

Row 64 of the 96-row table is ×1; on flat ground in daylight every corner
is 46 (×1.56, lighting §2 worked example).

## Heights

### Altitudes → runtime height map

**CONFIRMED** (`FUN_0053ea3a` map reader, `FUN_004abc1c` runtime map
builder, `0x4abd2c`–`0x4abea3`):

| Runtime map field | Source |
|---|---|
| `+0x04`, `+0x08` | width, height |
| `+0x0c` | section 1 (Tiles), copied |
| `+0x10` | section 2 (Altitudes), `w·h` bytes copied **verbatim** |
| `+0x14` | zeros, then section 3 copied only for rows `8 … h−5`, columns `8 … w−9` |
| `+0x18` | zeros (filled later with the terrain light map) |

`FUN_00420280` returns `+0x10`. Both readers, the vertex builder
(`FUN_00406658`) and the light map (`FUN_004ad552`), load it with `movsx`,
so **heights are signed bytes**: file values 128–255 are −128…−1. Only one
shipped map, `sc_an_twins2_4_4`, has such values (777 cells, 128–143); the
game draws them as pits.

### Vertex table: `FUN_00406658`

**CONFIRMED.** For the view origin `(vx, vy)` (`view+0x5c`, `+0x60`), view
size `W × Hv` cells (`+0x64`, `+0x68`) and map width `mw` (`+0x84`):

```
for r in −3 … Hv+7, c in −3 … W+3:
    vt[(r+3)·(W+7) + c+3] = 32·r − int8(H[(vy+r)·mw + vx+c])     # view+0xb4
```

x is never displaced: a vertex's screen x is always `32·c`. The routine
also fills `+0xb8` (per cell, min y of the top edge), `+0xbc` (max y of
the bottom edge) and `+0xc0` (the mean height of the four cells around a
vertex, `(a+b+c+d) / 4` truncated toward zero); their users were not
traced (INFERRED: culling and object placement).

So for a whole map, tile `(x, y)` has corners

```
yTL = 32·y − H[y][x]        yTR = 32·y − H[y][x+1]
yBL = 32·(y+1) − H[y+1][x]  yBR = 32·(y+1) − H[y+1][x+1]
```

The game reads `H[y][x+1]` on the last column as the next row's first byte
(flat array) and never shows the map edge; the implementation repeats the
last row and column instead (INFERRED, invisible in play).

### Draw order: `FUN_00404eb5`

**CONFIRMED** (`0x404f1d`–`0x4052ee`): rows `r = 0 … Hv+3` top to bottom
(4 extra rows so raised ground below the view is drawn), and inside a row
columns `c = W−1 … 0`. A tile always covers x `32c … 32c+31`, so only the
row order matters: lower rows overwrite higher ones. The flat test is
`yTL == yTR && yBL == yBR && yTL + 32 == yBL`.

After each tile the exe jumps (`0x40529d`) to a2mgr `Ordinal_65`
(RVA `0xe550`). It only replaces the original optional grid overlay: two
`FUN_0045ba0c` lines along the tile's top and left edges, drawn when a2mgr's
byte `0x1007b670` is set, in colour `0x10078018`. Terrain is unchanged.

### Edge step table: `FUN_0045752b`

**CONFIRMED** (`0x457847`–`0x4578c4`), built once at start-up into
`DAT_00625780` (128 rows × 128 bytes):

```
for n in 1 … 127:
    step = 0x200000 // (n + 1)                     # unsigned
    for k in 0 … n:
        T[n][k] = ((k + 1)·step + 0x8000) >> 16    # ≈ round((k+1)·32 / (n+1))
```

Row 0 stays zero. `T[n][k]` is the tile column at which an edge that moves
`n` pixels across the tile takes its `(k+1)`-th step. Examples:
`T[1] = 16, 32`; `T[2] = 11, 21, 32`; `T[5] = 5, 11, 16, 21, 27, 32`.

### Height-displaced blit: `FUN_0045c8ce`

**CONFIRMED.** Arguments: left x, right x, `yTL, yTR, yBL, yBR`, the corner
lights `TL, TR, BL, BR`, the tile pixels, the shade table. The tile is
drawn **column by column**. Before column `c` (0…31) each edge advances
one pixel for every step whose column has been reached:

```
n = |yTR − yTL|                    # top edge
top(c) = yTL + #{k < n : T[n][k] ≤ c}           if yTL < yTR
       = yTL − #{k < n : 32 − T[n][k] ≤ c}      otherwise
m = |yBR − yBL|                    # bottom edge, rounded the other way
bot(c) = yBL + #{k < m : 32 − T[m][k] ≤ c}      if yBL < yBR
       = yBL − #{k < m : T[m][k] ≤ c}           otherwise
```

Then column `c` is stretched over `span = bot(c) − top(c)` pixels; columns
with `span ≤ 0` (back-facing slopes) are skipped:

```
lt = (TL << 9) + c·(TR − TL)·16           # same light walk as the flat blit
lb = (BL << 9) + c·(BR − BL)·16
vstep = 0x200000 // span;  lstep = (lb − lt) / span      # C division
for i in 0 … span−1:
    row = (i·vstep) >> 16                 # tile texel row, 0…31
    dst[top(c) + i][x + c] = table.row((lt + 0x100 + i·lstep) >> 9)[tile[row][c]]
```

With `span = 32` and flat edges this is exactly the flat blit
(`vstep = 0x10000`, the same light step), so `render_3d` uses this one
routine for every tile. Rows above the clip top are skipped but still
advance the walk; the bottom is clamped to the clip.

- **CONFIRMED** (data): the largest height difference between horizontal
  neighbours is 233, in `sc_an_twins2_4_4` (31 edges over 127); in every
  other map it is at most 127. For `n > 127` the game reads past `T` into
  `DAT_00629780` (the alpha blend tables), which is undefined. The
  implementation extends the formula instead.
- **CONFIRMED** (data): 1,328 vertical cell edges in the install have
  `span ≤ 0` (fully folded columns).

Implementation: `vertex_y`, `edge_offsets`, `tile_columns`, `render_3d` in
`allods2/graphics/terrain.py`; `tools/terrain_render.py MAP [--rect X Y W H]
[--time MIN] [--flat]` → `out/terrain3d/`.

## Worked example

Cell value `0x2265` at map cell (3, 2):

| Field | Value |
|---|---|
| set | `(0x2265 & 0x1fff) >> 6` = `0x265 >> 6` = 9 → water, so the dirt flag is ignored |
| strip | `(0x2265 >> 4) & 3` = 2 |
| row | `0x2265 & 0xf` = 5 |
| frame (anim 0) | `8 + ((9 + 4·2 + 0) & 3)` = 8 + 1 = 9 |
| file | `tile3-06.bmp` (set 9 → `tile3`, `(9 & 3)·4 + 2` = 6), tile 5 = rows 160–191 |

### Worked example: a tile sloping up to the right

`H[y][x] = 0`, `H[y][x+1] = 2`, the row below flat, so `yTL = 0`,
`yTR = −2`, `yBL = yBR = 32`. Top edge: `n = 2`, going up, so it uses
`32 − T[2][k]` = 21, 11: `top(c) = 0` for c < 11, −1 for 11…20, −2 from 21.
Bottom edge flat: `bot(c) = 32`.

| Columns | top | span | vstep | texel rows |
|---|---|---|---|---|
| 0–10 | 0 | 32 | 0x10000 | 0, 1, …, 31 |
| 11–20 | −1 | 33 | 0xf83e | row 0 twice, then 1…31 |
| 21–31 | −2 | 34 | 0xf0f0 | rows 0 and 16 twice |

## Open questions

- What `.alm` section 3 holds (runtime map `+0x14`, copied only inside an
  8-cell border by `FUN_004abc1c`); [inventory](../inventory.md) calls it
  the object layer (INFERRED).
- Who uses the per-cell edge extents `view+0xb8` / `+0xbc` and the vertex
  mean heights `+0xc0` (`FUN_00406658`); INFERRED: culling and placing
  objects on the ground.
- Who calls `FUN_0047b899` and with which mask; what `DAT_00625778 & 2`
  (the `terrain.3d` path) means.
- Which settings control `DAT_005fb974` (gates water and structure
  animation).
- Bits 14–15 (`0xc000`) are masked by the draw code but never set in the
  shipped maps (INFERRED: fog or editor flags).
