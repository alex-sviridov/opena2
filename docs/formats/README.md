# Allods 2 file formats

Reverse-engineered from the shipped `allods2.exe` (English 1.30 build).
Each fact is marked CONFIRMED (exe routine via REA, or decodes every file)
or INFERRED, with the routines it was derived from, so claims can be
re-checked against the binary.

| Format | Document | Status |
|---|---|---|
| All graphics types: stats, ranking, dependencies | [graphics-overview.md](graphics-overview.md) | Survey; ranks 1–10 CONFIRMED |
| `.256`, `*b.256` (smoothing), `.16a`, `.16` sprites | [sprites.md](sprites.md) | Decoding CONFIRMED on all game files; some draw variants open |
| Palettes (embedded, `.pal`, `human.pal`, BMP, built in code), shade tables, day/night tint | [palettes.md](palettes.md) | CONFIRMED: all 2,973 palettes parse; FUN_00425bee conversion; text-colour users open |
| `.bmp` | [bitmaps.md](bitmaps.md) | Verified |
| Terrain: `.alm` Tiles block → `tile<g>-<nn>.bmp` strips, water animation, dirt overlay, flat lit blit | [terrain.md](terrain.md) | CONFIRMED: FUN_0047b899, FUN_00404eb5, FUN_0045c757; all 216 maps |
| `.png` (a2mgr paper-doll layers, menu art): lookup order, 160 × 240 rule, alpha blend | [png.md](png.md) | CONFIRMED: a2mgr Ordinal_102/103, FUN_10010d70; all 536 files |
| `fontN.dat` + `.16`/`.16a` fonts: metrics, char map, text layout, `~` hotkeys, a2mgr `%[...]` colours | [fonts.md](fonts.md) | CONFIRMED: all 4 fonts; FUN_00461e19, 0x4637f1 + a2mgr Ordinal_125/126, FUN_00463bbd |
| `.reg` registry: layout, entry types, lookup rules | [reg.md](reg.md) | CONFIRMED: FUN_004ed6cc, FUN_004f1f4e; all 17 files |
| Unit animation: `units.reg` fields, frame blocks, facing/mirroring, placement | [units.md](units.md) | CONFIRMED: FUN_0047f108, FUN_00468640; 59/62 units exact |
| Animation sources (part 1): structures/objects/projectiles/heroes registries, draw inputs, phase counters, tick rate | [animation.md](animation.md) | CONFIRMED: loaders FUN_00482e99, FUN_0047e4a0, FUN_004824cc; ticks FUN_0040bdc1, FUN_00492068; all 179 structures exact |

All open questions, across specs: [../open-questions.md](../open-questions.md).

Game mechanics (lighting, …): [../mechanics/](../mechanics/README.md).

Install survey, binary triage and the reversing plan: [../inventory.md](../inventory.md).
