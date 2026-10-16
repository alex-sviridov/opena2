# Terrain: `.alm` Tiles block → `tile<g>-<nn>.bmp` strips

Code: `allods2/alm.py` (container), `allods2/graphics/terrain.py`. Tools:
`tools/validate_terrain.py`; `tools/terrain_contact.py` →
`out/contact/terrain.png` (all strips, map thumbnails);
`tools/tile_contact.py` → `out/contact/tiles_<set>.png` (each tile
labelled with its cell value `tr.cell_value(set, strip, row)`; add
`0x2000` for dirt); one tile as RGBA:
`TerrainSet.tile_rgba(set, strip, row, light=None)`.

The ground is a grid of 32 × 32 8-bit tiles; each cell holds a u16 in the
`.alm` Tiles block (section 1, [inventory §5.2](../inventory.md)) selecting
a set, one of its four strip bitmaps, and a tile in the strip.

## Strip files: `FUN_0047b899(mask)`

CONFIRMED. For each bit `t` (0..31) in `mask`, four 8-bit BMPs →
`DAT_00630b90[t][j]`:

```
name(t, j) = "graphics\terrain\tile%d-%02d.bmp" % ((t >> 2) + 1, (t & 3)·4 + j)
```

(The exe uses `tile%d-0%d.bmp` below 10 and `tile%d-%d.bmp` above, strings
`0x5fbcac`/`0x5fbccc`.) A non-zero mask also loads
`graphics\terrain\dirt.bmp` → `DAT_00630da4`. Each set gets a 96-row
BRIGHT32 table from its first strip's palette
(`FUN_00426be0(0x60, 3, 1)` → `DAT_0062ca78[t]`; [palettes §5](palettes.md),
[lighting](../mechanics/lighting.md)).

| Set `t` | Files | Strip | Tiles/strip |
|---|---|---|---|
| 0–3 | `tile1-00` … `tile1-15` | 32 × 448 | 14 |
| 4–7 | `tile2-00` … `tile2-15` | 32 × 448 | 14 |
| 8–11 | `tile3-00` … `tile3-15` | 32 × 256 | 8 (water, 4 animation frames) |
| 12 | `tile4-00` … `tile4-03` | 32 × 448 | 14 |
| — | `dirt.bmp` | 32 × 128 | 4 dirt overlays |

- CONFIRMED (data): all 52 strips exist and share one palette; `dirt.bmp`
  has its own, but its indices are pasted into tile memory, so they are
  read with the tile palette.
- CONFIRMED (`FUN_004280d4`, [bitmaps](bitmaps.md)): rows are flipped
  after loading, so tile `r` is the r-th 32-row block from the **top**.
