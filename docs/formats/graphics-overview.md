# Graphics formats: overview

A high-level survey of every graphics file type in the install, ranked
from simplest to hardest, with dependencies. Generated with
`.venv/bin/python tools/gfx_survey.py`, which writes `out/gfx/stats.txt`
and hex dumps (first 128 and last 32 bytes of the 5 smallest and 5
largest non-empty files) to `out/gfx/dumps/<ext>/`.

**Status note.** This survey was requested as a first, all-INFERRED pass
before any decoding. In this repo most formats were decoded before the
overview was written, so the "Status" column links the spec and gives its
current marker. The header and encoding columns describe what a first
look at the dumps shows. Where a spec exists, the spec wins.

## 1. Statistics

Sizes are in bytes. `b.256` is a `.256` file with a sibling of the same name
without the `b` (smoothing overlays, plus `interface/radiob.256`).

| Ext | Files | Min | Median | Max | Folders (files) | Names suggest |
|---|---:|---:|---:|---:|---|---|
| `.256` | 1,535 | 0 | 2,424 | 458,099 | equipment 1,104, structures 163, objects 135, units 90, cursors 23, interface 12, projectiles 7, backpack 1 | paper-doll item layers (`<id>.256`), buildings (`house.256`), trees and rocks (`sprites.256`, `dead/`), unit animations, cursors, UI widgets |
| `b.256` | 396 | 1,059 | 2,333 | 104,501 | structures 163, objects 135, units 90, projectiles 7, backpack 1 | the `b` twin of each world sprite |
| `.16a` | 782 | 1,042 | 4,435 | 119,656 | inventory 697, interface 30, projectiles 29, cursors 23, global.map 2, font4 1 | item icons (`<id>.16a`), UI, spell effects, cursors, map flags, one font |
| `.16` | 3 | 1,100 | 9,599 | 15,537 | font1–3 | fonts |
| `.pal` | 166 | 1,086 | 17,462 | 26,680 | units 164, projectiles 2 | `palette<N>.pal` per unit, `human.pal` |
| `.bmp` | 1,012 | 104 | 40,182 | 921,656 | interface 598, infowindow 190, movies 156, terrain 53, locale 15 | UI screens, portraits, shop animation frames, terrain tile strips |
| `.png` | 536 | 487 | 6,106 | 306,055 | equipment 516, locale 20 | post-release items (allods2.eu patch), localized UI |
| `.dat` (graphics) | 5 | 13 | 896 | 896 | font1–4, interface | glyph metrics; `interface/data.dat` is a text date stamp |

Eight `.256` files are 0 bytes (4 cursors, 4 equipment). The install has no
`.res` archives: everything is a loose file under `data/`
([inventory §4](../inventory.md)).

## 2. What the dumps show

- **`.256`, `b.256`, `.16a`**: most start with `00 00 00 00` followed by
  4-byte groups ending in `00`, i.e. a 256 × BGR0 palette (1,024 bytes).
  The **last 4 bytes** are a little-endian count with bit 31 set (for
  example `01 00 00 80` = 1 frame, palette present). There is no header
  at the start. Before the trailer, each frame is `{u32 w, u32 h, u32 size}`
  followed by data. The data has many bytes with the top bits `0x80` /
  `0x40` and small low bits (`81 01 fe bf bf 02 …`), which looks like
  skip/copy RLE control bytes. In `.16a`, the 16-bit words with
  `0x8000` / `0x4000` flags suggest RLE over 16-bit pixel words.
- **`.16`**: no palette. It starts directly with `{w, h, size}` (`10 00 00 00
  0f 00 00 00 …`). The data bytes look nibble-packed (`bf 8e 01 bf …`),
  suggesting a 4-bit RLE.
- **`.pal`**: `BM` header, `bfOffBits` 0x436, 8-bit BMP, so the colour
  table is at 0x36. `human.pal` is 16,384 bytes with no header (16 × 1,024).
- **`.bmp`**: standard `BM` DIBs: 949 are 24-bit, 63 are 8-bit, none
  compressed.
- **`.png`**: standard RGBA PNGs.
- **`fontN.dat`**: 896 bytes = 224 × u32 (characters 0x20–0xFF) of small
  values, i.e. glyph widths. `font3.dat` is 256 bytes = 64 × u32.

