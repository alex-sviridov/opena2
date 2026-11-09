# Allods 2 file formats

Reverse-engineered from the GOG release of Rage of Mages II: Necromancer
(1.01, single player; install survey in [inventory](../inventory.md)).
Addresses refer to its `allods2.exe`, sha256
`0eaa9673d74d26dcf245d7233da5757a88769ecfe3cc1a706f34fb4e93c1b0c7`, image
base 0x400000, read in REA (Ghidra 12.1.4) and objdump listings. Game files
are read from the `.res` archives ([res](res.md), library `a2res`).

Facts are marked CONFIRMED (routine checked, or the decoder consumes every
file) or INFERRED, with the routines they came from.

| Format | Document | Status |
|---|---|---|
| `.res` archives, mounting, path lookup (`a2res`) | [res.md](res.md) | CONFIRMED, all 10 archives |
| All graphics types: stats, ranking, dependencies | [graphics-overview.md](graphics-overview.md) | survey; ranks 1–9 CONFIRMED |
| `.256`, `*b.256` (smoothing), `.16a`, `.16` sprites | [sprites.md](sprites.md) | CONFIRMED, all 43,947 sprites |
| Palettes, shade tables, text colours, effect ids | [palettes.md](palettes.md) | CONFIRMED, all 2,854 palettes |
| `.bmp`, portrait canvas | [bitmaps.md](bitmaps.md) | CONFIRMED |
| Terrain: tiles, water, dirt, lit and height-displaced blits | [terrain.md](terrain.md) | CONFIRMED, all 46 campaign maps |
| `.alm` maps: container, General block (header), Tiles/Altitudes/Objects layers, heights and derived passability, objects and structures | [map.md](map.md) | CONFIRMED header, terrain, heights, passability inputs, objects (section 3), structures (section 4, footprints, draw order), players, units, item groups and records (sections 5, 6, 8, 9; part 5) (all 46 campaign maps); scenario sections 7 (triggers), 10 (repop), 11 (inns, shops, signposts), 12 (music zones), part 6 |
| Paper doll: inventory figure layer order | [paperdoll.md](paperdoll.md) | CONFIRMED |
| `fontN.dat` + `.16`/`.16a` fonts, `~` hotkeys | [fonts.md](fonts.md) | CONFIRMED, all 4 fonts |
| `.reg` registry | [reg.md](reg.md) | CONFIRMED, all 17 files |
| `.a2c` characters, `famehall.dat`, `game%d.sav` saved games (client `.reg` tree, Scenario.dll block, server stream head) | [saves.md](saves.md) | CONFIRMED in the exe (readers and writers); `famehall.dat` decodes exactly; no `.a2c` / `.sav` in the install (synthetic tests) |
| Sound and music: RIFF `.wav` PCM / MS ADPCM, `sfx.reg` id table, hero banks, speech names, music playlists (`allods2/formats/sound.py`, `soundtable.py`) | [sound.md](sound.md) | CONFIRMED, all 1,599 files decode exactly; engine side read with REA |
| `units.reg`, unit frame blocks, facing, placement | [units.md](units.md) | CONFIRMED, 59/61 types + 30/30 hero files |
| `world/data/data.bin` game database: records, monster/item/spell parameters, modifier text | [databin.md](databin.md) | CONFIRMED container (file consumed exactly); maps partial |
| Animation: sources, unit layout, timing, `allods2/anim` API, whole-install check, combat handoff | [animation.md](animation.md) | CONFIRMED; 546 sets, 668/740 multi-frame files + 72 listed exclusions (47 town/world-map files open) |

Data tables built on these formats: [../data/](../data/README.md).

Open questions: [../open-questions.md](../open-questions.md). Mechanics:
[../mechanics/](../mechanics/README.md). Install survey, binary triage,
reversing plan: [../inventory.md](../inventory.md).
