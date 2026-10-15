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

`anim` is the view's counter at `+0xa88`; `DAT_005fb974` is a display option
(INFERRED: "animated water"). The water test uses the set **before**
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
draws a height-displaced tile (not covered here). Arguments: the screen
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

## Worked example

Cell value `0x2265` at map cell (3, 2):

| Field | Value |
|---|---|
| set | `(0x2265 & 0x1fff) >> 6` = `0x265 >> 6` = 9 → water, so the dirt flag is ignored |
| strip | `(0x2265 >> 4) & 3` = 2 |
| row | `0x2265 & 0xf` = 5 |
| frame (anim 0) | `8 + ((9 + 4·2 + 0) & 3)` = 8 + 1 = 9 |
| file | `tile3-06.bmp` (set 9 → `tile3`, `(9 & 3)·4 + 2` = 6), tile 5 = rows 160–191 |

## Open questions

- The height-displaced blit `FUN_0045c8ce` and the vertex table at view
  `+0xb4` (screen y per vertex from the `.alm` altitudes): needed for 3D
  relief. The terrain row loop itself is hooked by a2mgr (`Ordinal_65` at
  0x40529d), which was not read.
- Who calls `FUN_0047b899` and with which mask; what `DAT_00625778 & 2`
  (the `terrain.3d` path) means.
- The meaning of `DAT_005fb974` (water animation option) and how fast
  `view+0xa88` advances.
- Bits 14–15 (`0xc000`) are masked by the draw code but never set in the
  shipped maps (INFERRED: fog or editor flags).
