# Campaign maps (`.alm`, "M7R")

Code: `allods2/alm.py` (container), `allods2/formats/map.py` (`Map`,
`MapHeader`); CLI `python -m allods2 map info|render`; tests
`tests/test_map.py`. 46 maps in `scenario.res` (`scenario/<n>.alm`, 80², 144²
or 256² cells). Reader: `FUN_00534ad4` (file → map object, 0x3b8 bytes),
runtime map builder `FUN_004a449c`. Part 1 is the container, part 2 the
header and terrain; later parts will cover sections 4–12.

## Part 1. Container

Summary; byte accounting in [inventory §5.2](../inventory.md#52-alm-maps-m7r0).
File header 20 bytes: `M7R\0`, u32 `0x14`, u32 `w·h·4 + 72`, u32 section
count (13; the game wants ≥ 3), u32 **version** (1300 in 41 maps, 1600 in 5;
the game rejects > 1600 with "Map version too new" and gates fields on it).
Then per section a 20-byte header `{tag, 0x14, size, id, extra}` + data.
CONFIRMED (`FUN_00534ad4`, reads header → `switch(id)`): the id selects the
decoder; the `tag` is 7 (37 maps) or 5 (9 maps), equal in all sections of
one file, stored as map object `+0x08` and used by nothing found; `extra`
is never read (varies per map, 0 in `74.alm`).

## Part 2. Header and terrain

### Section 0, General block (644 bytes + 16)

CONFIRMED (`FUN_00534ad4`, case 0, sequential 4-byte reads; version gates as
listed). **The section declares 644 bytes but the reader consumes 660**:
the last field is a 512-byte text buffer at +0x94, so its final 16 bytes
lie in the 16 bytes that follow section 0 (the old "section 0 quirk").
`alm.Section.tail` keeps them.

| Off | Type | `MapHeader` field | Meaning |
|---|---|---|---|
| 0x00 | u32 | `width` | cells; 80, 144 or 256 (CONFIRMED: equals `FUN_004a66b0` → runtime width) |
| 0x04 | u32 | `height` | cells; always = width in the campaign |
| 0x08 | f32 | `angle` | initial sun angle: π/4 (0.7854) in 26 maps, 0.7679 (44°) in 18, −π/4 (`31`), 0.6632 (`75`) |
| 0x0c | i32 | `field_0c` | 360 (44 maps) or 720 (`31`, `52`); runtime map `+0x2c`, consumer not found |
| 0x10 | i32 | `ambient` | initial ambient light, 0–23 (21 in 26 maps) |
| 0x14 | i32 | `diffuse` | initial diffuse light, 54–64 (63 in 36 maps) |
| 0x18 | u32 | `tile_sets` | bit mask of tile sets 0–12 |
| 0x1c | u32 | `player_count` | records in section 5 (2–9; 7 in 13 maps) |
| 0x20 | u32 | `n_sec4` | entries of section 4 |
| 0x24 | u32 | `n_sec6` | records of section 6 |
| 0x28 | u32 | `n_sec7` | records of section 7 |
| 0x2c | u32 | `n_sec8` | records of section 8 |
| 0x30 | u32 | `n_sec10` | version > 1149; section 10, always 0 |
| 0x34, 0x38, 0x3c | u32 ×3 | `n_sec11` | version > 1229; three lists of section 11 (12 bytes each) |
| 0x40 | u32 | `n_sec12` | version > 1299; entries of section 12 |
| 0x44 | 64 B | `name` | map name |
| 0x84, 0x88 | i32 ×2 | `field_84`, `field_88` | `field_84` is 1 in all 46; `field_88` is 1 in 42 maps, 2 in `52`, 3 in `74`/`95`, 4 in `110`; default 1, 1 when no section 0 |
| 0x8c, 0x90 | i32 ×2 | `field_8c`, `field_90` | version > 1159; `field_8c` 0 in 38 maps, `field_90` 0 in 23 and 60,000,000 in 19; the rest stray memory |
| 0x94 | 512 B | `description` | description |

- **Text**: NUL-terminated, **cp1251** (`decode_text`); everything after the
  NUL is uninitialised editor memory (stack and heap fragments such as
  "Go away from ogre", pointers). 19 of 46 campaign maps have a name
  ("Adamantium mines", "Get Sword", …) and the same 19 a description (author credit
  "by Nozhnin Dmitry aka [DND]WildMaN …"); all are ASCII, so no cp1251
  byte occurs in the install, but the decoder is cp1251 because the game
  stores raw ANSI bytes (as the `main\text` files,
  [fonts](fonts.md#locale-text-chartooema)). Campaign briefings come from
  `main/text/mission%d.txt`, not from here.
- **Light fields** CONFIRMED overwritten: `FUN_004a5dd2` starts by copying
  the global ambient `0x6226c4`, diffuse `0x6226c8` and sun angle
  `0x6226d8` into runtime map `+0x1c/+0x1d/+0x20` (`0x4a5de1`–`0x4a5e07`),
  and the light map reads those. The file values (map `+0x18/+0x1c/…`
  copied by `FUN_004a449c` `0x4a44f0`–`0x4a4520`) only seed them before the
  first update ([lighting §1–2](../mechanics/lighting.md)). That they are
  angle / ambient / diffuse is INFERRED from the copy targets (types and
  the 0.7854 = π/4 range match).
- **`tile_sets`** CONFIRMED (data, all 46 maps): every set used in the Tiles
  block is in the mask (equal in 36 maps, a superset in 10). No selector of
  an "environment": the game ignores the mask and loads all 13 sets
  (`FUN_004a449c` stores `0x1fff`, [terrain](terrain.md#strip-files-fun_00476429mask));
  the mask is the editor's list of sets used.
- **Counts** CONFIRMED (data): section 5 is `76 · player_count` bytes, section
  6 `48 · n_sec6`, section 11 `12 · sum(n_sec11)`, section 10 empty, in all
  46 maps (all sizes and counts of sections 4, 7–9, 12 relate through
  variable-length records, left to later parts). Players: `player_count`
  records `{u32, u32, u32 (0 or 5000), name[32], u16 × 16}` (INFERRED:
  first record "Self"/"self" = the human; the u16 row is a relation row
  with 18 on the diagonal).
- Not decoded: `field_0c`, `field_84/88/8c/90` (see open questions).

### Sections 1–3, fixed layers

CONFIRMED (sizes by data on all maps; copy by `FUN_004a449c`, [terrain
§ Altitudes](terrain.md#altitudes--runtime-height-map)):

| ID | Name | Size | `Map` attribute |
|---|---|---|---|
| 1 | Tiles | `w·h·2` | `terrain` (h, w) uint16, raw cell values |
| 2 | Altitudes | `w·h` | `heights` uint8 (the game reads them signed) |
| 3 | Objects | `w·h` | `objects` uint8 = object index + 1 |

Any other section stays raw: `Map.sections[id]` (bytes).

### Terrain cell → tile image

Cell layout, the strip file for each cell, water frames and the draw
geometry are in [terrain.md](terrain.md) (CONFIRMED; routines
`FUN_00404e0e` cell decode and draw, `FUN_00476429` strip loader,
`FUN_00457487`/`FUN_004575fe` blits). Recap: `v & 0xf` tile in strip,
`(v >> 4) & 3` strip, `(v & 0x1fff) >> 6` set 0–12, bit 13 dirt, bits 14–15
fog. Geometry: a square 32 × 32 cell, x = 32·column, y = 32·row − height
(heights displace the corners, no isometric projection), rows drawn top to
bottom; an 8-cell border surrounds the playable area (objects are only
copied for rows 8…h−5, columns 8…w−9; `FUN_0041c071` addresses cells 8…w−9).

**Dirt flag (CONFIRMED, new)**: `FUN_004a449c` ends by clearing bit 13
(`& 0xdfff`, `0x4a53f7`; the other load path does the same at `0x4a5cad`)
in every cell, so the 1,654 dirt cells in the files are never drawn. The
flag is set again at run time from a server message that run-length encodes
it over the playable area (`FUN_0041c071`, called from the client message
loop `FUN_0040d9b2`); its server-side source (probably structure
foundations) is untraced. `Map.runtime_terrain()` clears the bit; the
renderer does too unless `--dirt` is given.

Fog bits 14–15 are 0 in every file.

### Checks

`tests/test_map.py`: all 46 headers parse with consistent sizes and counts;
the tile sets used are within `tile_sets`; every cell resolves to a tile
except the 5 known cells of `74.alm`; synthetic maps (cp1251 text, version
gates, the 16-byte tail, sizes, raw sections, CLI) run without game files.

Renders for visual comparison: `python -m allods2 map render 10
out/maps/10.png [--relief]`. Flat = plain strip palette, no light (dark);
`--relief` = heights plus the terrain light with day/night off
(`daylight(0, False)`), the closest to the game; fog, objects, structures and
units are not drawn.

## Open questions

- `field_0c` (360/720, runtime map `+0x2c`): consumer; `field_84/88` (1…4)
  and `field_8c/90`: reader stores them at object `+0xd8/+0xdc/+0xe0/+0xe4`,
  users untraced (candidates: map limits for players, game mode flags).
- Source of the run-time dirt flag on the server (the run-length message
  `FUN_0041c071`).
- Sections 4–12 (entries, units, players, triggers).
