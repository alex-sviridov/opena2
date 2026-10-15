# Allods 2 file formats

Reverse-engineered from the shipped `allods2.exe` (English 1.30 build).
Each fact is marked CONFIRMED (exe routine via REA, or decodes every file)
or INFERRED, with the routines it was derived from, so claims can be
re-checked against the binary.

| Format | Document | Status |
|---|---|---|
| `.256`, `*b.256` (smoothing), `.16a`, `.16` sprites | [sprites.md](sprites.md) | Decoding CONFIRMED on all game files; some draw variants open |
| Palettes (embedded, `.pal`, `human.pal`, BMP, built in code), shade tables, day/night tint | [palettes.md](palettes.md) | CONFIRMED: all 2,973 palettes parse; FUN_00425bee conversion; lighting row selection open |
| `.bmp` | [bitmaps.md](bitmaps.md) | Verified |
| `.reg` (unit/structure metadata) | [../inventory.md §5.1](../inventory.md#51-reg-registry-ya1) | Header CONFIRMED (FUN_004ed6cc, all 17 files); entries open |

Install survey, binary triage and the reversing plan: [../inventory.md](../inventory.md).
