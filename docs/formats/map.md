# Campaign maps (`.alm`, "M7R")

Code: `allods2/alm.py` (container), `allods2/formats/map.py` (`Map`,
`MapHeader`), `allods2/formats/passability.py` (part 3); CLI
`python -m allods2 map info|render`; tests `tests/test_map.py`,
`tests/test_passability.py`. 46 maps in `scenario.res` (`scenario/<n>.alm`, 80², 144²
or 256² cells). Reader: `FUN_00534ad4` (file → map object, 0x3b8 bytes),
runtime map builder `FUN_004a449c`. Part 1 is the container, part 2 the
header and terrain, part 3 heights and passability; later parts will cover
sections 4–12.

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
| 2 | Altitudes | `w·h` | `heights` uint8 (the game reads them signed: `heights_i8`) |
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
foundations) is untraced. The server's path finder, however, reads the
file's tiles with the bit still set and treats it as blocked
([part 3](#part-3-heights-and-passability)). `Map.runtime_terrain()` clears the bit; the
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

## Part 3. Heights and passability

### Heights (section 2)

CONFIRMED (`FUN_004a449c`, `FUN_004065b1`, [terrain § Vertex table](terrain.md#vertex-table-fun_004065b1)):
**one signed byte per vertex**, not per cell: `H[y][x]` is the height of
the top-left corner of cell `(x, y)`, so the last row and column only
serve as corners. Value range in the 46 files **0..127** (min 0, max 127;
no negative value), by the test `test_layers_match_the_header_and_value_range`.
Unit: **1 pixel** of vertical screen offset (`y = 32·row − H`, see terrain.md;
renders `map render --relief`). Steps between neighbouring vertices reach
126 in the data, so cliffs of several tiles exist.

Uses (CONFIRMED, every reader of the height table found by scan):

| Use | Routine | Rule |
|---|---|---|
| Terrain draw | `FUN_004065b1` | corner y = `32·r − H` |
| Ground height under a unit (`unit+0x6c`) | `FUN_0046025d`, map copy `FUN_004a62fd` | below; unit and structure draws subtract it from y (`0x46346a`, [animation §4.2](animation.md#42-structures-and-bridges)) |
| Walking speed | `FUN_00559195` (server) | slope term below |
| Sight (line of sight) | `FUN_00552929`, `FUN_00552c28`, `FUN_00552af8` | below |
| Passability | none | the block layer never reads heights |

**Ground height of a unit** (`FUN_0046025d`): position `(x, y)` in 1/256
cell, footprint `sx × sy` cells (vtable `+0x20/+0x24`): `X = x − 0x80 +
sx·0x80`, `Y = y − 0x80 + sy·0x80`, `c = X >> 8`, `r = Y >> 8`, `fx = (X >> 3)
& 31`, `fy = (Y >> 3) & 31`; `a = H[r][c] + ((H[r][c+1] − H[r][c])·fx)/32`,
`b = H[r+1][c] + ((H[r+1][c+1] − H[r+1][c])·fx)/32`, `h = a + ((b − a)·fy)/32`
with C division (toward 0). A 1 × 1 unit at a cell centre stands at the mean
of the four corners. The map method `FUN_004a62fd` is the same with 256
steps (`fx = x & 0xff`, `>> 8`).

**Slope and speed** (`FUN_00559195`, only for walkers, `movementType` 1):
the step to the next cell (direction 0..7 from the table at `+0x58e98`)
uses `dh = clamp(H[here] − H[next], ±32)` on the two vertices at the cell
indices; with `v = speed · SpeedMultiplier` (`map.reg` Path Finding, 8):
`v += v·dh >> 6` (downhill faster, uphill slower: at most ±50 %), then
`v /= (cost(here) + cost(next)) >> 1` (cost layer below; 0 counts as 8),
clamped to 1..63. This is a speed, not a barrier: **there is no slope limit**;
6 horizontally adjacent walkable pairs on `83.alm` differ by more than 32
(largest 50, at (128,133)–(129,133)). Flyers use `speed`, unscaled.

**Sight** (`FUN_00552929`): a 41 × 41 window around the viewer. The
centre budget is `scanRange << ScanShift` (type `+0xa5`; `map.reg` Scanning,
7); each ring outward takes the budget of the neighbour towards the centre
minus a distance table and **`H[cell] − H[viewer]`** (higher ground costs
sight, lower ground gives some back); a cell is seen while the budget is
above 0. Inputs are therefore only the heights and the scan range;
objects are not consulted (the `FUN_00552c28` variant gates cells with
`FUN_00559536`, untraced). The exact tables are INFERRED from the
decompile and not reproduced (open question).

### Passability: derived, not stored

CONFIRMED (data): no section holds a passability layer; sections 1–3 are
the only per-cell blocks (`w·h` or `2·w·h`, [Part 1](#part-1-container)).
The server's path finder derives it when the map loads: `FUN_005606aa`
reads the file with `FUN_00534ad4` (the raw object: width `+0`, height `+4`,
tiles `+0xc`, **objects `+0x10`, heights `+0x14`**, no cell cleared) and passes it
to the path finder constructor `FUN_0054d2d9` → `FUN_00553d51` (tables) and
`FUN_00554626` (grid build). All grids use a **256-cell stride** (`index =
y·256 + x`, maps smaller than 256 leave the rest unused):

| Offset | Content |
|---|---|
| `+0x00000` | cost layer, u8 |
| `+0x10000` | block layer, u8 bit mask (static bits + dynamic stamps) |
| `+0x20000` | copy of the block layer after the static build (reset source) |
| `+0x30000` | u16 distances of the search |
| `+0x944f4` | heights, copy of section 2 |
| `+0x540a6` / `+0x54126` / `+0x54146` | tile shape table, set types, type costs |
| `+0x58eb8..bf` | playable rectangle: `(8, 8, w−9, h−9)` |

**Terrain type** (`FUN_0055494d`): from the cell value `v` (low 10 bits:
row `v & 15`, strip `(v >> 4) & 3`, set `(v >> 6) & 15`):

- water (`v & 0x300 == 0x200`, sets 8..11): type `Land` if row 4 of strip 1
  (the shore tile), `Water` for rows 0..7, 0xFF for rows ≥ 8; cost always 8;
- else row ≥ 14: type 0xFF, cost 8 (the 5 cells of `74.alm`);
- else the set gives two types `(a, b)` and the tile a **shape** 1..5; type =
  `b` for shapes 1–2, `a` for 3–5; cost = `cost[b]`, `(cost[a] + 3·cost[b]) >> 2`,
  `(cost[a] + cost[b]) >> 1`, `(3·cost[a] + cost[b]) >> 2`, `cost[a]` for
  shapes 1..5.

Type ids: 0 none, 1 Land, 2 Grass, 3 Flowers, 4 Sand, 5 Cracked, 6 Stones,
7 Savanna, 8 Mountain, 9 Water, 10 Road. Set types (a, b): 0 Grass/Land,
1 Cracked/Land, 2 Sand/Land, 3 Savanna/Land, 4 Stones/Land, 5 Cracked/Stones,
6 Flowers/Savanna, 7 Mountain/Stones, 12 Road/Land. The shape table (strips 0..3 × rows
0..13) and these pairs are in `passability.py` (values CONFIRMED from the
constructor's stores). Costs are read from `world/data/map.reg` `[Terrain]
Cost<Name>` (`FUN_004e6f9f`, defaults in the code); shipped: Land 8, Grass 8,
Flowers 8, Sand 14, Cracked 6, Stones 12, Savanna 8, Mountain 16, Water 8,
Road 6. The `Pass<Name>` keys of that file (Mountain, Water, Road = 1) are
**never read**: the strings are not in the exe.

**Block layer, static build** (`FUN_00554626`, in this order per cell, from
the raw file values; fog bits are 0):

1. `v & 0x2000` (the dirt flag, still set: the server does not clear it) → 1;
2. terrain type is Mountain → 1;
3. water (sets 8..11) → 1;
4. Objects block byte ≠ 0 → **5** (replaces the above; every object blocks,
   `objects.reg` has no passability field);
5. afterwards `FUN_00553b30` writes `0x1F` over the 8-cell border on all
   sides (square maps; a non-square map uses the 256 × 256 rims, not
   reproduced, no campaign map needs it).

Then the layer is copied to `+0x20000`. Data (46 maps): the playable-area
values are only 0, 1, 5; walkers can enter 21 % (maps 93–96) to 89 % of it.

**Who is stopped by what.** A mover of `movementType` m (data.bin monsters;
humans are −1 and take 1) may enter a cell when `block & mask == 0`
(`FUN_0055d010`; mask `*(mover+0x1c0)+5`, set by `FUN_00557a89` from the
vtable `+0x20` result, constructor default 0x41 `FUN_00551346`):

| m | Units (data) | mask | Stopped by |
|---|---|---|---|
| 1 | 155 monsters (walkers, catapults); humans (assumed) | `0x41` | bit 0 (water, mountain, dirt, object, border), bit 6 |
| 2 | Ghost, Bee (+ `.2`–`.5`) | `0x44` | bit 2 (objects, border), bit 6: crosses water, mountain, dirt |
| 3 | Bat_Sonic, Dragon, Succubus (+ `.2`–`.5`) | `0x82` | bit 1 (border), bit 7: only the map border and each other |

The mapping `movementType` → m is INFERRED (the vtable slot was not
followed per class; the type 2/3 split by name matches ghosts/bees and
fliers). The other bits are stamped at run time (INFERRED from `FUN_00550a96`:
bit `0x20` marks a cell with an occupant record; an object with a footprint
mask gets 5 on its solid cells and has bits 0 and 2 cleared, and the cost set
to Cracked, on the rest) and are not part of the file-derived grid.

API: `Map.block`, `Map.passability(movement_type)` (bool), `Map.cost(costs)`,
`Map.heights_i8`; `passability.costs_from_reg(map_reg)`. Overlay check: a red
(bit 0) / yellow (objects) / magenta (border) render of `10.alm` follows
the water/mountain shapes and the placed objects (`out/maps/10_block.png`,
local only).

### VERIFY IN GAME

- Can a walker enter the cell (27,10) of `10.alm` (object 47, block 5)?
  Predicted: no. Same for a cell whose object has no collision look (bushes).
- `71.alm` (8,9): dirt flag, no object (block 1). Predicted: **blocked** from
  the start of the mission; (16,9) has dirt and an object (block 5).
- `10.alm` (61,8): mountain tile, no object (block 1). Predicted: walkers
  stop, a Ghost/Bee crosses.
- Steep ground: `83.alm` (128,133)→(129,133) drops 50 units. Predicted:
  walkable, uphill about 22–50 % slower, no slope limit.
- Does a unit's sight really shrink behind a hill (higher `H` than the
  viewer along the ray)? Compare the fog around a unit on a ridge and in a
  hollow.
- Which type a unit `movementType` selects for humans (−1 in the data) and
  for the hero classes: assumed walker (1).

## Open questions

- `field_0c` (360/720, runtime map `+0x2c`): consumer; `field_84/88` (1…4)
  and `field_8c/90`: reader stores them at object `+0xd8/+0xdc/+0xe0/+0xe4`,
  users untraced (candidates: map limits for players, game mode flags).
- Source of the run-time dirt flag on the server (the run-length message
  `FUN_0041c071`).
- Line of sight: the distance tables (`+0x22000` steps, `+0x28000`
  `ftol` of a power of `dx² + dy²`) and the `FUN_00559536` gate of
  `FUN_00552c28`; callers (`FUN_00552929` has no direct caller: vtable?).
- Block bits 3–7 and the dynamic stamping (`FUN_00550a96`,
  `FUN_0055c500`), the per-class `movementType` result (vtable `+0x20`),
  and the search itself (`FUN_0054d76e`, `FUN_0055d010`): phase H.
- Sections 4–12 (entries, units, players, triggers).
