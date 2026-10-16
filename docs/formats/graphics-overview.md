# Graphics formats: overview

Survey of every graphics file type, ranked simplest to hardest, with
dependencies. `tools/gfx_survey.py` writes `out/gfx/stats.txt` and hex
dumps (first 128 / last 32 bytes of the 5 smallest and 5 largest non-empty
files) to `out/gfx/dumps/<ext>/`. Requested as a first all-INFERRED pass;
most formats were decoded before it was written, so the specs win and the
Status column gives their markers.

## 1. Statistics

Bytes, over every file in the install's archives (`tools/gfx_survey.py`).
`b.256` = a `.256` with a same-named sibling without the `b` (smoothing
overlays, plus `interface/radiob.256`).

| Ext | Files | Min | Median | Max | Folders (files) | Names suggest |
|---|---:|---:|---:|---:|---|---|
| `.256` | 1,534 | 0 | 2,423 | 456,066 | equipment 1,104, structures 163, objects 135, units 89, cursors 23, interface 12, projectiles 7, backpack 1 | paper-doll layers (`<id>.256`), buildings, trees/rocks (`sprites.256`, `dead/`), units, cursors, UI widgets |
| `b.256` | 395 | 1,059 | 2,329 | 100,649 | structures, objects, units, projectiles, backpack | `b` twin of each world sprite |
| `.16a` | 623 | 1,042 | 4,656 | 213,104 | inventory 491, interface 73, projectiles 29, cursors 23, global.map 6, font4 1 | item icons, UI and town scenes, spell effects, cursors, world-map flags, a font |
| `.16` | 3 | 1,100 | 9,436 | 32,932 | font1–3 | fonts |
| `.pal` | 159 | 1,086 | 17,462 | 26,678 | units 157, projectiles 2 | `palette<N>.pal` per unit, `human.pal` |
| `.bmp` | 1,515 | 104 | 29,286 | 921,656 | interface 1,076, infowindow 185, movies 156, terrain 53, main 34, global.map 11 | UI and town screens, portraits, shop pictures, terrain strips, menus, world map |
| `.dat` (graphics) | 5 | 3 | 896 | 896 | font1–4, interface | glyph metrics; `interface/data.dat` |

Eight `.256` are 0 bytes (4 cursors, 4 equipment).

## 2. Formats, ranked

| Order | Ext | Purpose | Count | Difficulty | Needs | Status |
|---:|---|---|---:|---|---|---|
| 1 | `.pal` | unit/projectile palettes; `human.pal` player colours | 159 | trivial | none | CONFIRMED, [palettes](palettes.md) |
| 2 | `.bmp` | UI, portraits, shop pictures, terrain tiles | 1,515 | trivial (standard DIB) | terrain: 32×32 tiles stacked vertically | CONFIRMED, [bitmaps](bitmaps.md) |
| 3 | `fontN.dat` | glyph widths | 4 | trivial | `.16`/`.16a` glyphs | CONFIRMED, [fonts](fonts.md) |
| 4 | `.16` | 4-bit fonts | 3 | easy | 16-entry colour table from the caller | CONFIRMED, [sprites](sprites.md) |
| 5 | `.256` | world sprites, equipment, cursors, UI | 1,534 | medium | palette (embedded, unit `.pal`, or `human.pal[player]`); shade tables | CONFIRMED, [sprites](sprites.md) |
| 6 | `b.256` | edge-smoothing overlays (not shadows) | 395 | medium | main sprite's palette and frame; 50 % blend; Smoothing option | CONFIRMED, [sprites](sprites.md) |
| 7 | `.16a` | icons, spell effects, UI, a font | 623 | medium | FADE16 table of its palette (alpha = row) | CONFIRMED, [sprites](sprites.md), [palettes §5](palettes.md) |
| 8 | terrain (composite) | map ground | 52 tiles + `dirt.bmp` | hard | `.alm` sections 1–2, tile flags, [lighting](../mechanics/lighting.md) | CONFIRMED (cells, strips, water, dirt, lit blit, signed heights, displaced blit), [terrain](terrain.md) |
| 9 | unit animation (composite) | units on the map | 89 sprite sets | hard | `.reg`, palettes, mirroring, shadow shear | CONFIRMED, [units](units.md), [reg](reg.md), [animation](animation.md) |

Not covered here: `.smk` cut-scenes (`video.res`, standard Smacker).

## 3. Dependencies

```
.pal ──► .256 ──► b.256
  │        └────► unit animation ◄── .reg (units.reg)
  ├──► .16a (FADE16 tables)
  └──► shade tables ◄── day/night tint, light maps (mechanics/lighting.md)
.bmp ──► terrain ◄── .alm (Tiles, Altitudes)
fontN.dat ──► text rendering ◄── .16 / .16a fonts + code colour tables
```

## Open questions

None of its own; see [../open-questions.md](../open-questions.md).