## 3. Formats, ranked

Order 1 is the simplest. "Needs" lists what a decoder or renderer depends
on.

| Order | Ext | Purpose | Count | Header summary | Pixel encoding | Difficulty | Needs | Status |
|---:|---|---|---:|---|---|---|---|---|
| 1 | `.pal` | unit and projectile palettes; `human.pal` player colours | 166 | 54-byte BMP header, table at 0x36; `human.pal` raw 16 × 1,024 | 256 × BGR0, 8-bit channels | trivial | none | CONFIRMED, [palettes](palettes.md) |
| 2 | `.bmp` | UI, portraits, shop frames, terrain tiles | 1,012 | standard DIB | 24-bit or 8-bit indexed, bottom-up | trivial (standard) | terrain: 32×32 tiles stacked vertically | CONFIRMED, [bitmaps](bitmaps.md) |
| 3 | `.png` | post-release equipment, localized UI | 536 | standard | RGBA; equipment 160 × 240 | trivial (standard) | a2mgr: `<path>.png` tried before `<path>.256`; float alpha blend into the RGB565 doll buffer | CONFIRMED, [png](png.md) |
| 4 | `fontN.dat` | glyph widths | 4 | none; 224 or 64 × u32 | metrics, no pixels: `width[g]` = last ink column | trivial | the `.16`/`.16a` glyph sprites | CONFIRMED, [fonts](fonts.md) |
| 5 | `.16` | 4-bit fonts | 3 | no palette; trailer count; `{w, h, size}` per glyph | 4-bit RLE, nibble-packed, value = colour slot 0–15 | easy | a 16-entry colour table from the caller (code ramps, [palettes §6](palettes.md)) | CONFIRMED, [sprites](sprites.md) |
| 6 | `.256` | world sprites, equipment layers, cursors, UI | 1,535 | optional 1,024-byte palette; frames `{w, h, size}`; trailer `count | 0x80000000` | 8-bit indexed RLE (skip/copy/row-skip control bytes) | medium | a palette: embedded, a unit `palette<N>.pal`, or `human.pal[player]`; shade tables for lighting | CONFIRMED, [sprites](sprites.md) |
| 7 | `b.256` | edge-smoothing overlays (not shadows) | 396 | as `.256`; the palette is usually all zero | same RLE as `.256` | medium | the main sprite's palette and frame index; 50 % blend; the Smoothing option | CONFIRMED, [sprites](sprites.md) |
| 8 | `.16a` | icons, spell effects, UI, one font | 782 | 1,024-byte palette; frames; trailer | RLE over 16-bit words: `index << 1 | alpha << 9` | medium | the FADE16 shade table of its palette (alpha = row) | CONFIRMED, [sprites](sprites.md), [palettes §5](palettes.md) |
| 9 | terrain (composite) | map ground | 52 tiles + `dirt.bmp` | `.alm` Tiles block (u16 per cell) → `tile<g>-<nn>.bmp` strips | 8-bit tiles × 96-row shade table | hard | `.alm` sections 1–2, tile flags, [lighting](../mechanics/lighting.md) | CONFIRMED flat (cell bits, strips, water, dirt, lit blit), [terrain](terrain.md); height-displaced blit open |
| 10 | unit animation (composite) | units on the map | 90 sprite sets | `units.reg` (`Palette`, phases, directions) | `.256` + `b.256` + shadows | hard | `.reg` semantics, palettes, mirroring flag, shadow shear | CONFIRMED, [units](units.md) (frame blocks, facing, mirror, placement), [reg](reg.md) |

Not graphics files in this install: `.smk` video (absent, standard Smacker)
and `.res` archives (absent).

## 4. Dependencies

```
.pal ──► .256 ──► b.256
  │        └────► unit animation ◄── .reg (units.reg)
  ├──► .16a (FADE16 tables)
  └──► shade tables ◄── day/night tint, light maps (mechanics/lighting.md)
.bmp ──► terrain ◄── .alm (Tiles, Altitudes)
fontN.dat ──► text rendering ◄── .16 / .16a fonts + code colour tables
```

## Open questions

- Terrain relief: the height-displaced blit ([terrain](terrain.md)).

All open questions: [../open-questions.md](../open-questions.md).