- CONFIRMED dead code: when `DAT_00625778 & 2`, sets are first loaded from
  `graphics\terrain.3d\` (strings `0x5fbc28`…`0x5fbc6c`), then replaced by
  `graphics\terrain\`. `DAT_00625778` is written once, to 0 (`0x48695a`);
  its three other references only read it; a2mgr never touches it. No
  `terrain.3d` folder in this install.
- Callers (CONFIRMED): `FUN_0041dd29` passes map `+0x28`, which
  `FUN_004abc1c` sets to `0x1fff` (`0x4abd16`): every map loads all 13
  sets. `FUN_0047be70` passes 0.

## Cell value

CONFIRMED (`FUN_00404eb5`, `0x405035`–`0x405185`): bits 0–3 (`0x000f`)
tile in strip (`· 0x400` bytes); 4–5 (`0x0030`) strip `j`; 6–12
(`0x1fc0`) set `t`; 13 (`0x2000`) dirt overlay
(ignored on water); 14–15 (`0xc000`) masked off by the terrain draw
(`& 0x1fff` / `& 0xffff1fff`), = run-time fog of war: `0x8000` explored,
`0x4000` visible now, set from sight every 32 ticks by `FUN_0040c212` →
`FUN_00465e36` ([animation §1.6](animation.md#16-visibility-gates)).

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

`anim` = view counter `+0xa88`, +1 per tick (`FUN_0040bdc1`;
[animation §1.4](animation.md#14-timing)). `DAT_005fb974` = **Object
animations** option ([lighting §6](../mechanics/lighting.md#6-options));
it also freezes structures, objects and projectile lights. The water test
uses the stored set, so the frame depends on which of 8–11 the map stored.

CONFIRMED (data): all 216 maps walk exactly; Tiles = `width · height` u16;
every cell names set 0–12 (5,840,128 cells); bits 14–15 never set; 15,565
dirt cells; 994,050 water. **19 cells in 4 maps** name a tile past their
strip (game reads past the bitmap; implementation leaves them black).

## Drawing a flat tile: `FUN_0045c757`

CONFIRMED. Used when the four vertex positions form an undistorted 32 × 32
square (else `FUN_0045c8ce`, below). Args: screen position, corner lights
`L(x,y)`, `L(x+1,y)`, `L(x,y+1)`, `L(x+1,y+1)` from the terrain light map
([lighting §2](../mechanics/lighting.md)), tile pixels, shade table.

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

Row 64 is ×1; flat ground in daylight has every corner at 46 (×1.56).

## Heights

### Altitudes → runtime height map

CONFIRMED (`FUN_0053ea3a` map reader, `FUN_004abc1c` runtime map builder,
`0x4abd2c`–`0x4abea3`): `+0x04`/`+0x08` width, height; `+0x0c` section 1
(Tiles); `+0x10` section 2 (Altitudes), `w·h` bytes **verbatim**; `+0x14`
zeros, then section 3 copied only for rows `8 … h−5`, columns `8 … w−9`
(object layer, byte = object index + 1,
[animation §1.7](animation.md#17-map-placement-of-objects)); `+0x18` zeros
(later the terrain light map). `FUN_00420280` returns `+0x10`; the vertex
builder (`FUN_00406658`) and light map (`FUN_004ad552`) read it with
`movsx`: **heights are signed bytes** (128–255 = −128…−1). Only
`sc_an_twins2_4_4` has such values (777 cells, 128–143), drawn as pits.

### Vertex table: `FUN_00406658`

CONFIRMED. View origin `(vx, vy)` (`view+0x5c/+0x60`), size `W × Hv`
cells (`+0x64/+0x68`), map width `mw` (`+0x84`):

```
for r in −3 … Hv+7, c in −3 … W+3:
    vt[(r+3)·(W+7) + c+3] = 32·r − int8(H[(vy+r)·mw + vx+c])     # view+0xb4
```

x is never displaced (`32·c`). Also fills `+0xb8` (per cell, min y of the
top edge), `+0xbc` (max y of the bottom edge), `+0xc0` (mean of the four
heights around a vertex, `(a+b+c+d)/4` truncated toward zero). Users
(CONFIRMED): `+0xc0` per cell by every view-draw layer (`0x407d4d`,
`0x407fe7`, `0x40832c`, `0x408637`, `0x408ac3`, `0x4098a1`, `0x409db0`,
`0x409fd6`; for objects the relief subtracted from the top, `0x408ac3` →
`0x409276`, [animation §4.3](animation.md#43-objects)); `+0xb8/+0xbc` for
redraw rectangles (`FUN_004040e2`, ± 0x60 px), draw spans
(`FUN_00406981`, `FUN_00406c9e`) and culling (`0x409628`, `0x409b61`).

Tile `(x, y)` corners: `yTL = 32·y − H[y][x]`, `yTR = 32·y − H[y][x+1]`,
`yBL = 32·(y+1) − H[y+1][x]`, `yBR = 32·(y+1) − H[y+1][x+1]`. On the last
column the game reads the next row's first byte (flat array), never
shown; the implementation repeats the last row/column (INFERRED,
invisible).

### Draw order: `FUN_00404eb5`

CONFIRMED (`0x404f1d`–`0x4052ee`): rows `0 … Hv+3` top to bottom (4 extra
so raised ground below the view is drawn), columns `W−1 … 0`. A tile
always spans x `32c … 32c+31`, so lower rows overwrite higher ones. Flat
test: `yTL == yTR && yBL == yBR && yTL + 32 == yBL`. After each tile the
exe jumps (`0x40529d`) to a2mgr `Ordinal_65` (RVA `0xe550`), which only
replaces the optional grid overlay: two `FUN_0045ba0c` lines along the
top and left edges when a2mgr byte `0x1007b670` is set, colour
`0x10078018`.

### Edge step table: `FUN_0045752b`

CONFIRMED (`0x457847`–`0x4578c4`), built at start-up into `DAT_00625780`
(128 × 128 bytes, row 0 zero):

```
for n in 1 … 127:
    step = 0x200000 // (n + 1)                     # unsigned
    for k in 0 … n:
        T[n][k] = ((k + 1)·step + 0x8000) >> 16    # ≈ round((k+1)·32 / (n+1))
