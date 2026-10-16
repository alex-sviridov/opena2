# Graphics formats: overview

Survey of every graphics file type, ranked simplest to hardest, with
dependencies. `tools/gfx_survey.py` writes `out/gfx/stats.txt` and hex
dumps (first 128 / last 32 bytes of the 5 smallest and 5 largest non-empty
files) to `out/gfx/dumps/<ext>/`. Requested as a first all-INFERRED pass;
most formats were decoded before it was written, so the specs win and the
Status column gives their markers.

## 1. Statistics

Bytes. `b.256` = a `.256` with a same-named sibling without the `b`
(smoothing overlays, plus `interface/radiob.256`).

| Ext | Files | Min | Median | Max | Folders (files) | Names suggest |
|---|---:|---:|---:|---:|---|---|
| `.256` | 1,535 | 0 | 2,424 | 458,099 | equipment 1,104, structures 163, objects 135, units 90, cursors 23, interface 12, projectiles 7, backpack 1 | paper-doll layers (`<id>.256`), buildings, trees/rocks (`sprites.256`, `dead/`), units, cursors, UI widgets |
| `b.256` | 396 | 1,059 | 2,333 | 104,501 | structures 163, objects 135, units 90, projectiles 7, backpack 1 | `b` twin of each world sprite |
| `.16a` | 782 | 1,042 | 4,435 | 119,656 | inventory 697, interface 30, projectiles 29, cursors 23, global.map 2, font4 1 | item icons, UI, spell effects, cursors, map flags, a font |
| `.16` | 3 | 1,100 | 9,599 | 15,537 | font1–3 | fonts |
| `.pal` | 166 | 1,086 | 17,462 | 26,680 | units 164, projectiles 2 | `palette<N>.pal` per unit, `human.pal` |
| `.bmp` | 1,012 | 104 | 40,182 | 921,656 | interface 598, infowindow 190, movies 156, terrain 53, locale 15 | UI screens, portraits, shop animation frames, terrain strips |
| `.png` | 536 | 487 | 6,106 | 306,055 | equipment 516, locale 20 | post-release items (allods2.eu), localized UI |
| `.dat` (graphics) | 5 | 13 | 896 | 896 | font1–4, interface | glyph metrics; `interface/data.dat` = text date stamp |

Eight `.256` are 0 bytes (4 cursors, 4 equipment). No `.res` archives:
everything is loose under `data/` ([inventory §4](../inventory.md)).

## 2. Formats, ranked

| Order | Ext | Purpose | Count | Difficulty | Needs | Status |
|---:|---|---|---:|---|---|---|
| 1 | `.pal` | unit/projectile palettes; `human.pal` player colours | 166 | trivial | none | CONFIRMED, [palettes](palettes.md) |
| 2 | `.bmp` | UI, portraits, shop frames, terrain tiles | 1,012 | trivial (standard DIB) | terrain: 32×32 tiles stacked vertically | CONFIRMED, [bitmaps](bitmaps.md) |
| 3 | `.png` | post-release equipment (160 × 240), localized UI | 536 | trivial (standard) | a2mgr: `.png` before `.256`; float alpha into RGB565 | CONFIRMED, [png](png.md) |
| 4 | `fontN.dat` | glyph widths | 4 | trivial | `.16`/`.16a` glyphs | CONFIRMED, [fonts](fonts.md) |
| 5 | `.16` | 4-bit fonts | 3 | easy | 16-entry colour table from the caller | CONFIRMED, [sprites](sprites.md) |
| 6 | `.256` | world sprites, equipment, cursors, UI | 1,535 | medium | palette (embedded, unit `.pal`, or `human.pal[player]`); shade tables | CONFIRMED, [sprites](sprites.md) |
| 7 | `b.256` | edge-smoothing overlays (not shadows) | 396 | medium | main sprite's palette and frame; 50 % blend; Smoothing option | CONFIRMED, [sprites](sprites.md) |
| 8 | `.16a` | icons, spell effects, UI, a font | 782 | medium | FADE16 table of its palette (alpha = row) | CONFIRMED, [sprites](sprites.md), [palettes §5](palettes.md) |
| 9 | terrain (composite) | map ground | 52 tiles + `dirt.bmp` | hard | `.alm` sections 1–2, tile flags, [lighting](../mechanics/lighting.md) | CONFIRMED (cells, strips, water, dirt, lit blit, signed heights, displaced blit), [terrain](terrain.md) |
| 10 | unit animation (composite) | units on the map | 90 sprite sets | hard | `.reg`, palettes, mirroring, shadow shear | CONFIRMED, [units](units.md), [reg](reg.md), [animation](animation.md) |

Not graphics in this install: `.smk` video and `.res` archives (absent).

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
