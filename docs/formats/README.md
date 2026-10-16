# Allods 2 file formats

Reverse-engineered from the English 1.30 build. Unless a spec says
otherwise, addresses refer to `allods2.exe` sha256
`2a8bdf9dc69276cc8d4fee561a7473a6b0f709cf9758abddaf2cd3b1fdfdfe43` and
a2mgr addresses (`0x10…`, `Ordinal_N`) to the community patch `a2mgr.dll`
sha256 `6bc57ebba86d4a2a7b8505bef9099c17652009fcb0f7a147fee6b2aa29077cc6`
(image base 0x10000000), read in REA (Ghidra 12.1.4) and objdump
listings. Facts are marked CONFIRMED (routine checked, or decodes every
file) or INFERRED, with the routines they came from.

| Format | Document | Status |
|---|---|---|
| All graphics types: stats, ranking, dependencies | [graphics-overview.md](graphics-overview.md) | survey; ranks 1–10 CONFIRMED |
| `.256`, `*b.256` (smoothing), `.16a`, `.16` sprites | [sprites.md](sprites.md) | CONFIRMED, all 43,051 sprites |
| Palettes, shade tables, text colours, effect ids | [palettes.md](palettes.md) | CONFIRMED, all 2,973 palettes |
| `.bmp`, portrait canvas | [bitmaps.md](bitmaps.md) | CONFIRMED |
| Terrain: tiles, water, dirt, lit and height-displaced blits | [terrain.md](terrain.md) | CONFIRMED, all 216 maps |
| `.png` (a2mgr paper doll, menu art) | [png.md](png.md) | CONFIRMED, all 536 files |
| `fontN.dat` + `.16`/`.16a` fonts, `~` hotkeys, `%[...]` colours | [fonts.md](fonts.md) | CONFIRMED, all 4 fonts |
| `.reg` registry | [reg.md](reg.md) | CONFIRMED, all 17 files |
| `units.reg`, unit frame blocks, facing, placement | [units.md](units.md) | CONFIRMED, 59/62 types + 30/30 hero files |
| Animation: sources, unit layout, timing (client and server), `allods2/anim` API, whole-install check, combat handoff | [animation.md](animation.md) | CONFIRMED; 546 sets, 668/695 multi-frame files + 27 documented exclusions |

Open questions: [../open-questions.md](../open-questions.md). Mechanics:
[../mechanics/](../mechanics/README.md). Install survey, binary triage,
reversing plan: [../inventory.md](../inventory.md).