```

`T[n][k]` = column where an edge moving `n` px across the tile takes its
`(k+1)`-th step: `T[1] = 16, 32`; `T[2] = 11, 21, 32`;
`T[5] = 5, 11, 16, 21, 27, 32`.

### Height-displaced blit: `FUN_0045c8ce`

CONFIRMED. Args: left x, right x, `yTL, yTR, yBL, yBR`, corner lights,
tile, table. Column by column; before column `c` each edge advances one
pixel per reached step:

```
n = |yTR − yTL|                    # top edge
top(c) = yTL + #{k < n : T[n][k] ≤ c}           if yTL < yTR
       = yTL − #{k < n : 32 − T[n][k] ≤ c}      otherwise
m = |yBR − yBL|                    # bottom edge, rounded the other way
bot(c) = yBL + #{k < m : 32 − T[m][k] ≤ c}      if yBL < yBR
       = yBL − #{k < m : T[m][k] ≤ c}           otherwise
```

Column `c` is stretched over `span = bot(c) − top(c)`; `span ≤ 0`
(back-facing) is skipped:

```
lt = (TL << 9) + c·(TR − TL)·16           # same light walk as the flat blit
lb = (BL << 9) + c·(BR − BL)·16
vstep = 0x200000 // span;  lstep = (lb − lt) / span      # C division
for i in 0 … span−1:
    row = (i·vstep) >> 16                 # tile texel row, 0…31
    dst[top(c) + i][x + c] = table.row((lt + 0x100 + i·lstep) >> 9)[tile[row][c]]
```

With `span = 32` and flat edges this equals the flat blit
(`vstep = 0x10000`), so `render_3d` uses it for every tile. Rows above
the clip are skipped but advance the walk; the bottom is clamped.

- CONFIRMED (data): largest horizontal-neighbour height difference 233
  (`sc_an_twins2_4_4`, 31 edges over 127); ≤ 127 in every other map. For
  `n > 127` the game reads past `T` into `DAT_00629780` (alpha blend
  tables, undefined); the implementation extends the formula.
- CONFIRMED (data): 1,328 vertical cell edges have `span ≤ 0`.

Implementation: `vertex_y`, `edge_offsets`, `tile_columns`, `render_3d`;
`tools/terrain_render.py MAP [--rect X Y W H] [--time MIN] [--flat]` →
`out/terrain3d/`.

## Worked example

Cell `0x2265` at (3, 2): set `0x265 >> 6` = 9 → water (dirt flag
ignored); strip `(0x2265 >> 4) & 3` = 2; row 5; frame at anim 0 =
`8 + ((9 + 4·2) & 3)` = 9; file `tile3-06.bmp` (`(9 & 3)·4 + 2`), tile 5 =
rows 160–191.

Slope up to the right: `H[y][x] = 0`, `H[y][x+1] = 2`, row below flat →
`yTL = 0`, `yTR = −2`, `yBL = yBR = 32`. Top edge `n = 2`, rising, uses
`32 − T[2][k]` = 21, 11: `top(c)` = 0 for c < 11, −1 for 11…20, −2 from
21; `bot = 32`:

| Columns | top | span | vstep | texel rows |
|---|---|---|---|---|
| 0–10 | 0 | 32 | 0x10000 | 0…31 |
| 11–20 | −1 | 33 | 0xf83e | row 0 twice, then 1…31 |
| 21–31 | −2 | 34 | 0xf0f0 | rows 0 and 16 twice |

## Open questions

None at present.
