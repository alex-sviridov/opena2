# Allods 2 file formats

Reverse-engineered from the shipped `allods2.exe` (English 1.30 build).
Each fact is marked CONFIRMED (exe routine via REA, or decodes every file)
or INFERRED, with the routines it was derived from, so claims can be
re-checked against the binary.

| Format | Document | Status |
|---|---|---|
| All graphics types: stats, ranking, dependencies | [graphics-overview.md](graphics-overview.md) | Survey; ranks 1–8 CONFIRMED |
| `.256`, `*b.256` (smoothing), `.16a`, `.16` sprites | [sprites.md](sprites.md) | Decoding CONFIRMED on all game files; some draw variants open |
| Palettes (embedded, `.pal`, `human.pal`, BMP, built in code), shade tables, day/night tint | [palettes.md](palettes.md) | CONFIRMED: all 2,973 palettes parse; FUN_00425bee conversion; text-colour users open |
| `.bmp` | [bitmaps.md](bitmaps.md) | Verified |
| Terrain: `.alm` Tiles block → `tile<g>-<nn>.bmp` strips, water animation, dirt overlay, flat lit blit | [terrain.md](terrain.md) | CONFIRMED: FUN_0047b899, FUN_00404eb5, FUN_0045c757; all 216 maps |
| `.png` (a2mgr paper-doll layers, menu art): lookup order, 160 × 240 rule, alpha blend | [png.md](png.md) | CONFIRMED: a2mgr Ordinal_102/103, FUN_10010d70; all 536 files |
| `fontN.dat` + `.16`/`.16a` fonts: metrics, char map, text layout, `~` hotkeys, a2mgr `%[...]` colours | [fonts.md](fonts.md) | CONFIRMED: all 4 fonts; FUN_00461e19, 0x4637f1 + a2mgr Ordinal_125/126, FUN_00463bbd |
| `.reg` (unit/structure metadata) | [../inventory.md §5.1](../inventory.md#51-reg-registry-ya1) | Header CONFIRMED (FUN_004ed6cc, all 17 files); entries open |

Game mechanics (lighting, …): [../mechanics/](../mechanics/README.md).

Install survey, binary triage and the reversing plan: [../inventory.md](../inventory.md).
